import os

# create a class with the DIBBs default Creative Commons Zero v1.0 and
# MIT license to be used by the BaseService class
LICENSES = {
    "CreativeCommonsZero": {
        "name": "Creative Commons Zero v1.0 Universal",
        "url": "https://creativecommons.org/publicdomain/zero/1.0/",
    },
    "MIT": {"name": "The MIT License", "url": "https://mit-license.org/"},
}

DIBBS_CONTACT = {
    "name": "CDC Public Health Data Infrastructure",
    "url": "https://cdcgov.github.io/dibbs-site/",
    "email": "dibbs@cdc.gov",
}


def _get_env_variable(name: str) -> str:
    """
    Grabs a variable by name from the environment. Throws an error if the variable is not present.

    Args:
        name (str): Name of the environment variable

    Raises:
        OSError: raised if environment variable is not present

    Returns:
        str: Name of the environment variable
    """
    print(f"VAR: {name}")
    value = os.getenv(name)
    print(f"VAL: {value}")
    if value is None:
        raise OSError(f"Missing environment variable: {name}")
    return value


ENVIRONMENT: dict[str, str] = {
    "ENV": _get_env_variable("ENV"),
}

# Store a list of all the data fields/elements that are relevant
# This may not be maintainable - but for our purposes should suffice
# for now
DATA_FIELDS = ["lab_order", "lab_result", "lab_value", "lab_interp"]

# Putting this here for now to store rules for
# evaluating text, for specified data elements,
# to see if they are viable for TTC
# TODO: Does this work for us or is there something better?
DATA_FIELD_TEXT_RULES = {
    "lab_order": {
        "text_length": 2,  # anything that is greater than 2
        # putting this here for now, but we may not need/want this
        # but was thinking about it as I was storing the rules
        "x_paths": ["some path", "some other path"],  # store the X-Paths in order of importance
    },
    "lab_result": {
        "text_length": 2,  # anything that is greater than 2
        # putting this here for now, but we may not need/want this
        # but was thinking about it as I was storing the rules
        "x_paths": ["some path", "some other path"],  # store the X-Paths in order of importance
    },
    "lab_value": {},
    "lab_interp": {},
}
