"""Shared dataclass → JSON-friendly dict helper.

Used by tools whose envelope is built from a frozen dataclass: turns
tuples (any nesting depth, including 2-tuples-in-a-tuple) into lists,
MappingProxyType into plain dict, and date into ISO 8601 string.
Everything else passes through unchanged.

`dataclasses.asdict` alone is not enough: it preserves tuple-as-tuple
and proxy-as-proxy, both of which serialize to JSON arrays at the edge
but break callers that round-trip through Python.
"""
from dataclasses import fields, is_dataclass
from datetime import date
from types import MappingProxyType
from typing import Any


def _jsonable(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


def dataclass_to_jsonable_dict(obj: Any) -> dict[str, Any]:
    """Convert a frozen dataclass into a JSON-friendly dict.

    Recursively converts tuples → lists, MappingProxyType → dict, and
    date → ISO string. Plain primitives pass through. `obj` MUST be a
    dataclass instance.
    """
    if not is_dataclass(obj):
        raise TypeError(
            f"dataclass_to_jsonable_dict expects a dataclass instance; got {type(obj).__name__}"
        )
    return {f.name: _jsonable(getattr(obj, f.name)) for f in fields(obj)}
