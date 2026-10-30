from __future__ import annotations

import re
from typing import Any, Iterable

JSON_TYPE_MAP = {
    "string": "string",
    "str": "string",
    "integer": "integer",
    "int": "integer",
    "number": "number",
    "float": "number",
    "boolean": "boolean",
    "bool": "boolean",
    "array": "array",
    "list": "array",
    "object": "object",
    "dict": "object",
}


def endpoint_names(detail: dict[str, Any]) -> list[str]:
    return [str(api.get("endpoint_name", "")) for api in detail.get("apis", [])]


def parameter_schema(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    raw_type = str(spec.get("type") or "string").lower()
    json_type = JSON_TYPE_MAP.get(raw_type, "string")
    schema: dict[str, Any] = {"type": json_type}
    if spec.get("description"):
        schema["description"] = str(spec["description"])
    if "default" in spec:
        schema["default"] = spec["default"]
    domain = spec.get("domain") or {}
    values = domain.get("values")
    if isinstance(values, list) and values:
        schema["enum"] = values
    pattern = domain.get("pattern") or spec.get("pattern")
    if pattern:
        schema["pattern"] = str(pattern)
    example = domain.get("example", spec.get("example"))
    if example is not None:
        schema["example"] = example
    return schema


def input_schema(endpoint: dict[str, Any]) -> dict[str, Any]:
    params = endpoint.get("input_params") or {}
    required = sorted(name for name, spec in params.items() if isinstance(spec, dict) and spec.get("required") is True)
    return {
        "type": "object",
        "properties": {name: parameter_schema(name, spec) for name, spec in params.items() if isinstance(spec, dict)},
        "required": required,
        "additionalProperties": False,
    }


def schema_from_sample(value: Any) -> dict[str, Any]:
    if value is None:
        return {"nullable": True}
    if isinstance(value, bool):
        return {"type": "boolean"}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"type": "integer"}
    if isinstance(value, float):
        return {"type": "number"}
    if isinstance(value, str):
        return {"type": "string"}
    if isinstance(value, list):
        schema: dict[str, Any] = {"type": "array", "items": {}}
        if value:
            schema["items"] = merge_schemas([schema_from_sample(item) for item in value])
        return schema
    if isinstance(value, dict):
        return {
            "type": "object",
            "properties": {str(k): schema_from_sample(v) for k, v in value.items()},
            "required": sorted(str(k) for k, v in value.items() if v is not None),
            "additionalProperties": True,
        }
    return {}


def merge_schemas(schemas: Iterable[dict[str, Any]]) -> dict[str, Any]:
    schemas = list(schemas)
    if not schemas:
        return {}
    first = schemas[0]
    if all(s == first for s in schemas):
        return first
    types = {s.get("type") for s in schemas if s.get("type")}
    if len(types) == 1:
        t = types.pop()
        if t == "object":
            props: dict[str, Any] = {}
            required_sets = []
            for schema in schemas:
                props.update(schema.get("properties") or {})
                required_sets.append(set(schema.get("required") or []))
            required = sorted(set.intersection(*required_sets)) if required_sets else []
            return {"type": "object", "properties": props, "required": required, "additionalProperties": True}
        if t == "array":
            return {"type": "array", "items": merge_schemas([s.get("items") or {} for s in schemas])}
        return {"type": t}
    return {"anyOf": schemas}


def response_schema(endpoint: dict[str, Any]) -> dict[str, Any]:
    returned = endpoint.get("return_schema") or {}
    sample = returned.get("sample")
    if sample is not None:
        return schema_from_sample(sample)
    fields = returned.get("fields")
    if isinstance(fields, dict):
        props = {}
        for key, description in fields.items():
            text = str(description).lower()
            if "integer" in text or "number" in text:
                typ = "integer"
            elif "array" in text or "list" in text:
                typ = "array"
            elif "boolean" in text:
                typ = "boolean"
            else:
                typ = "string"
            prop: dict[str, Any] = {"type": typ, "description": str(description)}
            if typ == "array":
                prop["items"] = {}
            props[str(key)] = prop
        return {"type": "object", "properties": props, "additionalProperties": True}
    return {"type": "object", "additionalProperties": True}


def coerce_value(value: Any, expected_type: str) -> Any:
    if value is None:
        return None
    if expected_type == "integer" and isinstance(value, str) and re.fullmatch(r"[-+]?\d+", value):
        return int(value)
    if expected_type == "number" and isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return value
    if expected_type == "boolean" and isinstance(value, str) and value.lower() in {"true", "false"}:
        return value.lower() == "true"
    return value


def validate_instance(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    if not schema:
        return errors
    if value is None:
        if schema.get("nullable") or schema.get("default") is None and not schema.get("type"):
            return errors
        if schema.get("nullable"):
            return errors
        errors.append(f"{path}: null is not allowed")
        return errors
    expected = schema.get("type")
    if expected:
        type_ok = {
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "array": isinstance(value, list),
            "object": isinstance(value, dict),
        }.get(str(expected), True)
        if not type_ok:
            errors.append(f"{path}: expected {expected}, got {type(value).__name__}")
            return errors
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']!r}")
    if "pattern" in schema and isinstance(value, str) and not re.fullmatch(str(schema["pattern"]), value):
        errors.append(f"{path}: {value!r} does not match {schema['pattern']!r}")
    if isinstance(value, dict):
        props = schema.get("properties") or {}
        for req in schema.get("required") or []:
            if req not in value:
                errors.append(f"{path}.{req}: required property is missing")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in props:
                    errors.append(f"{path}.{key}: additional property is not allowed")
        for key, child in value.items():
            if key in props:
                errors.extend(validate_instance(child, props[key], f"{path}.{key}"))
    if isinstance(value, list) and "items" in schema:
        for index, child in enumerate(value):
            errors.extend(validate_instance(child, schema.get("items") or {}, f"{path}[{index}]"))
    return errors


def validate_input_values(endpoint: dict[str, Any], values: dict[str, Any]) -> list[str]:
    schema = input_schema(endpoint)
    coerced: dict[str, Any] = {}
    props = schema.get("properties") or {}
    errors: list[str] = []
    for key, value in values.items():
        if key not in props:
            errors.append(f"$.{key}: additional property is not allowed")
            continue
        coerced[key] = coerce_value(value, str(props[key].get("type") or "string"))
    return errors + validate_instance(coerced, schema)
