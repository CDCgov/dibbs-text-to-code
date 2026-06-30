from enum import StrEnum
from typing import ClassVar

from pydantic import Field

from shared_models import LOINC_NAME, LOINC_OID, DataField, FrozenBaseModel

from ..models.eicr import LabXPaths


class CodeTranslation(StrEnum):
    """Logical classification of known code systems used to prioritize translation candidates.

    This enum is not derived from raw XML directly. Instead, it is inferred by comparing a
    Candidate.system value against configured system URI lists.

    :returns: A CodeTranslation enum value when the candidate system matches a configured
        code system list, otherwise None.
    """

    LOINC = LOINC_NAME
    SNOMED = "SNOMED"


class CodeSystemValues(list[str]):
    """A list of code system identifier strings used to classify translation candidates."""

    LOINC_VALUES: ClassVar[list[str]] = [
        "http://loinc.org",
        f"urn:oid:{LOINC_OID}",
    ]

    SNOMED_VALUES: ClassVar[list[str]] = [
        "http://snomed.info/sct",
        "urn:oid:2.16.840.1.113883.6.96",
    ]


class TranslationSelectionStrategy(StrEnum):
    """Strategy for selecting one translation candidate when multiple are available.

    FIRST:
        Always return the first translation candidate encountered.

    PREFER_SYSTEM_ORDER:
        If any translation has system information, prefer:
        1) LOINC
        2) SNOMED
        3) otherwise, the first translation
    """

    FIRST = "first"
    PREFER_SYSTEM_ORDER = "prefer_system_order"


class TranslationPreference(FrozenBaseModel):
    """Preferences for choosing among multiple translations when a system attribute is available.

    :param strategy: Strategy used when selecting among multiple translation candidates.
    :param loinc_system_values: System identifiers that should be treated as LOINC.
    :param snomed_system_values: System identifiers that should be treated as SNOMED.
    """

    strategy: TranslationSelectionStrategy = TranslationSelectionStrategy.PREFER_SYSTEM_ORDER
    loinc_system_values: list[str] = Field(
        default_factory=list,
        description="System identifiers that should be treated as LOINC.",
    )
    snomed_system_values: list[str] = Field(
        default_factory=list,
        description="System identifiers that should be treated as SNOMED.",
    )


class XPathPriority(FrozenBaseModel):
    """A single prioritized source of candidate text.

    :param xpath: The LabXPaths entry identifying where the candidate text was extracted from.
    :param priority: Numeric priority where 1 is highest priority.
    :param rules: Optional rule overrides applied only for this specific XPath source.
    """

    xpath: LabXPaths
    priority: int = Field(..., ge=1)


class BaseEvaluationCriteria(FrozenBaseModel):
    """Base configuration for selecting the most relevant text for a given DataField.

    :param data_field: The DataField this evaluation criteria applies to.
    :param priorities: Prioritized XPath sources considered during evaluation.
    :param rules: Optional rules applied to candidates during evaluation.
    :param translation_preference: Preferences for selecting among translation candidates.
    """

    data_field: DataField | None = Field(
        default=None,
        description="The DataField this evaluation criteria applies to.",
    )
    priorities: list[XPathPriority] = Field(
        default_factory=list,
        description="Prioritized XPath sources considered during evaluation.",
    )
    translation_preference: TranslationPreference = Field(
        default_factory=TranslationPreference,
        description="Preferences used when selecting among translation candidates.",
    )

    def ordered_priorities(self) -> list[XPathPriority]:
        """Return candidate priorities sorted from highest to lowest importance.

        :returns: A list of XPathPriority entries sorted by ascending priority value.
        """
        return sorted(self.priorities, key=lambda p: p.priority)


class LabTestNameOrderedEvaluationCriteria(BaseEvaluationCriteria):
    """Evaluation criteria for selecting text relevant to Lab Test Name Ordered.

    This config encodes the memo priority order:
    1) code/displayName
    2) translation/displayName
    3) code/originalText
    4) translation/originalText
    """

    data_field: DataField = DataField.LAB_TEST_NAME_ORDERED

    priorities: list[XPathPriority] = Field(
        default_factory=lambda: [
            XPathPriority(xpath=LabXPaths.CODE_DISPLAY_NAME, priority=1),
            XPathPriority(xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME, priority=2),
            XPathPriority(xpath=LabXPaths.CODE_ORIGINAL_TEXT, priority=3),
            XPathPriority(xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT, priority=4),
            XPathPriority(xpath=LabXPaths.OBSERVATION_TEXT, priority=5),
        ]
    )

    translation_preference: TranslationPreference = Field(
        default_factory=lambda: TranslationPreference(
            strategy=TranslationSelectionStrategy.PREFER_SYSTEM_ORDER,
            loinc_system_values=CodeSystemValues.LOINC_VALUES,
            snomed_system_values=CodeSystemValues.SNOMED_VALUES,
        )
    )


class LabTestNameResultedEvaluationCriteria(BaseEvaluationCriteria):
    """Evaluation criteria for selecting text relevant to Lab Test Name Resulted.

    This config encodes the memo priority order:
    1) code/displayName
    2) translation/displayName
    3) code/originalText
    4) translation/originalText
    """

    data_field: DataField = DataField.LAB_TEST_NAME_RESULTED

    priorities: list[XPathPriority] = Field(
        default_factory=lambda: [
            XPathPriority(xpath=LabXPaths.CODE_DISPLAY_NAME, priority=1),
            XPathPriority(xpath=LabXPaths.CODE_TRANSLATION_DISPLAY_NAME, priority=2),
            XPathPriority(xpath=LabXPaths.CODE_ORIGINAL_TEXT, priority=3),
            XPathPriority(xpath=LabXPaths.CODE_TRANSLATION_ORIGINAL_TEXT, priority=4),
            XPathPriority(xpath=LabXPaths.OBSERVATION_TEXT, priority=5),
        ]
    )

    translation_preference: TranslationPreference = Field(
        default_factory=lambda: TranslationPreference(
            strategy=TranslationSelectionStrategy.PREFER_SYSTEM_ORDER,
            loinc_system_values=[
                "http://loinc.org",
                f"urn:oid:{LOINC_OID}",
            ],
            snomed_system_values=[
                "http://snomed.info/sct",
                "urn:oid:2.16.840.1.113883.6.96",
            ],
        )
    )


EvaluationConfigType = type[BaseEvaluationCriteria]
EVALUATION_REGISTRY: dict[DataField, EvaluationConfigType] = {
    DataField.LAB_TEST_NAME_ORDERED: LabTestNameOrderedEvaluationCriteria,
    DataField.LAB_TEST_NAME_RESULTED: LabTestNameResultedEvaluationCriteria,
}
