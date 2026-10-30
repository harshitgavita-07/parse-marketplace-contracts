import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from parse_contracts.exporters import mcp_tools, openapi_document, python_client_source, safe_name
from parse_contracts.model import input_schema, parameter_schema, response_schema, schema_from_sample, validate_input_values
from parse_contracts.verify import diff_details, evaluate_assertion, evaluate_verification, get_path, validate_detail


def endpoint(name="search_articles", method="GET"):
    return {
        "method": method,
        "endpoint_name": name,
        "description": "Search articles",
        "input_params": {
            "query": {"type": "string", "required": True, "description": "Search text", "domain": {"kind": "open", "example": "ai"}},
            "limit": {"type": "integer", "required": False, "default": 10, "domain": {"kind": "enum", "values": [5, 10, 20]}},
            "mode": {"type": "string", "required": False, "default": "fast", "domain": {"kind": "enum", "values": ["fast", "full"]}},
        },
        "return_schema": {"type": "object", "sample": {"status": "success", "data": {"articles": [{"title": "AI", "pageid": 1}], "total_hits": 1}}},
        "verification": {"assertions": [{"path": "$.status", "op": "equals", "value": "success"}, {"path": "$.data.articles", "op": "array_min_len", "value": 1}, {"path": "$.data.articles[0].title", "op": "not_null"}]},
        "initiates_session": False,
        "price": 1,
    }


def detail():
    return {
        "id": "4e241d54-c859-4aec-846d-5ea3159104c7",
        "slug": "wikipedia-api",
        "name": "Wikipedia API",
        "description": "Public Wikipedia API",
        "source_url": "https://www.wikipedia.org",
        "canonical_scraper_id": "cabed3f6-f0a2-4ce6-ab14-897da89a04db",
        "latest_version": 9,
        "last_verified_at": "2026-10-29T15:47:46.369223+00:00",
        "sdk_delivery_state": "absent",
        "primary_category": "reference",
        "apis": [endpoint()],
        "sample_inputs": {"search_articles": {"query": "artificial intelligence", "limit": "10", "mode": "fast"}},
        "endpoint_health": [{"endpoint_name": "search_articles", "status": "healthy"}],
    }


class SchemaTests(unittest.TestCase):
    def test_parameter_maps_string(self):
        self.assertEqual(parameter_schema("q", {"type": "string"})["type"], "string")

    def test_parameter_maps_integer(self):
        self.assertEqual(parameter_schema("n", {"type": "int"})["type"], "integer")

    def test_parameter_maps_boolean(self):
        self.assertEqual(parameter_schema("ok", {"type": "bool"})["type"], "boolean")

    def test_unknown_type_falls_back_string(self):
        self.assertEqual(parameter_schema("x", {"type": "mystery"})["type"], "string")

    def test_enum_is_exported(self):
        schema = parameter_schema("mode", {"type": "string", "domain": {"values": ["a", "b"]}})
        self.assertEqual(schema["enum"], ["a", "b"])

    def test_pattern_is_exported(self):
        schema = parameter_schema("owner", {"type": "string", "domain": {"pattern": "[a-z]+"}})
        self.assertEqual(schema["pattern"], "[a-z]+")

    def test_input_schema_required(self):
        self.assertEqual(input_schema(endpoint())["required"], ["query"])

    def test_input_schema_rejects_unknown(self):
        errors = validate_input_values(endpoint(), {"query": "ai", "extra": "x"})
        self.assertTrue(any("additional property" in e for e in errors))

    def test_input_schema_accepts_string_integer(self):
        self.assertEqual(validate_input_values(endpoint(), {"query": "ai", "limit": "10"}), [])

    def test_input_schema_rejects_bad_integer(self):
        errors = validate_input_values(endpoint(), {"query": "ai", "limit": "ten"})
        self.assertTrue(any("expected integer" in e for e in errors))

    def test_input_schema_rejects_bad_enum(self):
        errors = validate_input_values(endpoint(), {"query": "ai", "mode": "slow"})
        self.assertTrue(any("not one of" in e for e in errors))

    def test_sample_object_schema(self):
        schema = schema_from_sample({"a": 1, "b": ["x"]})
        self.assertEqual(schema["properties"]["a"]["type"], "integer")
        self.assertEqual(schema["properties"]["b"]["items"]["type"], "string")

    def test_response_schema_uses_sample(self):
        schema = response_schema(endpoint())
        self.assertIn("status", schema["properties"])
        self.assertIn("data", schema["properties"])


class VerificationTests(unittest.TestCase):
    def test_get_path_nested(self):
        found, value = get_path({"data": {"items": [{"title": "x"}]}}, "$.data.items[0].title")
        self.assertTrue(found)
        self.assertEqual(value, "x")

    def test_get_path_missing(self):
        found, _ = get_path({"data": {}}, "$.data.missing")
        self.assertFalse(found)

    def test_equals_passes(self):
        ok, _ = evaluate_assertion({"status": "success"}, {"path": "$.status", "op": "equals", "value": "success"})
        self.assertTrue(ok)

    def test_equals_fails(self):
        ok, _ = evaluate_assertion({"status": "failed"}, {"path": "$.status", "op": "equals", "value": "success"})
        self.assertFalse(ok)

    def test_not_null_passes(self):
        ok, _ = evaluate_assertion({"x": 0}, {"path": "$.x", "op": "not_null"})
        self.assertTrue(ok)

    def test_not_null_fails_on_null(self):
        ok, _ = evaluate_assertion({"x": None}, {"path": "$.x", "op": "not_null"})
        self.assertFalse(ok)

    def test_array_min_len_passes(self):
        ok, _ = evaluate_assertion({"x": [1, 2]}, {"path": "$.x", "op": "array_min_len", "value": 2})
        self.assertTrue(ok)

    def test_array_min_len_fails(self):
        ok, _ = evaluate_assertion({"x": [1]}, {"path": "$.x", "op": "array_min_len", "value": 2})
        self.assertFalse(ok)

    def test_unsupported_op_fails_safely(self):
        ok, detail = evaluate_assertion({}, {"path": "$.x", "op": "regex", "value": "x"})
        self.assertFalse(ok)
        self.assertIn("unsupported", detail)

    def test_evaluate_verification_uses_sample(self):
        results = evaluate_verification(endpoint())
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r["ok"] for r in results))

    def test_validate_detail_passes(self):
        report = validate_detail(detail())
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["endpoint_count"], 1)

    def test_validate_detail_catches_duplicate(self):
        d = detail()
        d["apis"].append(endpoint())
        self.assertFalse(validate_detail(d)["ok"])

    def test_validate_detail_catches_missing_canonical(self):
        d = detail()
        d["canonical_scraper_id"] = None
        self.assertFalse(validate_detail(d)["ok"])

    def test_validate_detail_catches_bad_method(self):
        d = detail()
        d["apis"][0]["method"] = "DELETE"
        self.assertFalse(validate_detail(d)["ok"])

    def test_validate_detail_warns_sdk_gap(self):
        report = validate_detail(detail())
        self.assertTrue(any("sdk_delivery_state" in w for w in report["warnings"]))

    def test_validate_detail_catches_sample_error(self):
        d = detail()
        d["sample_inputs"]["search_articles"]["limit"] = "bad"
        self.assertFalse(validate_detail(d)["ok"])


class ExportTests(unittest.TestCase):
    def test_safe_name(self):
        self.assertEqual(safe_name("Get Articles!"), "get_articles")

    def test_safe_name_keyword(self):
        self.assertEqual(safe_name("class"), "class_")

    def test_openapi_version(self):
        self.assertEqual(openapi_document(detail())["openapi"], "3.1.0")

    def test_openapi_path(self):
        doc = openapi_document(detail())
        self.assertIn("/scraper/{scraper_id}/search_articles", doc["paths"])

    def test_openapi_get_parameters(self):
        op = openapi_document(detail())["paths"]["/scraper/{scraper_id}/search_articles"]["get"]
        names = [p["name"] for p in op["parameters"]]
        self.assertEqual(names, ["scraper_id", "query", "limit", "mode"])

    def test_openapi_post_body(self):
        d = detail()
        d["apis"][0] = endpoint("create_item", "POST")
        op = openapi_document(d)["paths"]["/scraper/{scraper_id}/create_item"]["post"]
        self.assertIn("requestBody", op)

    def test_openapi_security(self):
        doc = openapi_document(detail())
        self.assertEqual(doc["components"]["securitySchemes"]["ApiKeyAuth"]["name"], "X-API-Key")

    def test_openapi_marks_generated(self):
        desc = openapi_document(detail())["info"]["description"]
        self.assertIn("not an official Parse export", desc)

    def test_mcp_tool_count(self):
        self.assertEqual(len(mcp_tools(detail())["tools"]), 1)

    def test_mcp_tool_name(self):
        self.assertEqual(mcp_tools(detail())["tools"][0]["name"], "wikipedia_api__search_articles")

    def test_mcp_execute_url(self):
        tool = mcp_tools(detail())["tools"][0]
        self.assertIn("cabed3f6", tool["x-execute"]["url"])

    def test_python_client_compiles(self):
        source = python_client_source(detail())
        compile(source, "generated_client.py", "exec")
        self.assertIn("def search_articles", source)
        self.assertIn("X-API-Key", source)

    def test_python_client_uses_canonical(self):
        self.assertIn("cabed3f6-f0a2", python_client_source(detail()))


class DiffTests(unittest.TestCase):
    def test_diff_no_changes(self):
        result = diff_details(detail(), detail())
        self.assertEqual(result["added_endpoints"], [])
        self.assertEqual(result["removed_endpoints"], [])
        self.assertEqual(result["changed_endpoints"], [])

    def test_diff_added_endpoint(self):
        before = detail()
        after = copy.deepcopy(detail())
        after["apis"].append(endpoint("get_article", "GET"))
        self.assertEqual(diff_details(before, after)["added_endpoints"], ["get_article"])

    def test_diff_removed_endpoint(self):
        before = detail()
        after = copy.deepcopy(detail())
        after["apis"] = []
        self.assertEqual(diff_details(before, after)["removed_endpoints"], ["search_articles"])

    def test_diff_changed_input(self):
        before = detail()
        after = copy.deepcopy(detail())
        after["apis"][0]["input_params"]["limit"]["default"] = 20
        changed = diff_details(before, after)["changed_endpoints"]
        self.assertEqual(changed[0]["endpoint_name"], "search_articles")
        self.assertIn("input_params", changed[0]["changes"])

    def test_diff_version(self):
        after = copy.deepcopy(detail())
        after["latest_version"] = 10
        self.assertEqual(diff_details(detail(), after)["version"], {"before": 9, "after": 10})


class CLITests(unittest.TestCase):
    def test_validate_cli(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "detail.json"
            path.write_text(json.dumps(detail()))
            proc = subprocess.run([sys.executable, "-m", "parse_contracts.cli", "validate", str(path)], cwd=Path(__file__).parents[1], text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertIn('"ok": true', proc.stdout)

    def test_export_cli_writes_four_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "detail.json"
            out = Path(td) / "out"
            source.write_text(json.dumps(detail()))
            proc = subprocess.run([sys.executable, "-m", "parse_contracts.cli", "export", "unused", "--input", str(source), "--output-dir", str(out)], cwd=Path(__file__).parents[1], text=True, capture_output=True)
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            for name in ["openapi.json", "mcp-tools.json", "contract-report.json", "parse_client.py", "source-detail.snapshot.json"]:
                self.assertTrue((out / name).exists(), name)


if __name__ == "__main__":
    unittest.main()
