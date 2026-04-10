import os


def get_env_var(key: str) -> str:
    """Grabs a variable by key from the environment. Throws an error if the variable is not present.

    Args:
        key (str): key of the environment variable

    Raises:
        OSError: raised if environment variable is not present

    Returns:
        str: key of the environment variable
    """
    value = os.getenv(key)
    if value is None:
        raise OSError(f"Missing environment variable: {key}")
    return value
