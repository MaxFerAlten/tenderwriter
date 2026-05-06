# Implementation Plan - Debug and Fix Tender List Regression

The `/api/tenders` endpoint is failing with a 500 error, causing the Dashboard to appear empty. Since the logs don't show the traceback, we will add diagnostic logging and then fix the root cause.

## Proposed Changes

### [Backend] [tenders.py](file:///d:/tender/tenderwriter/backend/app/api/tenders.py)

#### [MODIFY] [tenders.py](file:///d:/tender/tenderwriter/backend/app/api/tenders.py)
- Wrap the mapping logic in `list_tenders` with a `try...except` block to log the exact exception and traceback.
- Add logging inside `_tender_to_response` to track which tender ID is being processed.
- Defensively cast `lifecycle_metadata` and other JSON fields to ensure they match the Pydantic schema.
- Ensure all Enum fields in the response are explicitly converted to strings via `.value`.

## Verification Plan

### Automated Tests
- Check `docker logs tw-backend` to see the newly added diagnostic output.
- Call `/api/tenders?limit=100` and verify it returns 200 OK.

### Manual Verification
- Verify the Dashboard loads the list of tenders successfully.
