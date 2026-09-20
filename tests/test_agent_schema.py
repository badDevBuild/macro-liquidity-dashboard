from __future__ import annotations

import json
import unittest
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def walk_schema(node: Any, path: str = "$") -> list[str]:
    """Return object-schema paths that are incompatible with strict outputs."""
    errors: list[str] = []
    if isinstance(node, dict):
        if "uniqueItems" in node:
            errors.append(f"{path}: uniqueItems is not supported by Codex outputs")
        if node.get("type") == "object":
            properties = node.get("properties", {})
            required = node.get("required")
            if not isinstance(required, list):
                errors.append(f"{path}: missing required array")
            elif set(required) != set(properties):
                missing = sorted(set(properties) - set(required))
                extra = sorted(set(required) - set(properties))
                errors.append(
                    f"{path}: required must match properties; missing={missing}, extra={extra}"
                )
            for name, property_schema in properties.items():
                if not isinstance(property_schema, dict) or not any(
                    key in property_schema
                    for key in ("type", "$ref", "anyOf", "oneOf", "allOf")
                ):
                    errors.append(f"{path}.properties.{name}: missing type or reference")
        for key, value in node.items():
            errors.extend(walk_schema(value, f"{path}.{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            errors.extend(walk_schema(value, f"{path}[{index}]"))
    return errors


class AgentSchemaTests(unittest.TestCase):
    def test_schema_is_compatible_with_codex_strict_structured_output(self) -> None:
        schema = json.loads(
            (PROJECT_ROOT / "config" / "agent-analysis.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(walk_schema(schema), [])


if __name__ == "__main__":
    unittest.main()
