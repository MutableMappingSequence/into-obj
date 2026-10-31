"""Tests for the converter registry fallback in ``into`` / ``try_into``."""

from collections.abc import Iterator

import pytest
from rezult import Err, Ok

from into_obj import (
    INTO_CONVERTERS,
    TRY_INTO_CONVERTERS,
    Reg,
    into,
    register_into,
    register_try_into,
    try_into,
    unregister_into,
    unregister_try_into,
)


@pytest.fixture(autouse=True)
def _isolated_registries() -> Iterator[None]:
    """Keep the global registries untouched between tests."""
    into_snapshot = dict(INTO_CONVERTERS)
    try_snapshot = dict(TRY_INTO_CONVERTERS)
    INTO_CONVERTERS.clear()
    TRY_INTO_CONVERTERS.clear()
    try:
        yield
    finally:
        INTO_CONVERTERS.clear()
        INTO_CONVERTERS.update(into_snapshot)
        TRY_INTO_CONVERTERS.clear()
        TRY_INTO_CONVERTERS.update(try_snapshot)


class Meters:
    def __init__(self, value: float) -> None:
        self.value = value


class Kilometers:
    def __init__(self, value: float) -> None:
        self.value = value


class SubMeters(Meters):
    pass


class WithInto:
    def __init__(self, value: int) -> None:
        self.value = value

    def __into__(self, into: type[str]) -> str:
        if into is str:
            return f"v{self.value}"
        raise NotImplementedError


class WithTryInto:
    def __init__(self, value: int) -> None:
        self.value = value

    def __try_into__(self, into: type[int]) -> Ok[int] | Err[str]:
        if into is int:
            return Ok(self.value)
        return Err("unsupported target")


def _register_meters(*, source: type = Meters) -> None:
    register_into(source, Kilometers, lambda meters: Kilometers(meters.value / 1000))


# --------------------------------------------------------------------------
# into: magic methods
# --------------------------------------------------------------------------


def test_into_uses_magic_method() -> None:
    assert into(WithInto(3), str) == "v3"


def test_into_prefers_magic_method_over_registry() -> None:
    register_into(WithInto, str, lambda with_into: "from-registry")

    assert into(WithInto(3), str) == "v3"
    assert into(Reg(WithInto(3)), str) == "v3"


def test_into_magic_method_not_implemented_falls_back_to_registry() -> None:
    register_into(WithInto, float, lambda with_into: float(with_into.value))

    assert into(WithInto(7), float) == 7.0


def test_into_magic_method_not_implemented_without_converter_reraises() -> None:
    with pytest.raises(NotImplementedError):
        into(WithInto(7), float)


# --------------------------------------------------------------------------
# into: converter dictionary
# --------------------------------------------------------------------------


def test_into_uses_registered_converter_for_reg_wrapped_value() -> None:
    _register_meters()

    assert into(Reg(Meters(1500)), Kilometers).value == 1.5


def test_into_lookup_walks_source_mro() -> None:
    _register_meters()

    assert into(Reg(SubMeters(2000)), Kilometers).value == 2.0


def test_into_lookup_prefers_nearest_source_class() -> None:
    _register_meters()
    register_into(SubMeters, Kilometers, lambda meters: Kilometers(-1))

    assert into(Reg(SubMeters(2000)), Kilometers).value == -1
    assert into(Reg(Meters(2000)), Kilometers).value == 2


def test_into_lookup_walks_target_mro() -> None:
    class Fahrenheit(Kilometers):
        pass

    register_into(Meters, Kilometers, lambda meters: Fahrenheit(meters.value))

    result = into(Reg(Meters(3)), Fahrenheit)

    assert isinstance(result, Fahrenheit)
    assert result.value == 3


def test_into_object_target_acts_as_wildcard() -> None:
    register_into(Meters, object, lambda meters: ("meters", meters.value))

    assert into(Reg(Meters(3)), str) == ("meters", 3)


def test_into_missing_conversion_raises_type_error() -> None:
    with pytest.raises(TypeError, match="no conversion from 'Meters' to 'Kilometers'"):
        into(Reg(Meters(1)), Kilometers)


# --------------------------------------------------------------------------
# try_into: magic methods and dictionary
# --------------------------------------------------------------------------


def test_try_into_uses_magic_method() -> None:
    assert try_into(WithTryInto(5), int) == Ok(5)
    assert try_into(WithTryInto(5), str) == Err("unsupported target")


def test_try_into_prefers_magic_method_over_registry() -> None:
    register_try_into(WithTryInto, int, lambda with_try_into: Ok(-1))

    assert try_into(WithTryInto(5), int) == Ok(5)


def test_try_into_registered_converter_returning_result() -> None:
    register_try_into(
        str,
        int,
        lambda text: Ok(int(text)) if text.isdigit() else Err(ValueError(text)),
    )

    assert try_into(Reg("12"), int) == Ok(12)
    failure = try_into(Reg("abc"), int)
    assert isinstance(failure, Err)
    assert isinstance(failure.value, ValueError)


def test_try_into_registered_converter_returning_plain_value() -> None:
    register_try_into(bytes, str, lambda data: data.decode())

    assert try_into(Reg(b"hi"), str) == Ok("hi")


def test_try_into_registered_converter_exception_becomes_err() -> None:
    def boom(_: bytearray) -> str:
        raise RuntimeError("boom")

    register_try_into(bytearray, str, boom)

    failure = try_into(Reg(bytearray(b"hi")), str)
    assert isinstance(failure, Err)
    assert isinstance(failure.value, RuntimeError)


def test_try_into_falls_back_to_into_magic_method() -> None:
    assert try_into(WithInto(4), str) == Ok("v4")


def test_try_into_falls_back_to_into_converter() -> None:
    _register_meters()

    assert try_into(Reg(Meters(1000)), Kilometers).unwrap().value == 1.0


def test_try_into_without_conversion_returns_err() -> None:
    failure = try_into(Reg(Meters(1)), Kilometers)

    assert isinstance(failure, Err)
    assert isinstance(failure.value, TypeError)


def test_try_into_magic_method_not_implemented_falls_back_to_registry() -> None:
    class Partial:
        def __try_into__(self, into: type[int]) -> Ok[int]:
            raise NotImplementedError

    register_try_into(Partial, int, lambda _: Ok(99))

    assert try_into(Partial(), int) == Ok(99)


# --------------------------------------------------------------------------
# registration helpers and Reg
# --------------------------------------------------------------------------


def test_unregister_removes_converters() -> None:
    _register_meters()
    register_try_into(str, int, lambda text: Ok(int(text)))

    unregister_into(Meters, Kilometers)
    unregister_try_into(str, int)

    assert (Meters, Kilometers) not in INTO_CONVERTERS
    assert (str, int) not in TRY_INTO_CONVERTERS

    # Unregistering an unknown key is a no-op.
    unregister_into(Meters, Kilometers)
    unregister_try_into(str, int)


@pytest.mark.parametrize(
    ("source", "target", "converter"),
    [
        ("Meters", Kilometers, lambda value: value),
        (Meters, "Kilometers", lambda value: value),
        (Meters, Kilometers, "not-callable"),
    ],
)
def test_register_validates_arguments(source: object, target: object, converter: object) -> None:
    with pytest.raises(TypeError):
        register_into(source, target, converter)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        register_try_into(source, target, converter)  # type: ignore[arg-type]


def test_reg_wraps_value_and_supports_pattern_matching() -> None:
    wrapped = Reg(Meters(2))

    assert wrapped.value.value == 2
    assert repr(wrapped).startswith("Reg(<")
    assert repr(Reg(1)) == "Reg(1)"

    match Reg(5):
        case Reg(value):
            assert value == 5
        case _:  # pragma: no cover
            pytest.fail("Reg should match with one positional pattern")
