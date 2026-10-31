# pyright: reportUnnecessaryIsInstance = false
"""Conversion helpers built on magic methods and registered converters.

Two mechanisms are provided:

1. Magic methods -- a type implements ``__into__`` (see `Into`) or
   ``__try_into__`` (see `TryInto`) and converts itself.
2. Converter registries -- infallible converters live in `INTO_CONVERTERS`
   and fallible ones in `TRY_INTO_CONVERTERS`, keyed by
   ``(source type, target type)``. Values converted this way must be wrapped
   in `Reg`, which keeps the intent visible in the type signature.

Resolution order:

- `into` prefers ``__into__`` and falls back to `INTO_CONVERTERS`.
- `try_into` prefers ``__try_into__``, then `TRY_INTO_CONVERTERS`, then the
  same path as `into`.

A magic method that raises ``NotImplementedError`` is treated as missing, so
resolution continues in the registry.

Example:
    >>> register_into(int, str, lambda value: f"#{value}")
    >>> into(Reg(42), str)
    '#42'
"""

from collections.abc import Callable
from typing import Any, Protocol, cast

from rezult import Err, Ok, Result


class Into[T](Protocol):
    """Protocol for values that convert themselves into another type.

    Implementing ``__into__`` lets a type be passed to `into` directly,
    without a `Reg` wrapper and without registering a converter.
    """

    def __into__(self, into: type[T]) -> T:
        """Convert this value into the given target type.

        Args:
            into: Target type of the conversion.

        Returns:
            The converted value.

        Raises:
            NotImplementedError: If this type cannot convert into the given
                target type.
        """
        raise NotImplementedError


class TryInto[T, E](Protocol):
    """Protocol for values that fallibly convert themselves.

    Implementing ``__try_into__`` lets a type be passed to `try_into`
    directly, without a `Reg` wrapper and without registering a converter.
    """

    def __try_into__(self, into: type[T]) -> Result[T, E]:
        """Try to convert this value into the given target type.

        Args:
            into: Target type of the conversion.

        Returns:
            ``Ok`` with the converted value, or ``Err`` describing why the
            conversion failed.

        Raises:
            NotImplementedError: If this type cannot convert into the given
                target type.
        """
        raise NotImplementedError


class Reg[T]:
    """Explicit marker for values converted by a registered converter.

    `into` and `try_into` only accept registered-converter sources when they
    are wrapped in ``Reg``, which makes the conversion path visible in the
    type signature (``Into[T] | Reg[S]`` and ``TryInto[T, E] | Reg[S]``).

    The wrapper is transparent at runtime: the value is unwrapped and
    resolved normally, so an implemented magic method still wins over a
    registered converter.

    Attributes:
        value: The wrapped source value.

    Example:
        >>> into(Reg(Meters(1500)), Kilometers)
    """

    __slots__ = ("value",)
    __match_args__ = ("value",)

    def __init__(self, value: T) -> None:
        """Initialize the wrapper.

        Args:
            value: Source value to convert through a registered converter.
        """
        self.value: T = value

    def __repr__(self) -> str:
        """Return a debug representation such as ``Reg(42)``."""
        return f"Reg({self.value!r})"


#: Source accepted by `into`: a self-converting value or a `Reg` wrapper.
type IntoSource[S, T] = Into[T] | Reg[S]

#: Source accepted by `try_into`: a fallibly self-converting value or `Reg`.
type TryIntoSource[S, T, E] = TryInto[T, E] | Reg[S]

#: Infallible converter from ``T`` to ``U``.
type Converter[T, U] = Callable[[T], U]

#: Fallible converter from ``T`` to ``U``, reporting failures as ``Result``.
type TryConverter[T, U, E] = Callable[[T], Result[U, E]]

#: Registry used by `into`; keys are ``(source class, target class)``.
INTO_CONVERTERS: dict[tuple[type, type], Converter[Any, Any]] = {}

#: Registry used by `try_into`; keys are ``(source class, target class)``.
TRY_INTO_CONVERTERS: dict[tuple[type, type], TryConverter[Any, Any, Any]] = {}


def register_into[T, U](
    source: type[T],
    target: type[U],
    converter: Converter[T, U],
) -> None:
    """Register an infallible converter for `into`.

    Keys are matched through both MROs: the nearest source class wins, then
    the nearest target class. Registering ``object`` as the target therefore
    applies the converter to every target type. Registering an existing pair
    replaces the previous converter.

    Args:
        source: Type of the value being converted.
        target: Type produced by ``converter``.
        converter: Callable receiving the source value and returning the
            converted value.

    Raises:
        TypeError: If ``source`` or ``target`` is not a class, or if
            ``converter`` is not callable.

    Example:
        >>> register_into(Meters, Kilometers, lambda m: Kilometers(m.value / 1000))
        >>> into(Reg(Meters(1500)), Kilometers).value
        1.5
    """
    _validate(source, target, converter)
    INTO_CONVERTERS[source, target] = converter


def register_try_into[T, U, E](
    source: type[T],
    target: type[U],
    converter: TryConverter[T, U, E],
) -> None:
    """Register a fallible converter for `try_into`.

    The converter should return a ``Result``; a plain value is wrapped in
    ``Ok`` and a raised ``Exception`` becomes ``Err``. Matching follows the
    same MRO rules as `register_into`.

    Args:
        source: Type of the value being converted.
        target: Type produced by ``converter``.
        converter: Callable receiving the source value and returning a
            ``Result`` (or a plain value, which is wrapped in ``Ok``).

    Raises:
        TypeError: If ``source`` or ``target`` is not a class, or if
            ``converter`` is not callable.

    Example:
        >>> register_try_into(
        ...     str,
        ...     int,
        ...     lambda text: Ok(int(text)) if text.isdigit() else Err(ValueError(text)),
        ... )
        >>> try_into(Reg("42"), int)
        Ok(42)
    """
    _validate(source, target, converter)
    TRY_INTO_CONVERTERS[source, target] = converter


def unregister_into(source: type, target: type) -> None:
    """Remove the converter registered for ``source`` -> ``target``.

    Does nothing when the pair is not registered.

    Args:
        source: Source type of the registration to remove.
        target: Target type of the registration to remove.
    """
    INTO_CONVERTERS.pop((source, target), None)


def unregister_try_into(source: type, target: type) -> None:
    """Remove the try converter registered for ``source`` -> ``target``.

    Does nothing when the pair is not registered.

    Args:
        source: Source type of the registration to remove.
        target: Target type of the registration to remove.
    """
    TRY_INTO_CONVERTERS.pop((source, target), None)


def into[S, T](from_: IntoSource[S, T], into: type[T]) -> T:
    """Convert ``from_`` into the given target type.

    Args:
        from_: Value implementing `Into`, or a `Reg` wrapper around a value
            whose converter is registered in `INTO_CONVERTERS`.
        into: Target type of the conversion.

    Returns:
        The converted value.

    Raises:
        NotImplementedError: If ``__into__`` raises it and no converter is
            registered for the pair.
        TypeError: If the value has no ``__into__`` and no converter is
            registered for the pair.

    Example:
        >>> into(Version(3), str)
        'v3'
        >>> into(Reg(Meters(1500)), Kilometers).value
        1.5
    """
    return cast(T, _convert(_unwrap(from_), into))


def try_into[S, T, E](from_: TryIntoSource[S, T, E], into: type[T]) -> Result[T, E]:
    """Try to convert ``from_`` into the given target type.

    Resolution order is ``__try_into__``, `TRY_INTO_CONVERTERS`, then the
    infallible path used by `into` (``__into__`` and `INTO_CONVERTERS`).
    Any exception raised along the way becomes ``Err``.

    Args:
        from_: Value implementing `TryInto`, or a `Reg` wrapper around a value
            whose converter is registered in `TRY_INTO_CONVERTERS` or
            `INTO_CONVERTERS`.
        into: Target type of the conversion.

    Returns:
        ``Ok`` with the converted value, or ``Err`` describing why the
        conversion failed.

    Example:
        >>> try_into(Reg("42"), int)
        Ok(42)
    """
    value = _unwrap(from_)

    magic = getattr(value, "__try_into__", None)
    if magic is not None:
        try:
            return cast(Result[T, E], magic(into))
        except NotImplementedError:
            pass

    converter = _lookup(TRY_INTO_CONVERTERS, value, into)
    if converter is not None:
        try:
            result = converter(value)
        except Exception as error:
            return Err(cast(E, error))
        if isinstance(result, Result):
            return cast(Result[T, E], result)
        return Ok(cast(T, result))

    try:
        return Ok(_convert(value, into))
    except Exception as error:
        return Err(cast(E, error))


def _unwrap(from_: object) -> object:
    """Return the value inside a `Reg` wrapper, or ``from_`` unchanged.

    Args:
        from_: Possibly wrapped source value.

    Returns:
        The unwrapped source value.
    """
    return from_.value if isinstance(from_, Reg) else from_  # type: ignore


def _convert(from_: object, target: type) -> Any:
    """Resolve and run an infallible conversion.

    Args:
        from_: Unwrapped source value.
        target: Target type of the conversion.

    Returns:
        The converted value.

    Raises:
        NotImplementedError: If ``__into__`` raises it and no converter is
            registered for the pair.
        TypeError: If the value has no ``__into__`` and no converter is
            registered for the pair.
    """
    magic = getattr(from_, "__into__", None)
    if magic is not None:
        try:
            return magic(target)
        except NotImplementedError:
            converter = _lookup(INTO_CONVERTERS, from_, target)
            if converter is None:
                raise
            return converter(from_)

    converter = _lookup(INTO_CONVERTERS, from_, target)
    if converter is None:
        raise TypeError(
            f"no conversion from {type(from_).__qualname__!r} "
            f"to {getattr(target, '__qualname__', target)!r}"
        )
    return converter(from_)


def _lookup[T](
    registry: dict[tuple[type, type], T],
    value: object,
    target: type,
) -> T | None:
    """Find a converter by walking the source and target MROs.

    Args:
        registry: Registry to search.
        value: Source value whose type starts the source lookup.
        target: Target type that starts the target lookup.

    Returns:
        The first matching converter, or ``None`` when nothing matches.
    """
    target_mro = getattr(target, "__mro__", (target,))
    for source_cls in type(value).__mro__:
        for target_cls in target_mro:
            converter = registry.get((source_cls, target_cls))
            if converter is not None:
                return converter
    return None


def _validate(source: type, target: type, converter: Callable[..., Any]) -> None:
    """Validate the arguments of a registration helper.

    Args:
        source: Type of the value being converted.
        target: Type produced by ``converter``.
        converter: Callable performing the conversion.

    Raises:
        TypeError: If ``source`` or ``target`` is not a class, or if
            ``converter`` is not callable.
    """
    if not isinstance(source, type) or not isinstance(target, type):
        raise TypeError("source and target must be classes")
    if not callable(converter):
        raise TypeError("converter must be callable")
