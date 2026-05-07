import logging
from dataclasses import dataclass
from pathlib import Path

from saxonche import PySaxonProcessor  # ty: ignore[unresolved-import]

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
XSLT_COMPILE = XSLT_FOLDER / "compile-for-svrl.xsl"
XSLT_EXPAND = XSLT_FOLDER / "expand.xsl"
XSLT_INCLUDE = XSLT_FOLDER / "include.xsl"

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Error ID and list."""

    error_id: str
    locations: list[str]


def validate_eicr(eicr: str | None = None, redo_all_steps: bool = False) -> list[ValidationResult]:
    """Validate an eICR."""
    logger.info("Starting eICR Validation")
    logger.info(f"For eICR: {eicr}")
    errors = []
    try:
        with PySaxonProcessor(license=False) as proc:
            logger.info(f"Saxon/C version: {proc.version}")
            xsltproc = proc.new_xslt30_processor()
            if redo_all_steps:
                logger.info("Remove all previous files generated at all steps")
                STAGE1_OUTPUT.unlink(missing_ok=True)
                STAGE2_OUTPUT.unlink(missing_ok=True)
                VALIDATOR_OUTPUT.unlink(missing_ok=True)
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

            # Step 4: Apply the generated XSLT to the source XML
            # Parse the XML string into an XDM node
            xml_node = proc.parse_xml(xml_text=eicr)

            # Use the node as the source for transformation
            executable = xsltproc.compile_stylesheet(stylesheet_file=str(VALIDATOR_OUTPUT))
            result = executable.apply_templates_returning_value(xdm_value=xml_node)
            logger.info(result)

            for x in result[0][0].children:
                if x.local_name == "failed-assert":
                    errors.append(
                        {
                            "error_id": x.get_attribute_value("id"),
                            "location": x.get_attribute_value("location"),
                        }
                    )
    except Exception as e:
        logger.error(f"An error occurred during validation: {e}")

    return errors
