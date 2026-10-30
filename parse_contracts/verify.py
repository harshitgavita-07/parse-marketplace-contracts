from __future__ import annotations

import re
from typing import Any

from .model import input_schema, response_schema, validate_input_values

_PATH_PART = re.compile(r"([^\.\[\]]+)|\[(\d+)\]")


def get_path(document: Any, path: str) -> tuple[bool, Any]:
    if not path.startswith("$"):
        return False, None
    current = document
    for name, index in _PATH_PART.findall(path[1:]):
        if name:
            if not isinstance(current, dict) or name not in current:
                return False, None
            current = current[name]
        elif index:
            i = int(index)
            if not isinstance(current, list) or i >= len(current):
                return False, None
            current = current[i]
    return True, current


def evaluate_assertion(document: Any, assertion: dict[str, Any]) -> tuple[bool, str]:
    path = str(assertion.get("path") or "")
    op = str(assertion.get("op") or "")
    expected = assertion.get("value")
    found, actual = get_path(document, path)
    if op == "not_null":
        ok = found and actual is not None
    elif op == "equals":
        ok = found and actual == expected
    elif op == "array_min_len":
        ok = found and isinstance(actual, list) and len(actual) >= int(expected)
    elif op == "exists":
        ok = found
    else:
        return False, f"unsupported assertion op {op!r} at {path}"
    return ok, f"{path} {op} {expected!r}: actual {actual!r}"


def evaluate_verification(endpoint: dict[str, Any]) -> list[dict[str, Any]]:
    sample = ((endpoint.get("return_schema") or {}).get("sample"))
    results = []
    assertions = ((endpoint.get("verification") or {}).get("assertions") or [])
    if sample is None:
        return [{"ok": False, "detail": "no response sample is present", "assertion": None}] if assertions else []
    for assertion in assertions:
        ok, detail = evaluate_assertion(sample, assertion)
        results.append({"ok": ok, "detail": detail, "assertion": assertion})
    return results


def validate_detail(detail: dict[str, Any], include_samples: bool = True) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []
    apis = detail.get("apis") or []
    names = [api.get("endpoint_name") for api in apis]
    if not detail.get("canonical_scraper_id"):
        errors.append("listing has no canonical_scraper_id")
    if len(names) != len(set(names)):
        errors.append("duplicate endpoint_name values")
    for api in apis:
        name = str(api.get("endpoint_name") or "<unnamed>")
        method = str(api.get("method") or "").upper()
        if method not in {"GET", "POST"}:
            errors.append(f"{name}: unsupported method {method!r}")
        schema = input_schema(api)
        required = set(schema.get("required") or [])
        props = set((schema.get("properties") or {}).keys())
        if not required <= props:
            errors.append(f"{name}: required parameters missing from properties")
        if include_samples:
            sample_inputs = ((detail.get("sample_inputs") or {}).get(name) or {})
            for err in validate_input_values(api, sample_inputs):
                errors.append(f"{name} sample_inputs: {err}")
            for result in evaluate_verification(api):
                if not result["ok"]:
                    errors.append(f"{name} verification sample: {result['detail']}")
        if response_schema(api) == {"type": "object", "additionalProperties": True}:
            warnings.append(f"{name}: response schema is generic")
    health_names = {row.get("endpoint_name") for row in detail.get("endpoint_health") or []}
    unknown_health = health_names - set(names)
    if unknown_health:
        warnings.append("health rows do not match current endpoints: " + ", ".join(sorted(map(str, unknown_health))))
    sdk_state = detail.get("sdk_delivery_state")
    if sdk_state in {"absent", "legacy", None}:
        warnings.append(f"sdk_delivery_state is {sdk_state!r}; generated SDK fills the public listing gap")
    if detail.get("last_verified_at"):
        info.append(f"last_verified_at={detail['last_verified_at']}")
    info.append(f"latest_version={detail.get('latest_version')}")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "info": info, "endpoint_count": len(apis)}


def diff_details(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    old_eps = {api.get("endpoint_name"): api for api in old.get("apis") or []}
    new_eps = {api.get("endpoint_name"): api for api in new.get("apis") or []}
    added = sorted(set(new_eps) - set(old_eps))
    removed = sorted(set(old_eps) - set(new_eps))
    changed = []
    for name in sorted(set(old_eps) & set(new_eps)):
        before = old_eps[name]
        after = new_eps[name]
        changes = {}
        for field in ["method", "description", "input_params", "return_schema", "price", "verification"]:
            if before.get(field) != after.get(field):
                changes[field] = {"before": before.get(field), "after": after.get(field)}
        if changes:
            changed.append({"endpoint_name": name, "changes": changes})
    return {
        "version": {"before": old.get("latest_version"), "after": new.get("latest_version")},
        "added_endpoints": added,
        "removed_endpoints": removed,
        "changed_endpoints": changed,
        "health_before": old.get("endpoint_health") or [],
        "health_after": new.get("endpoint_health") or [],
    }
