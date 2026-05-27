from pathlib import Path

import pytest

from validation import main as validation_main
from validation import validate_eicr
from validation.main import ValidationResult


class FakeAssert:
    local_name = "failed-assert"

    def get_attribute_value(self, attribute: str) -> str:
        values = {
            "id": "ttc-labTestNameOrdered-noCode",
            "location": "/ClinicalDocument/component/structuredBody/component/section/entry/observation",
        }

        return values[attribute]


class FakeRoot:
    def __init__(self) -> None:
        """Represents the root of the SVRL output, which contains failed-assert children."""
        self.children = [FakeAssert()]


class FakeExecutable:
    def apply_templates_returning_value(self, xdm_value: str) -> list[list[FakeRoot]]:
        """Simulates applying the XSLT stylesheet to the XML document and returning SVRL output."""
        return [[FakeRoot()]]


class FakeXsltProcessor:
    def __init__(self) -> None:
        """Simulates the XSLT processor, recording transformations applied."""
        self.transforms: list[tuple[str, str, str]] = []

    def transform_to_file(self, source_file: str, stylesheet_file: str, output_file: str) -> None:
        """Simulates transforming an XML file with an XSLT stylesheet and writing to an output file."""
        self.transforms.append((source_file, stylesheet_file, output_file))
        Path(output_file).write_text("<generated />")

    def compile_stylesheet(self, stylesheet_file: str) -> FakeExecutable:
        """Simulates compiling an XSLT stylesheet into an executable."""
        return FakeExecutable()


class FakeSaxonProcessor:
    version = "Fake Saxon/C"
    """Simulates the Saxon/C processor."""

    def __init__(self, license: bool) -> None:
        """Initializes the Saxon/C processor with a license flag and an XSLT processor."""
        self.license = license
        self.xslt_processor = FakeXsltProcessor()

    def __enter__(self) -> "FakeSaxonProcessor":
        """Enters the context manager, returning itself to be used for transformations."""
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        """Exits the context manager, performing any necessary cleanup (none in this fake implementation)."""
        return

    def new_xslt30_processor(self) -> FakeXsltProcessor:
        """Returns the XSLT processor to be used for transformations."""
        return self.xslt_processor

    def parse_xml(self, xml_text: str | None) -> str:
        """Simulates parsing an XML string into an XDM node, which in this fake implementation is just the string itself."""
        return xml_text or ""


class BrokenSaxonProcessor:
    def __init__(self, license: bool) -> None:
        """Simulates a Saxon/C processor that raises an error when used, to test error handling in the validation function."""
        self.license = license

    def __enter__(self) -> "BrokenSaxonProcessor":
        """Raises a RuntimeError to simulate a failure when entering the context manager."""
        raise RuntimeError("validator failed")

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        """Exits the context manager, which in this case is not reached due to the error raised in __enter__."""
        return


def test_validation():
    """Tests that the validate_eicr function correctly processes an eICR and returns expected validation results."""
    with Path("packages/validation/tests/assets/test_eicr.xml").open() as f:
        eicr = f.read()
    results = validate_eicr(eicr)

    assert results == [
        ValidationResult(
            error_id="ttc-labTestNameOrdered-noCode",
            locations=[
                "/Q{urn:hl7-org:v3}ClinicalDocument[1]/Q{urn:hl7-org:v3}component[1]/Q{urn:hl7-org:v3}structuredBody[1]/Q{urn:hl7-org:v3}component[1]/Q{urn:hl7-org:v3}section[1]/Q{urn:hl7-org:v3}entry[1]/Q{urn:hl7-org:v3}observation[1]",
            ],
        )
    ]


def test_validation_no_errors():
    """Tests that the validate_eicr function returns an empty list when there are no validation errors."""
    with Path("e2e/snapshots/test_e2e/test_upload_and_process/augmented_eicr.xml").open() as f:
        eicr = f.read()
    results = validate_eicr(eicr)

    assert results == []


def test_validation_redoes_all_steps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Tests that the validate_eicr function redoes all steps of the validation process when redo_all_steps is True, and that it returns expected validation results."""
    stage1_output = tmp_path / "stage1.sch.tmp"
    stage2_output = tmp_path / "stage2.sch.tmp"
    validator_output = tmp_path / "validator.xsl.tmp"

    stage1_output.write_text("old stage 1")
    stage2_output.write_text("old stage 2")
    validator_output.write_text("old validator")

    monkeypatch.setattr(validation_main, "STAGE1_OUTPUT", stage1_output)
    monkeypatch.setattr(validation_main, "STAGE2_OUTPUT", stage2_output)
    monkeypatch.setattr(validation_main, "VALIDATOR_OUTPUT", validator_output)
    monkeypatch.setattr(validation_main, "APHL_SCHEMATRON", tmp_path / "schema.sch")
    monkeypatch.setattr(validation_main, "XSLT_INCLUDE", tmp_path / "include.xsl")
    monkeypatch.setattr(validation_main, "XSLT_EXPAND", tmp_path / "expand.xsl")
    monkeypatch.setattr(validation_main, "XSLT_COMPILE", tmp_path / "compile.xsl")
    monkeypatch.setattr(validation_main, "PySaxonProcessor", FakeSaxonProcessor)

    results = validate_eicr("<ClinicalDocument />", redo_all_steps=True)

    assert results == [
        ValidationResult(
            error_id="ttc-labTestNameOrdered-noCode",
            locations=[
                "/ClinicalDocument/component/structuredBody/component/section/entry/observation",
            ],
        )
    ]
    assert stage1_output.read_text() == "<generated />"
    assert stage2_output.read_text() == "<generated />"
    assert validator_output.read_text() == "<generated />"


def test_validation_uses_existing_generated_files(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Tests that the validate_eicr function uses existing generated files for steps 1-3 of the validation process when redo_all_steps is False, and that it returns expected validation results."""
    stage1_output = tmp_path / "stage1.sch.tmp"
    stage2_output = tmp_path / "stage2.sch.tmp"
    validator_output = tmp_path / "validator.xsl.tmp"

    stage1_output.write_text("existing stage 1")
    stage2_output.write_text("existing stage 2")
    validator_output.write_text("existing validator")

    monkeypatch.setattr(validation_main, "STAGE1_OUTPUT", stage1_output)
    monkeypatch.setattr(validation_main, "STAGE2_OUTPUT", stage2_output)
    monkeypatch.setattr(validation_main, "VALIDATOR_OUTPUT", validator_output)
    monkeypatch.setattr(validation_main, "PySaxonProcessor", FakeSaxonProcessor)

    results = validate_eicr("<ClinicalDocument />")

    assert results == [
        ValidationResult(
            error_id="ttc-labTestNameOrdered-noCode",
            locations=[
                "/ClinicalDocument/component/structuredBody/component/section/entry/observation",
            ],
        )
    ]
    assert stage1_output.read_text() == "existing stage 1"
    assert stage2_output.read_text() == "existing stage 2"
    assert validator_output.read_text() == "existing validator"


def test_validation_returns_empty_list_when_validator_errors(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """Tests that the validate_eicr function returns an empty list and logs an error when the validator fails."""
    monkeypatch.setattr(validation_main, "PySaxonProcessor", BrokenSaxonProcessor)

    results = validate_eicr("<ClinicalDocument />")

    assert results == []
    assert "An error occurred during validation: validator failed" in caplog.text
