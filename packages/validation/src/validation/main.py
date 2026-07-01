import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from saxonche import PySaxonProcessor  # ty: ignore[unresolved-import]

from shared_models import FrozenBaseModel

BASE_FOLDER = Path(__file__).parent / "eicr-validator"

EICR_FOLDER = BASE_FOLDER / "eicr"
OUTPUT_FOLDER = BASE_FOLDER / "output"
RESULT_FOLDER = OUTPUT_FOLDER / "result"
SCHEMA_FOLDER = BASE_FOLDER / "schematron"
XSLT_FOLDER = BASE_FOLDER / "schxslt"

APHL_SCHEMATRON = SCHEMA_FOLDER / "APHL_TextToCodeSchematron_09252025.sch"
STAGE1_OUTPUT = OUTPUT_FOLDER / "stage1.sch.tmp"
STAGE2_OUTPUT = OUTPUT_FOLDER / "stage2.sch.tmp"
VALIDATOR_OUTPUT = OUTPUT_FOLDER / "validator.xsl.tmp"
VOC_OUTPUT = OUTPUT_FOLDER / "voc_ttc.xml"
VOC_SOURCE = SCHEMA_FOLDER / "voc_ttc.xml"
XSLT_COMPILE = XSLT_FOLDER / "compile-for-svrl.xsl"
XSLT_EXPAND = XSLT_FOLDER / "expand.xsl"
XSLT_INCLUDE = XSLT_FOLDER / "include.xsl"

logger = logging.getLogger(__name__)

# Saxon emits failed-assert locations in EQName (Clark) notation, e.g.
# ``/Q{urn:hl7-org:v3}ClinicalDocument[1]/Q{urn:hl7-org:v3}component[1]``.
_NAMESPACE_STEP = re.compile(r"Q\{[^}]*\}")


class ValidationResult(FrozenBaseModel):
    """Error ID and location."""

    error_id: str
    location: str


@dataclass(frozen=True)
class _RawAssert:
    """A single failed-assert parsed from the validator's SVRL output."""

    error_id: str
    location: str
    test: str
    message: str


def _normalize_location(location: str) -> str:
    """Strip Saxon EQName namespace prefixes from a failed-assert location.

    Downstream Text-to-Code processing strips namespaces from the eICR tree and
    evaluates plain paths, so ``/Q{urn:hl7-org:v3}ClinicalDocument[1]/...`` must
    be rewritten to ``/ClinicalDocument[1]/...``.

    :param location: The raw Saxon location XPath.
    :return: The location with ``Q{...}`` namespace prefixes removed.
    """
    return _NAMESPACE_STEP.sub("", location)


def _normalize_whitespace(value: str | None) -> str:
    """Collapse runs of whitespace to single spaces, or return empty for None.

    :param value: The string to normalize, which may be None.
    :return: The whitespace-normalized string.
    """
    return " ".join(value.split()) if value else ""


def _run_validator(eicr: str | None, redo_all_steps: bool = False) -> list[_RawAssert]:
    """Compile the schematron and run it against the eICR, returning failed asserts.

    :param eicr: The eICR XML document as a string.
    :param redo_all_steps: When True, regenerate the cached XSLT artifacts.
    :return: The list of failed asserts emitted by the validator.
    """
    logger.info("Starting eICR Validation")
    logger.info(f"For eICR: {eicr}")
    asserts: list[_RawAssert] = []

    try:
        with PySaxonProcessor(license=False) as proc:
            logger.info(f"Saxon/C version: {proc.version}")
            xsltproc = proc.new_xslt30_processor()
            # The cached XSLT artifacts (steps 1-3) are written here. The wheel
            # ships no output/ dir, so create it before the first write.
            STAGE1_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            if redo_all_steps:
                logger.info("Remove all previous files generated at all steps")
                STAGE1_OUTPUT.unlink(missing_ok=True)
                STAGE2_OUTPUT.unlink(missing_ok=True)
                VALIDATOR_OUTPUT.unlink(missing_ok=True)
                VOC_OUTPUT.unlink(missing_ok=True)
            else:
                logger.info("Will use existing files for Step 1-3")

            if not STAGE1_OUTPUT.exists():
                # Step 1: Process includes
                # Note: For schxslt, you typically apply the XSLT to the SCH file as the source
                logger.info("--- Step 1: Process Includes against Schematron File")
                xsltproc.transform_to_file(
                    source_file=str(APHL_SCHEMATRON),
                    stylesheet_file=str(XSLT_INCLUDE),
                    output_file=str(STAGE1_OUTPUT),
                )

            if not STAGE2_OUTPUT.exists():
                # Step 2: Expand abstract rules
                logger.info("--- Step 2: Expand abstract rules using output from Step 1")
                xsltproc.transform_to_file(
                    source_file=str(STAGE1_OUTPUT),
                    stylesheet_file=str(XSLT_EXPAND),
                    output_file=str(STAGE2_OUTPUT),
                )

            if not VALIDATOR_OUTPUT.exists():
                # Step 3: Compile to an SVRL-producing XSLT stylesheet
                logger.info(
                    "--- Step 3: Compile to an SVRL-producing XSLT stylesheet using the output from Step 2"
                )
                xsltproc.transform_to_file(
                    source_file=str(STAGE2_OUTPUT),
                    stylesheet_file=str(XSLT_COMPILE),
                    output_file=str(VALIDATOR_OUTPUT),
                )

            # Ensure the document()-referenced vocab sits next to the generated stylesheet.
            # Guarded like the stage artifacts above: on Lambda the package dir is read-only
            # and this file is baked into the image at build time (Dockerfile.augmentation),
            # so an unconditional copy would crash with OSError [Errno 30] on every invocation.
            if not VOC_OUTPUT.exists():
                shutil.copy2(VOC_SOURCE, VOC_OUTPUT)

            # Step 4: Apply the generated XSLT to the source XML
            # Parse the XML string into an XDM node
            xml_node = proc.parse_xml(xml_text=eicr)

            # Use the node as the source for transformation
            executable = xsltproc.compile_stylesheet(stylesheet_file=str(VALIDATOR_OUTPUT))
            result = executable.apply_templates_returning_value(xdm_value=xml_node)
            logger.info(result)

            for x in result[0][0].children:
                if x.local_name == "failed-assert":
                    # The human-readable message lives in the <svrl:text> child.
                    message = ""
                    for child in x.children:
                        if child.local_name == "text":
                            message = (child.string_value or "").strip()
                            break
                    asserts.append(
                        _RawAssert(
                            error_id=x.get_attribute_value("id"),
                            location=x.get_attribute_value("location"),
                            test=_normalize_whitespace(x.get_attribute_value("test")),
                            message=message,
                        )
                    )
    except Exception as e:
        logger.exception(f"An error occurred during validation: {e}")
        raise

    return asserts


def validate_eicr(eicr: str | None = None, redo_all_steps: bool = False) -> list[ValidationResult]:
    """Validate an eICR.

    :param eicr: The eICR XML document as a string.
    :param redo_all_steps: When True, regenerate the cached XSLT artifacts.
    :return: The list of validation errors found.
    """
    return [
        ValidationResult(error_id=raw.error_id, location=raw.location)
        for raw in _run_validator(eicr, redo_all_steps=redo_all_steps)
    ]


def _validation_result_xml(raw: _RawAssert) -> str:
    """Serialize one failed assert into a NIST ``<validationResult>`` fragment.

    The ``xmlns=""`` reset is required: the Text-to-Code reader locates the issue
    fields with namespace-less ``find()`` calls.

    :param raw: The failed assert to serialize.
    :return: The XML fragment for the validation result.
    """
    return (
        '        <validationResult xmlns="">\n'
        '            <issue severity="errors">\n'
        f"                <assertionID>{escape(raw.error_id)}</assertionID>\n"
        f"                <message>{escape(raw.message)}</message>\n"
        f"                <context>{escape(_normalize_location(raw.location))}</context>\n"
        f"                <test>{escape(raw.test)}</test>\n"
        "                <specification />\n"
        "            </issue>\n"
        "        </validationResult>"
    )


def build_schematron_report_xml(eicr: str | None = None, redo_all_steps: bool = False) -> str:
    """Validate an eICR and serialize the results as a NIST cdaGuideValidator ``<Report>``.

    This is the shape the deployed TTC pipeline consumes from
    ``s3://.../ValidationResponseV2/`` (parsed by
    ``text_to_code.services.schematron_processor``): it locates ``validationResult``
    elements and reads their namespace-less ``issue/message``, ``issue/context``
    and ``issue/test`` children, matching the message text against known error
    enums.

    :param eicr: The eICR XML document as a string.
    :param redo_all_steps: When True, regenerate the cached XSLT artifacts.
    :return: The schematron validation report as a NIST ``<Report>`` XML string.
    """
    results = "\n".join(
        _validation_result_xml(raw) for raw in _run_validator(eicr, redo_all_steps=redo_all_steps)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<Report>\n"
        "    <ReportHeader>\n"
        "        <ValidationStatus>Complete</ValidationStatus>\n"
        "    </ReportHeader>\n"
        '    <Results xmlns="urn:gov:nist:cdaGuideValidator">\n'
        f"{results}\n"
        "    </Results>\n"
        "</Report>"
    )
