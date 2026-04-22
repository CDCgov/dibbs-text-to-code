from os import getenv


def get_env_variable(name: str) -> str:
    """Grabs a variable by name from the environment. Throws an error if the variable is not present.

    Args:
        name (str): Name of the environment variable

    Raises:
        OSError: raised if environment variable is not present

    Returns:
        str: Name of the environment variable
    """
    value = getenv(name)
    if value is None:
        raise OSError(f"Missing environment variable: {name}")
    return value
