# API Contract v1

This document freezes the Sprint 1 HTTP contract for `tw-kpi-reason-engine`.

## Base Rules

- All timestamps are UTC.
- `external_tender_id` is the stable cross-service identifier.
- Endpoint names and top-level payload shapes are frozen in Sprint 1.
- All ingestion endpoints are asynchronous and return `202 Accepted`.
- Query endpoints are live in Sprint 1 but return `status = "not_ready"` placeholders until scoring is implemented.

## Endpoints

| Method | Path | Intent | Sprint 1 behavior |
| --- | --- | --- | --- |
| `GET` | `/health` | Liveness and version probe | Returns service name, version, and `healthy` status |
| `POST` | `/v1/tenders` | Sync canonical tender context | Returns `202 Accepted` |
| `POST` | `/v1/tenders/{external_tender_id}/events` | Ingest canonical domain events | Returns `202 Accepted` |
| `POST` | `/v1/tenders/{external_tender_id}/documents/context` | Ingest document context for future analysis | Returns `202 Accepted` |
| `POST` | `/v1/tenders/{external_tender_id}/analysis-jobs` | Request asynchronous recomputation | Returns `202 Accepted` |
| `GET` | `/v1/tenders/{external_tender_id}/snapshot` | Retrieve tender KPI snapshot | Returns placeholder response with `status = "not_ready"` |
| `GET` | `/v1/tenders/{external_tender_id}/diagnostics` | Retrieve diagnostics and explanations | Returns placeholder response with `status = "not_ready"` |
| `GET` | `/v1/tenders/{external_tender_id}/transitions` | Retrieve analytical state transitions | Returns placeholder response with `status = "not_ready"` |
| `GET` | `/v1/tenders/{external_tender_id}/forecast` | Retrieve forecast scenarios | Returns placeholder response with `status = "not_ready"` |
| `GET` | `/v1/admin/portfolio/overview` | Retrieve portfolio overview for admin UI | Returns placeholder response with `status = "not_ready"` |
| `GET` | `/v1/admin/portfolio/bottlenecks` | Retrieve admin bottleneck list | Returns placeholder response with `status = "not_ready"` |

## Compatibility Rules

- New optional fields can be added in future sprints without changing the frozen route names.
- Existing required fields must remain backward compatible for `tw-backend`.
- Query contracts may gain richer content, but `status`, identifiers, and response object names remain stable.
- Authentication and service-to-service authorization will be hardened in follow-up sprints without renaming the routes.
