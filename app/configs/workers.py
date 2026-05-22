from app.parsers import PARSERS


ignored_parser_types: list[str] = []

light_parser_types = [
    "yt",
    "tiktok",
    "web",
    "kinogo",
    "twitch",
    "hltv",
    "liquidpedia",
    "shiki",
    "pornhub",
    "porno365",
]


def _filter_parser_types(
    light_parser_types: list[str], ignored_parser_types: list[str]
) -> tuple[list[str], list[str]]:
    ignored = set(ignored_parser_types)
    light = [parser for parser in light_parser_types if parser not in ignored]
    heavy = [
        parser
        for parser in PARSERS
        if parser not in light_parser_types and parser not in ignored
    ]

    return light, heavy


light_parsers, heavy_parsers = _filter_parser_types(
    light_parser_types, ignored_parser_types
)
