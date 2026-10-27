from bs4 import Tag


def require_tag(value: object, field: str) -> Tag:
    """Require an HTML element and identify the field when it is missing."""
    if not isinstance(value, Tag):
        raise ValueError(f"Missing HTML tag for {field}")  # noqa: TRY004 - malformed page data, not caller misuse
    return value


def required_attr(tag: Tag, attribute: str, field: str) -> str:
    """Read a non-empty string attribute without normalizing its value."""
    value = tag.get(attribute)
    if value is None:
        raise ValueError(f"Missing {attribute!r} attribute for {field}")
    if not isinstance(value, str):
        raise ValueError(  # noqa: TRY004 - malformed page data, not caller misuse
            f"Invalid {attribute!r} attribute for {field}: expected a string"
        )
    if not value.strip():
        raise ValueError(f"Empty {attribute!r} attribute for {field}")
    return value


def required_text(tag: Tag, field: str, *, separator: str = "") -> str:
    """Read non-empty text, stripping each text node before joining it."""
    value = tag.get_text(separator, strip=True)
    if not value:
        raise ValueError(f"Empty text for {field}")
    return value
