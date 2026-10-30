from __future__ import annotations

import argparse
import json
import pathlib
import sys

from .client import MarketplaceClient
from .exporters import mcp_tools, openapi_document, python_client_source
from .verify import diff_details, validate_detail


def load_json(path: str) -> dict:
    return json.loads(pathlib.Path(path).read_text())


def write_json(path: pathlib.Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def cmd_search(args) -> int:
    data = MarketplaceClient(args.base_url).search(q=args.query, limit=args.limit, offset=args.offset, sort=args.sort, semantic=not args.no_semantic)
    print(json.dumps(data, indent=2, ensure_ascii=False))
    return 0


def cmd_snapshot(args) -> int:
    data = MarketplaceClient(args.base_url).detail(args.listing_id)
    write_json(pathlib.Path(args.output), data)
    return 0


def cmd_export(args) -> int:
    detail = MarketplaceClient(args.base_url).detail(args.listing_id) if args.live else load_json(args.input)
    out = pathlib.Path(args.output_dir)
    report = validate_detail(detail)
    write_json(out / "openapi.json", openapi_document(detail))
    write_json(out / "mcp-tools.json", mcp_tools(detail))
    write_json(out / "contract-report.json", report)
    write_json(out / "source-detail.snapshot.json", detail)
    (out / "parse_client.py").write_text(python_client_source(detail))
    if args.probe_auth and detail.get("canonical_scraper_id"):
        report["unauthenticated_openapi_status"] = MarketplaceClient(args.base_url).probe_openapi_auth(detail["canonical_scraper_id"])
        write_json(out / "contract-report.json", report)
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 2


def cmd_validate(args) -> int:
    report = validate_detail(load_json(args.input))
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 2


def cmd_diff(args) -> int:
    result = diff_details(load_json(args.before), load_json(args.after))
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="parse-contracts", description="Generate contracts and SDKs from public Parse Marketplace listings.")
    parser.add_argument("--base-url", default="https://api.parse.bot")
    sub = parser.add_subparsers(required=True)
    p = sub.add_parser("search")
    p.add_argument("--query")
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--sort", default="top")
    p.add_argument("--no-semantic", action="store_true")
    p.set_defaults(func=cmd_search)
    p = sub.add_parser("snapshot")
    p.add_argument("listing_id")
    p.add_argument("--output", required=True)
    p.set_defaults(func=cmd_snapshot)
    p = sub.add_parser("export")
    p.add_argument("listing_id")
    p.add_argument("--live", action="store_true")
    p.add_argument("--input", default="examples/wikipedia-detail.snapshot.json")
    p.add_argument("--output-dir", required=True)
    p.add_argument("--probe-auth", action="store_true")
    p.set_defaults(func=cmd_export)
    p = sub.add_parser("validate")
    p.add_argument("input")
    p.set_defaults(func=cmd_validate)
    p = sub.add_parser("diff")
    p.add_argument("before")
    p.add_argument("after")
    p.set_defaults(func=cmd_diff)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
