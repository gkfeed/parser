from app.core.worker_kind import WorkerKind
from app.parsers import Parser

ignored_parser_types: set[Parser] = {
    Parser.X,
    Parser.MATRESHKA,  # The site has closed.
}


def _filter_by_worker_type(worker_kind: WorkerKind, ignore: set[Parser]) -> list[str]:
    return [
        parser.value.id
        for parser in Parser
        if parser.value.worker_kind == worker_kind and parser not in ignore
    ]


light_parsers = _filter_by_worker_type(WorkerKind.LIGHT, ignored_parser_types)
http_parsers = _filter_by_worker_type(WorkerKind.HTTP, ignored_parser_types)
browser_parsers = _filter_by_worker_type(WorkerKind.BROWSER, ignored_parser_types)
