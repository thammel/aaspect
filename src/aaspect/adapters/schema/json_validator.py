import json
import re
from typing import Any

import jsonschema_rs

from aaspect.adapters.schema.violations import violation
from aaspect.domain.schema_check import SchemaViolation

# The official schemas match characters outside the BMP as UTF-16 surrogate pairs.
# jsonschema-rs refuses to compile that, and a pure-Python validator compiles it but then
# rejects every emoji. The code-point range means the same and works everywhere.
_SURROGATE_PAIRS = r"\ud800[\udc00-\udfff]|[\ud801-\udbfe][\udc00-\udfff]|\udbff[\udc00-\udfff]"
_SUPPLEMENTARY_PLANES = "[\U00010000-\U0010ffff]"
_SURROGATE_ESCAPE = re.compile(r"\\u[dD][89a-fA-F][0-9a-fA-F]{2}")


class JsonSchemaValidator:
    def __init__(self, schema: dict[str, Any]) -> None:
        self._validator = jsonschema_rs.validator_for(_rewrite_patterns(schema))

    def validate(self, content: bytes) -> list[SchemaViolation]:
        try:
            instance = json.loads(content.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
            return [violation("well-formedness", "", "", f"Not well-formed JSON: {error}")]
        try:
            return [_from_error(error) for error in self._validator.iter_errors(instance)]
        except UnicodeEncodeError:
            # "\ud800" is legal JSON, but jsonschema-rs cannot take a lone surrogate.
            message = "Contains a lone UTF-16 surrogate, which is not a valid Unicode character"
            return [violation("lone-surrogate", "", "", message)]


def _rewrite_patterns(node: Any) -> Any:
    if isinstance(node, dict):
        return {
            key: _rewrite_pattern(value) if key == "pattern" else _rewrite_patterns(value)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_rewrite_patterns(item) for item in node]
    return node


def _rewrite_pattern(pattern: str) -> str:
    rewritten = pattern.replace(_SURROGATE_PAIRS, _SUPPLEMENTARY_PLANES)
    if _SURROGATE_ESCAPE.search(rewritten):
        raise ValueError(f"schema pattern uses an unknown surrogate form: {pattern}")
    return rewritten


def _from_error(error: jsonschema_rs.ValidationError) -> SchemaViolation:
    keyword = error.schema_path[-1] if error.schema_path else type(error.kind).__name__
    return violation(
        keyword=str(keyword),
        schema_path=_pointer(error.schema_path),
        instance_path=_pointer(error.instance_path),
        message=error.message,
    )


def _pointer(path: list[str | int]) -> str:
    return "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in path)
