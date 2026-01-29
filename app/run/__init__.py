from app.parsers import PARSERS

light_parsers = [
    "yt",
    "tiktok",
    "web",
    "kinogo",
    "twitch",
    "vk",
    "hltv",
    "liquidpedia",
    "shiki",
    "pornhub",
]

heavy_parsers = [parser for parser in PARSERS if parser not in light_parsers]
