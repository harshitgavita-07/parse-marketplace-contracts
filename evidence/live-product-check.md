# Live product check - October 30, 2026

All requests were unauthenticated, read-only marketplace or expected-auth probes. No endpoint execution was performed.

## Public discovery works

```sh
curl 'https://api.parse.bot/marketplace/apis?q=wikipedia&limit=8&semantic=true'
```

Returned HTTP 200 with `wikipedia-api`, listing id `4e241d54-c859-4aec-846d-5ea3159104c7`.

## Public detail exposes the contract inputs

```sh
curl 'https://api.parse.bot/marketplace/apis/4e241d54-c859-4aec-846d-5ea3159104c7'
```

Returned HTTP 200 with:

- `canonical_scraper_id`: `cabed3f6-f0a2-4ce6-ab14-897da89a04db`
- `latest_version`: `9`
- `last_verified_at`: `2026-10-29T15:47:46.369223+00:00`
- `sdk_delivery_state`: `absent`
- 3 endpoints with input schemas, sample inputs, response samples, verification assertions, prices, and health

## Official OpenAPI export still requires a key

```sh
curl -i 'https://api.parse.bot/v1/apis/cabed3f6-f0a2-4ce6-ab14-897da89a04db/openapi.json'
```

Returned HTTP 401:

```json
{"error":"Missing X-API-Key header","status_code":401}
```

## Canonical execution also requires a key

An earlier read-only probe against `/scraper/{canonical_scraper_id}/{endpoint}` returned HTTP 401 with the same missing-key error. This repo does not attempt to bypass that boundary.
