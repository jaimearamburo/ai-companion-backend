"""Shared base class and field types for every boundary model.

Boundary models are strict: values must already have the declared type (no
silent coercion of "3" to 3 or "true" to True), unknown fields are rejected,
and instances are immutable. Sequence fields accept lists, because database
rows and YAML files supply lists, but their items stay strict.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class Contract(BaseModel):
    """Base for every model that crosses a boundary."""

    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


type Seq[T] = Annotated[tuple[T, ...], Field(strict=False)]
"""An immutable sequence that accepts a list or tuple as input."""

type Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""Text that must contain something other than whitespace."""

type BotSlug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=40)]
"""A bot's short fixed name; the pattern matches the `bots_slug_format` check."""

type PresetName = Annotated[
    str, StringConstraints(pattern=r"^[a-z0-9]+(_[a-z0-9]+)*$", max_length=64)
]
"""A provider preset name, e.g. `deepgram_nova3_au`."""


def has_duplicates[T](items: tuple[T, ...]) -> bool:
    """Whether any item appears more than once."""
    return len(set(items)) != len(items)
