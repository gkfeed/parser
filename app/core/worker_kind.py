from enum import StrEnum


class WorkerKind(StrEnum):
    LIGHT = "light"
    HTTP = "http"
    BROWSER = "browser"
