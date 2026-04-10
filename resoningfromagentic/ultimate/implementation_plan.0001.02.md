# Implementation Plan - Fix Tender List 500 Error

The `/api/tenders` endpoint is currently returning a 500 Internal Server Error. This is likely due to a schema mismatch or an error in the mapping logic between the `Tender` model and the `TenderResponse` Pydantic schema, specifically regarding the newly added ingestion fields.

## Proposed Changes

### [Backend] [tenders.py](file:///d:/tender/tenderwriter/backend/app/api/tenders.py)

#### [MODIFY] [tenders.py](file:///d:/tender/tenderwriter/backend/app/api/tenders.py)
- Update `TenderResponse` to include `ingestion_progress: float | None = 0.0` to match the frontend expectations and provide consistency with the `DocumentResponse`.
- Refine `_tender_to_response` to calculate an aggregate progress value for the tender based on its documents.
- Add defensive checks to prevent mapping errors if metadata or relationships are partially missing.

## Verification Plan

### Automated Tests
- Call `GET /api/tenders?limit=100` via the browser or `curl` to verify a 200 OK response with the expected JSON structure.
- Verify that `ingestion_status` and `ingestion_progress` are correctly populated in the response.

### Manual Verification
- Check the Dashboard to ensure tenders are listed correctly and progress bars are visible for ongoing ingestions.
