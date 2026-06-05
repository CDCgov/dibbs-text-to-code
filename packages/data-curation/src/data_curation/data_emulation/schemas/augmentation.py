"""This module contains the schema definitions for the augmented data.
"""

import enum
from typing import Literal, Optional

import pydantic
from typing_extensions import Annotated


class EnhancementOptions(pydantic.BaseModel):
    """
    The schema for a dictionary of probability settings used for input enhancement
    during data augmentation.
    """

    model_config = pydantic.ConfigDict(from_attributes=True)

    min_enhances: int = pydantic.Field(
        default=1,
        description=(
            "When randomly choosing how many operations to perform as part of this "
            "enhancement, the minimum number that can be selected."
        ),
    )
    max_enhances: int = pydantic.Field(
        default=3,
        description=(
            "When randomly choosing how many operations to perform as part of this "
            "enhancement, the maximum number that can be selected."
        ),
    )
    enhancement_prob: Annotated[float, pydantic.Field(ge=0, le=1)] = pydantic.Field(
        default=0.5,
        description=(
            "The probability that this enhancement will be performed as part of "
            "holistic data augmentation to an input code."
        ),
    )


class InsertionOptions(pydantic.BaseModel):
    """
    The schema for a dictionary of probability settings used for performing
    term insertion on a code string during data augmentation.
    """

    model_config = pydantic.ConfigDict(from_attributes=True)

    min_inserts: int = pydantic.Field(
        default=1,
        description=(
            "The minimum number of insertions that will be performed on the code "
            "string, if insertion is selected."
        ),
    )
    max_inserts: int = pydantic.Field(
        default=3,
        description=(
            "The maximum number of insertions that will be performed on the code "
            "string, if insertion is selected."
        ),
    )
    insert_prob_after_enhance: Annotated[float, pydantic.Field(ge=0, le=1)] = pydantic.Field(
        default=0.5,
        description=(
            "The probability that insertion will be chosen for application, given "
            "that the code string has already been selected for enhancement."
        ),
    )
    insert_prob_without_enhance: Annotated[float, pydantic.Field(ge=0, le=1)] = pydantic.Field(
        default=0.5,
        description=(
            "The probability that insertion will be chosen for application, given "
            "that the code string has not already been selected for enhancement."
        ),
    )


class PermutationOptions(pydantic.BaseModel):
    """
    The schema for a dictionary of probability settings used for performing
    term permutation (swapping) on a code string during data augmentation.
    """

    model_config = pydantic.ConfigDict(from_attributes=True)

    min_swaps: int = pydantic.Field(
        default=1,
        description=(
            "The minimum number of swaps that will be performed on the code "
            "string, if permutation is selected."
        ),
    )
    max_swaps: int = pydantic.Field(
        default=3,
        description=(
            "The maximum number of swaps that will be performed on the code "
            "string, if permutation is selected."
        ),
    )
    swap_prob: Annotated[float, pydantic.Field(ge=0, le=1)] = pydantic.Field(
        default=0.5,
        description=("The probability that permutation will be performed on the code string."),
    )


class DeletionOptions(pydantic.BaseModel):
    """
    The schema for a dictionary of probability settings used for performing
    character deletion on a code string during data augmentation.
    """

    model_config = pydantic.ConfigDict(from_attributes=True)

    deletion_mode: Literal["word", "char"] = pydantic.Field(
        default="char",
        description=(
            "The means of randomly choosing characters to delete from the "
            "code string, if deletion is selected. 'Word' mode first randomly "
            "selects a word in the string, then chooses a character within "
            "that word. 'Char' mode randomly selects a character from any "
            "word in the input, giving all characters the same chance to be "
            "deleted."
        ),
    )
    min_deletes: int = pydantic.Field(
        default=1,
        description=(
            "The minimum number of deletions that will be performed on the code "
            "string, if deletion is selected."
        ),
    )
    max_deletes: int = pydantic.Field(
        default=3,
        description=(
            "The maximum number of deletions that will be performed on the code "
            "string, if deletion is selected."
        ),
    )
    max_deletes_per_word: int = pydantic.Field(
        default=2,
        description=(
            "The maximum number of deletions that can be performed on a single "
            "word in the input string, regardless of the selection mode chosen. "
            "Excess deletions beyond this number on a single word are ignored."
        ),
    )
    deletion_prob: Annotated[float, pydantic.Field(ge=0, le=1)] = pydantic.Field(
        default=0.5,
        description=("The probability that deletion will be performed on the code string."),
    )


class AugmentationConfig(pydantic.BaseModel):
    """
    The schema for a dictionary of configuration options governing how to augment,
    randomize, scramble, and otherwise create noisy interference in a text string
    for the purpose of creating synthetic data.
    """

    model_config = pydantic.ConfigDict(from_attributes=True)

    enhancement_all: Optional[EnhancementOptions] = pydantic.Field(
        default=None,
        description=(
            "A dictionary of EnhancementOptions for the setting 'enhancement_all'. "
            "This setting, if provided, will randomly choose what type of enhancement "
            "to perform on the input string (abbreviation, synonyms, etc.). If this "
            "parameter is provided, other enhancement parameters will not be checked "
            "for or evaluated."
        ),
    )
    enhancement_synonyms: Optional[EnhancementOptions] = pydantic.Field(
        default=None,
        description=(
            "A dictionary of EnhancementOptions for the setting 'enhancement_synonyms'. "
            "This setting, if provided, will apply property-axis word synonym to "
            "tokens in the input string. Will not be used if 'enhancement_all' is "
            "defined, but can be used with enhancement_abbreviation."
        ),
    )
    enhancement_abbreviation: Optional[EnhancementOptions] = pydantic.Field(
        default=None,
        description=(
            "A dictionary of EnhancementOptions for the setting 'enhancement_abbreviation'. "
            "This setting, if provided, will abbreviate word tokens in the input string, "
            "based on LOINC related name properties. Will not be used if "
            "'enhancement_all' is defined, but can be used with enhancement_synonyms "
            "and enhancement_abbreviation."
        ),
    )
    insertion: InsertionOptions = InsertionOptions()
    permutation: PermutationOptions = PermutationOptions()
    deletion: DeletionOptions = DeletionOptions()


class LoincFileGenerationConfig(pydantic.BaseModel):
    """
    The schema for a dictionary of configuration options governing how to generate
    synthetic data specifically for LOINC short names, long common names, and display
    names.
    """

    short_name: AugmentationConfig = AugmentationConfig()
    long_common_name: AugmentationConfig = AugmentationConfig()
    display_name: AugmentationConfig = AugmentationConfig()
