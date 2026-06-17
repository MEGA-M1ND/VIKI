"""Result envelope types for explicit success/failure modelling.

Instead of raising exceptions across service boundaries, operations that can
partially fail return a typed ``Ok`` or ``Err``. The caller inspects ``.ok``
before accessing ``.value``.

Usage::

    result: Ok[MemoryRecord] | Err = await writer.safe_write(record)
    if result.ok:
        use(result.value)
    else:
        log(result.error, result.details)
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Ok(BaseModel, Generic[T]):
    """Successful outcome carrying a value.

    Attributes:
        value: The operation's successful result.
        ok: Always ``True`` — use this to discriminate from :class:`Err`.
    """

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    ok: bool = True
    value: T


class Err(BaseModel):
    """Failed outcome carrying an error description.

    Attributes:
        error: Human-readable error message.
        details: Optional structured context (record ids, upstream errors, …).
        ok: Always ``False`` — use this to discriminate from :class:`Ok`.
    """

    model_config = ConfigDict(extra="forbid")

    ok: bool = False
    error: str
    details: dict[str, object] = {}
