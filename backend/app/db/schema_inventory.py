"""Helpers to snapshot backend schema metadata for migration planning."""

from __future__ import annotations

import json
from typing import Any

from app.db.database import Base
import app.models  # noqa: F401  Ensures metadata is fully registered.

_COMPATIBILITY_COLUMNS = {
    "users": ["is_active", "is_verified"],
    "ai_gateway_targets": ["connection_method", "api_key"],
}


def _serialize_column(column) -> dict[str, Any]:
    server_default = None
    if column.server_default is not None:
        server_default = str(getattr(column.server_default, "arg", column.server_default))

    return {
        "name": column.name,
        "type": str(column.type),
        "nullable": column.nullable,
        "primary_key": column.primary_key,
        "server_default": server_default,
    }


def _serialize_foreign_key(foreign_key) -> dict[str, Any]:
    return {
        "column": foreign_key.parent.name,
        "target": str(foreign_key.target_fullname),
        "ondelete": foreign_key.ondelete,
    }


def build_schema_inventory() -> dict[str, Any]:
    """Return a JSON-serializable snapshot of the registered SQLAlchemy metadata."""

    tables: dict[str, Any] = {}
    for table in sorted(Base.metadata.sorted_tables, key=lambda item: item.name):
        tables[table.name] = {
            "schema": table.schema,
            "columns": [_serialize_column(column) for column in table.columns],
            "foreign_keys": [_serialize_foreign_key(fk) for fk in table.foreign_keys],
            "indexes": sorted(index.name for index in table.indexes if index.name),
        }

    compatibility_columns = {}
    for table_name, column_names in _COMPATIBILITY_COLUMNS.items():
        table = Base.metadata.tables.get(table_name)
        available = set(table.columns.keys()) if table is not None else set()
        compatibility_columns[table_name] = {
            column_name: column_name in available for column_name in column_names
        }

    return {
        "table_count": len(tables),
        "tables": tables,
        "compatibility_columns": compatibility_columns,
    }


def build_schema_inventory_json(*, indent: int = 2) -> str:
    """Serialize the metadata snapshot as JSON for docs or manual review."""

    return json.dumps(build_schema_inventory(), indent=indent, sort_keys=True)
