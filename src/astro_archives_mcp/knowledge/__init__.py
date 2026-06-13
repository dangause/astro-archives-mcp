"""Curated per-table knowledge layer.

Public exports:
- Schema: the dataclass
- SCHEMA_KB: the curated tuple
- lookup_schema: the keyed lookup
- schema_to_dict: serializer used by the vo_schema_describe envelope
"""
from astro_archives_mcp._serialization import dataclass_to_jsonable_dict
from astro_archives_mcp.knowledge.schemas import (
    SCHEMA_KB,
    Schema,
    lookup_schema,
)


def schema_to_dict(s: Schema) -> dict:
    """Serialize a Schema for inclusion in a tool's JSON envelope."""
    return dataclass_to_jsonable_dict(s)


__all__ = ["SCHEMA_KB", "Schema", "lookup_schema", "schema_to_dict"]
