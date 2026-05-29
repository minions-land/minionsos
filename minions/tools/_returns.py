"""Typed return-shape models for high-traffic MCP tools.

Each model documents the wire format of one MCP tool's return value. Models
inherit from :class:`DictLikeBaseModel` so callers may use either attribute
access (``result.port``) or dict-style subscription (``result["port"]`` /
``result.get("commit_sha")``). This keeps the strong typing benefits of
Pydantic without breaking the existing dict-shape API surface that callers,
tests, and the MCP wrappers rely on.

When a model is returned through the FastMCP layer, ``convert_result`` runs
``pydantic_core.to_jsonable_python`` which dumps the model to a plain JSON
dict — the wire format is therefore identical to the prior ``dict[str, object]``
return shape.

If a tool grows new fields, extend the model rather than letting them sneak
in untyped: ``ConfigDict(extra="forbid")`` will surface unknown keys as
validation errors during construction.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class DictLikeBaseModel(BaseModel):
    """Pydantic base class that also supports dict-style read access.

    Adds ``__getitem__``, ``get``, and ``__contains__`` so callers used to
    indexing into the prior ``dict[str, object]`` return shape (e.g.
    ``result["port"]``, ``result.get("commit_sha")``) keep working without
    modification. Also overrides ``__eq__`` to compare equal against the
    plain-dict form (``model_dump()``) — useful for tests asserting strict
    return shape via ``result == {...}``.

    Writes are not supported — typed result models are immutable contracts;
    mutate by constructing a new instance instead.
    """

    model_config = ConfigDict(extra="forbid")

    def __getitem__(self, key: str) -> Any:
        if key in type(self).model_fields:
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        if key in type(self).model_fields:
            return getattr(self, key)
        return default

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key in type(self).model_fields

    def __eq__(self, other: object) -> bool:
        if isinstance(other, dict):
            return self.model_dump() == other
        return super().__eq__(other)

    def __hash__(self) -> int:  # pragma: no cover - models stay unhashable
        # Pydantic BaseModel is unhashable by default; restate to keep mypy/ty
        # happy when overriding __eq__.
        raise TypeError(f"unhashable type: {type(self).__name__!r}")


__all__ = ["DictLikeBaseModel"]
