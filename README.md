# Parse Marketplace Contracts

Generate an OpenAPI 3.1 document, MCP tool definitions, a contract report, and a Python SDK from Parse's **public no-auth Marketplace detail API**.

This is a pre-signup evaluation bridge. It is not an official Parse SDK, not a patch to Parse, and not a claim that the hosted product is broken.

## The product gap

Parse's Marketplace is publicly discoverable. Its docs say marketplace search and detail need no authentication, and the product site positions the catalog as a way to discover and fork thousands of ready APIs.

While testing the live product on October 30, 2026:

- `GET /marketplace/apis?q=wikipedia` returned public listings without an API key.
- `GET /marketplace/apis/4e241d54-c859-4aec-846d-5ea3159104c7` returned the full Wikipedia listing, endpoint parameters, sample inputs, verification assertions, health, `canonical_scraper_id`, and `sdk_delivery_state: "absent"` without an API key.
- `GET /v1/apis/{canonical_scraper_id}/openapi.json` returned `401 Missing X-API-Key` without a key.
- Executing the canonical endpoint also requires a key, as documented.

That leaves a concrete evaluation gap: a developer can inspect a public listing, but cannot take the same public contract into standard OpenAPI/MCP/SDK tooling before creating an account. Parse already has authenticated OpenAPI export and SDK generation; this repo fills only the unauthenticated marketplace evaluation boundary.

## Live proof included

[`examples/wikipedia/`](examples/wikipedia/) was generated from the live public Wikipedia listing:

- Listing: `wikipedia-api`
- Canonical scraper: `cabed3f6-f0a2-4ce6-ab14-897da89a04db`
- Marketplace version: `9`
- Last verified by Parse: `2026-10-29T15:47:46.369223+00:00`
- Endpoints: `search_articles`, `get_article_details`, `get_category_members`
- Local contract report: 0 errors, 3 endpoints
- Measured unauthenticated official OpenAPI export status: `401`

Files generated:

- `openapi.json` - OpenAPI 3.1 compatibility contract
- `mcp-tools.json` - MCP tool definitions with input schemas
- `parse_client.py` - dependency-free Python client, ready for a caller's own API key
- `contract-report.json` - validation result and product-gap evidence
- `source-detail.snapshot.json` - public marketplace detail snapshot used for reproducibility

## Use

Python 3.10+, no runtime dependencies.

```sh
python -m unittest discover -s tests -v
python -m parse_contracts.cli search --query wikipedia --limit 5
python -m parse_contracts.cli snapshot 4e241d54-c859-4aec-846d-5ea3159104c7 --output /tmp/wiki.json
python -m parse_contracts.cli export 4e241d54-c859-4aec-846d-5ea3159104c7 --live --probe-auth --output-dir out/wikipedia
python -m parse_contracts.cli diff before.json after.json
```

The generated client needs the caller's own Parse API key. Keep it in an environment variable or secret manager; never commit it.

```python
import os

from out.wikipedia.parse_client import WikipediaApiClient

client = WikipediaApiClient(api_key=os.environ["PARSE_API_KEY"])
result = client.search_articles(query="artificial intelligence", limit=5)
```

## What is validated

The contract report checks:

- unique endpoint names
- supported GET/POST methods
- a present canonical scraper ID
- required parameters existing in properties
- marketplace sample inputs against the generated input schema
- string-to-integer and string-to-boolean coercion used by marketplace samples
- enum and pattern constraints
- Parse's own verification assertions against the bundled response sample
- health rows that do not match current endpoint names
- `sdk_delivery_state` values such as `absent` or `legacy`

The diff command reports added, removed, and changed endpoints, plus version and health changes between two public snapshots.

## Boundaries

- The generated OpenAPI is a compatibility contract inferred from public marketplace metadata and samples. Parse's authenticated export remains the source of truth when available.
- The response schema is inferred from sample data. It can be narrower or wider than every production response.
- The tool does not execute paid endpoints, create Parse jobs, scrape websites, bypass authentication, or use anyone else's API key.
- A `401` on unauthenticated export is expected behavior, not a vulnerability.
- The generated MCP file is tool metadata, not a running MCP server.
- Marketplace detail can change; regenerate and diff before relying on a contract.

## Sources checked

- Parse product: <https://parse.bot>
- Parse docs index: <https://docs.parse.bot/llms.txt>
- Marketplace search docs: <https://docs.parse.bot/api-reference/marketplace/search-and-browse-the-marketplace.md>
- Marketplace detail docs: <https://docs.parse.bot/api-reference/marketplace/get-a-marketplace-apis-detail.md>
- Authenticated OpenAPI export docs: <https://docs.parse.bot/api-reference/export/get-a-callable-apis-openapi-document.md>
- Execute endpoint docs: <https://docs.parse.bot/api-reference/execute/execute-an-api-endpoint-post.md>
- YC company page: <https://www.ycombinator.com/companies/parse-bot>

AI-assisted implementation and tests. Independently exercised against Parse's live public marketplace routes. Not affiliated with Parse.
