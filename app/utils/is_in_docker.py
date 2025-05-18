import os


def _running_in_docker():
    return os.path.exists("/.dockerenv")


IS_IN_DOCKER = _running_in_docker()
