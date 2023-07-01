import os


def getenv(key, default=None):
    # ENV variable not found in system AND no fallback value was provided
    if key not in os.environ and default is None:
        raise ValueError(f"Error: ENV variable <{key}> missing")

    val = os.environ.get(key, default)

    if str(val).lower() == "true":
        return True
    elif str(val).lower() == "false":
        return False
    else:
        return val
