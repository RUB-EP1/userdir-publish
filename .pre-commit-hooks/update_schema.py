"""Generate the JSON Schema for the ``[tool.userdir-publish]`` TOML table.

Run this script to update the committed schema file. It only rewrites the file when its
content changes, so that Prettier can own the formatting.
"""

from __future__ import annotations

import ast
import inspect
import itertools
import json
import textwrap
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

from userdir_publish.config import TOOL_NAME, Settings

SCHEMA_PATH = Path(f"{TOOL_NAME}.schema.json")


def main() -> int:
    """Write the schema if it is outdated and return 1, so that the hook fails."""
    if schema_is_current():
        return 0
    SCHEMA_PATH.write_text(render_schema())
    return 1


def schema_is_current() -> bool:
    """Check whether the committed schema is semantically up to date.

    >>> schema_is_current()
    True
    """
    try:
        committed = json.loads(SCHEMA_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    return committed == create_schema()


def create_schema() -> dict[str, Any]:
    r"""Project the `.Settings` dataclass onto ``[tool.userdir-publish]``.

    The defaults and examples in the schema form a valid configuration:

    >>> import tempfile
    >>> from userdir_publish.config import load_settings
    >>> lines = [f"[tool.{TOOL_NAME}]"]
    >>> for key, field_schema in create_schema()["properties"].items():
    ...     value = field_schema.get("default", field_schema.get("examples", [None])[0])
    ...     if isinstance(value, str):
    ...         lines.append(f'{key} = "{value}"')
    >>> with tempfile.TemporaryDirectory() as tmp:
    ...     root = Path(tmp)
    ...     _ = (root / "pyproject.toml").write_text("\n".join(lines))
    ...     settings = load_settings(project_root=root, user_config=root / "none")
    >>> settings.host
    'web.example.edu'
    """
    descriptions = _get_attribute_docstrings(Settings)
    type_hints = get_type_hints(Settings)
    properties: dict[str, Any] = {}
    for settings_field in fields(Settings):
        if settings_field.name.startswith("_"):
            continue
        field_schema = {
            "description": descriptions[settings_field.name],
            **_to_json_type(
                annotation=type_hints[settings_field.name],
                pattern=settings_field.metadata.get("pattern"),
            ),
        }
        if settings_field.default not in {MISSING, None}:
            default = settings_field.default
            field_schema["default"] = (
                list(default) if isinstance(default, tuple) else default
            )
        if "examples" in settings_field.metadata:
            field_schema["examples"] = settings_field.metadata["examples"]
        properties[settings_field.name.replace("_", "-")] = field_schema
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"{TOOL_NAME} configuration",
        "description": f"Configuration for the tool.{TOOL_NAME} TOML table.",
        "type": "object",
        "x-tombi-table-keys-order": "ascending",
        "properties": dict(sorted(properties.items())),
        "additionalProperties": False,
    }


def render_schema() -> str:
    """Render the generated schema in its committed representation."""
    return json.dumps(create_schema(), indent=2) + "\n"


def _to_json_type(annotation: Any, pattern: str | None = None) -> dict[str, Any]:
    """Convert a type annotation of a `.Settings` field to a JSON Schema type.

    A *pattern* constrains the plain strings that the annotation accepts.

    >>> _to_json_type(str | None)
    {'type': 'string'}
    >>> _to_json_type(tuple[str, ...])
    {'type': 'array', 'items': {'type': 'string'}}
    >>> from typing import Literal
    >>> _to_json_type(Literal["a", "b"] | str, pattern="^c+$")
    {'anyOf': [{'enum': ['a', 'b']}, {'type': 'string', 'pattern': '^c+$'}]}
    """
    args = [arg for arg in get_args(annotation) if arg is not type(None)]
    origin = get_origin(annotation)
    if annotation is str:
        if pattern is None:
            return {"type": "string"}
        return {"type": "string", "pattern": pattern}
    if origin is tuple:
        return {"type": "array", "items": _to_json_type(args[0])}
    if repr(origin) == "typing.Literal":
        return {"enum": list(args)}
    if len(args) == 1:
        return _to_json_type(args[0], pattern)
    if len(args) > 1:
        return {"anyOf": [_to_json_type(arg, pattern) for arg in args]}
    msg = f"Cannot convert {annotation} to a JSON Schema type"
    raise NotImplementedError(msg)


def _get_attribute_docstrings(cls: type) -> dict[str, str]:
    """Collect the docstrings that follow the attribute definitions of a class."""
    module = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    body = module.body[0].body  # ty: ignore[unresolved-attribute]
    docstrings: dict[str, str] = {}
    for node, next_node in itertools.pairwise(body):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and isinstance(next_node, ast.Expr)
            and isinstance(next_node.value, ast.Constant)
            and isinstance(next_node.value.value, str)
        ):
            docstrings[node.target.id] = inspect.cleandoc(next_node.value.value)
    return docstrings


if __name__ == "__main__":
    raise SystemExit(main())
