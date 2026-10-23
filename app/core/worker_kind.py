from enum import StrEnum


class WorkerKind(StrEnum):
    LIGHT = "light"
    HTTP = "http"
    BROWSER = "browser"

    # Keep consumers of the former browser worker name compatible.
    HEAVY = BROWSER
