This directory will store backend Alembic revision files.

The scaffold exists on purpose before the runtime startup switch. Until the
baseline revision lands, `backend/app/db/database.py` remains the active schema
bootstrap path.
