from aaspect.domain.schema_check import SchemaViolation

# Messages and paths quote uploaded content, which can be arbitrarily long.
_MAX_LENGTH = 300


def violation(keyword: str, schema_path: str, instance_path: str, message: str) -> SchemaViolation:
    return SchemaViolation(
        keyword=keyword,
        schema_path=_truncate(schema_path),
        instance_path=_truncate(instance_path),
        message=_truncate(message),
    )


def _truncate(text: str) -> str:
    return text if len(text) <= _MAX_LENGTH else text[: _MAX_LENGTH - 1] + "…"
