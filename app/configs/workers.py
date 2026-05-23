from app.parsers import Parser, WorkerKind


ignored_parser_types: set[Parser] = set()


def _filter_by_worker_type(worker_kind: WorkerKind, ignore: set[Parser]) -> list[str]:
    return [
        parser.value.id
        for parser in Parser
        if parser.value.worker_kind == worker_kind and parser not in ignore
    ]


light_parsers = _filter_by_worker_type(WorkerKind.LIGHT, ignored_parser_types)
heavy_parsers = _filter_by_worker_type(WorkerKind.HEAVY, ignored_parser_types)
