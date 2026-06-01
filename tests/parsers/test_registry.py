from app.extensions.parsers.selenium import SeleniumParserExtension
from app.parsers import Parser, WorkerKind


def test_selenium_parsers_use_heavy_workers():
    for parser in Parser:
        if issubclass(parser.value.handler, SeleniumParserExtension):
            assert parser.value.worker_kind == WorkerKind.HEAVY
