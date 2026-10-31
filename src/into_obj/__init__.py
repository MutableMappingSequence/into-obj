"""Rust-style conversions for Python, built on ``rezult``.

The public API is re-exported from `into_obj.into`:

- `into` / `try_into`: convert a value into a target type.
- `Into` / `TryInto`: protocols implemented by self-converting types.
- `Reg`: wrapper marking values converted by a registered converter.
- `register_into` / `register_try_into`: register converters.
- `unregister_into` / `unregister_try_into`: remove converters.
- `INTO_CONVERTERS` / `TRY_INTO_CONVERTERS`: the converter registries.
"""

from .into import (
    INTO_CONVERTERS,
    TRY_INTO_CONVERTERS,
    Converter,
    Into,
    IntoSource,
    Reg,
    TryConverter,
    TryInto,
    TryIntoSource,
    into,
    register_into,
    register_try_into,
    try_into,
    unregister_into,
    unregister_try_into,
)

__all__ = [
    "INTO_CONVERTERS",
    "TRY_INTO_CONVERTERS",
    "Converter",
    "Into",
    "IntoSource",
    "Reg",
    "TryConverter",
    "TryInto",
    "TryIntoSource",
    "into",
    "register_into",
    "register_try_into",
    "try_into",
    "unregister_into",
    "unregister_try_into",
]


def main() -> None:
    """Run the ``into-obj`` console script."""
    print("Hello from into-obj!")
