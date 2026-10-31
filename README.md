# into-obj

Rust-style `Into` & `TryInto` conversions for Python, with explicit,
type-checked converter registries.

```python
from into_obj import Reg, into, register_into

register_into(Celsius, Fahrenheit, lambda c: Fahrenheit(c.degrees * 9 / 5 + 32))

into(Reg(Celsius(100)), Fahrenheit)  # 212.0
```

## Features

- `into(from_, Target)` for infallible conversions and `try_into(from_, Target)`
  for fallible ones that return `Result`.
- Two conversion mechanisms:
  - **Magic methods** — a type converts itself via `__into__` / `__try_into__`.
  - **Converter registries** — converters keyed by `(source type, target type)`,
    usable without touching the source type.
- `Reg` wrapper makes registry-based conversions visible in the type signature,
  so type checkers reject unregistered, non-converting sources.
- MRO-aware dispatch: a converter registered for a base class also serves its
  subclasses, and `object` works as a wildcard target.
- Errors are explicit: `into` raises, `try_into` returns `Err`.

## Requirements

- Python 3.12+ (the package uses PEP 695 generics)
- `rezult >= 0.2.0`

## Installation

```bash
uv add into-obj
# or
pip install into-obj
```

## Quick start

```python
from rezult import Err, Ok

from into_obj import Reg, into, register_into, register_try_into, try_into


class Version:
    def __init__(self, number: int) -> None:
        self.number = number

    def __into__(self, into: type[str]) -> str:
        return f"v{self.number}"


class Celsius:
    def __init__(self, degrees: float) -> None:
        self.degrees = degrees


class Fahrenheit(float):
    pass


register_into(
    Celsius,
    Fahrenheit,
    lambda celsius: Fahrenheit(celsius.degrees * 9 / 5 + 32),
)

register_try_into(
    str,
    int,
    lambda text: Ok(int(text)) if text.isdigit() else Err(ValueError(text)),
)

assert into(Version(3), str) == "v3"
assert into(Reg(Celsius(100)), Fahrenheit) == 212.0
assert try_into(Reg("42"), int) == Ok(42)
assert try_into(Reg("abc"), int).is_err()
```

## How it works

Every call resolves a conversion by walking a fixed order. A magic method that
raises `NotImplementedError` counts as missing, and resolution continues.

| Call                  | Resolution order                                                                          |
| --------------------- | ----------------------------------------------------------------------------------------- |
| `into(x, T)`          | `x.__into__(T)`                                                                            |
| `into(Reg(x), T)`     | `x.__into__(T)` → `INTO_CONVERTERS`                                                        |
| `try_into(x, T)`      | `x.__try_into__(T)`                                                                        |
| `try_into(Reg(x), T)` | `x.__try_into__(T)` → `TRY_INTO_CONVERTERS` → `x.__into__(T)` → `INTO_CONVERTERS`          |

### Magic methods

Implement `__into__` for infallible conversions, or `__try_into__` when the
conversion can fail.

```python
from rezult import Err, Ok, Result


class Port:
    def __init__(self, text: str) -> None:
        self.text = text

    def __try_into__(self, into: type[int]) -> Result[int, str]:
        if into is not int:
            return Err("only int is supported")
        if not self.text.isdigit():
            return Err(f"invalid port: {self.text}")
        return Ok(int(self.text))


assert try_into(Port("8080"), int) == Ok(8080)
assert try_into(Port("http"), int) == Err("invalid port: http")
```

`Into[T]` and `TryInto[T, E]` are protocols, so implementing the method is
enough — no inheritance required.

### Registered converters

Register a converter when you cannot (or do not want to) change the source
type. Wrap the source value in `Reg` to select the registry path.

```python
class Meters:
    def __init__(self, value: float) -> None:
        self.value = value


class Kilometers:
    def __init__(self, value: float) -> None:
        self.value = value


register_into(Meters, Kilometers, lambda meters: Kilometers(meters.value / 1000))

assert into(Reg(Meters(1500)), Kilometers).value == 1.5
```

A fallible converter returns a `Result`. Returning a plain value is treated as
`Ok(value)`, and raising an `Exception` becomes `Err(exception)`.

```python
register_try_into(
    str,
    int,
    lambda text: Ok(int(text)) if text.isdigit() else Err(ValueError(text)),
)

assert try_into(Reg("7"), int) == Ok(7)
assert isinstance(try_into(Reg("seven"), int), Err)
```

Converters can be removed again, which is useful in tests:

```python
from into_obj import unregister_into, unregister_try_into

unregister_into(Meters, Kilometers)
unregister_try_into(str, int)
```

### MRO-aware lookup

Registry keys are `(source type, target type)`. Lookup walks the source MRO
first, then the target MRO, so the nearest source class wins.

```python
class SubMeters(Meters):
    pass


register_into(Meters, Kilometers, lambda meters: Kilometers(meters.value / 1000))
register_into(SubMeters, Kilometers, lambda meters: Kilometers(-1))

into(Reg(Meters(2000)), Kilometers).value      # 2.0  (base converter)
into(Reg(SubMeters(2000)), Kilometers).value   # -1   (nearest source wins)
```

Registering `object` as the target makes a converter apply to every target
type:

```python
register_into(Meters, object, lambda meters: meters.value)

into(Reg(Meters(3)), int)  # 3
```

## API reference

### Functions

| Function                                | Description                                                        |
| --------------------------------------- | ------------------------------------------------------------------ |
| `into(from_, target)`                   | Convert `from_` into `target`, raising on failure.                 |
| `try_into(from_, target)`               | Convert `from_` into `target`, returning `Result[T, E]`.           |
| `register_into(source, target, conv)`   | Register an infallible converter for `(source, target)`.           |
| `register_try_into(source, target, conv)` | Register a fallible converter for `(source, target)`.            |
| `unregister_into(source, target)`       | Remove the infallible converter for the pair, if any.              |
| `unregister_try_into(source, target)`   | Remove the fallible converter for the pair, if any.                |

`register_*` validates its arguments and raises `TypeError` if `source` or
`target` is not a class, or if the converter is not callable.

### Types

| Name                     | Description                                                            |
| ------------------------ | ---------------------------------------------------------------------- |
| `Reg[T]`                 | Wrapper marking a value as converted by a registered converter.        |
| `Into[T]`                | Protocol for types implementing `__into__`.                            |
| `TryInto[T, E]`          | Protocol for types implementing `__try_into__`.                        |
| `IntoSource[S, T]`       | `Into[T] \| Reg[S]` — accepted by `into`.                              |
| `TryIntoSource[S, T, E]` | `TryInto[T, E] \| Reg[S]` — accepted by `try_into`.                    |
| `Converter[T, U]`        | `Callable[[T], U]`.                                                    |
| `TryConverter[T, U, E]`  | `Callable[[T], Result[U, E]]`.                                         |
| `INTO_CONVERTERS`        | Registry used by `into`.                                               |
| `TRY_INTO_CONVERTERS`    | Registry used by `try_into`.                                           |

### Type signatures

```python
def into[S, T](from_: IntoSource[S, T], into: type[T]) -> T: ...
def try_into[S, T, E](from_: TryIntoSource[S, T, E], into: type[T]) -> Result[T, E]: ...
```

`S` is the wrapped source type and `T` the target type, which is why `Reg` is
parameterized separately: `into(Reg(Celsius(100)), Fahrenheit)` infers
`S = Celsius` and `T = Fahrenheit`. Passing a registered source without `Reg`
is rejected by type checkers.

### Error handling

- `into` raises `TypeError` when neither a magic method nor a converter is
  available, and re-raises `NotImplementedError` from `__into__` in that case.
- `try_into` never raises for conversion failures: exceptions from the
  registry converter or the fallback path are returned as `Err`.

## Notes

- Registries are process-global dictionaries. Register converters once at
  import time or application startup.
- Registering the same `(source, target)` pair twice replaces the converter.
- `Reg` is transparent at runtime: it is unwrapped before resolution, so a
  magic method still takes precedence over a registered converter.

## Development

```bash
uv sync
uv run pytest
```

Tests live in `tests/test_into.py` and isolate the global registries with an
autouse fixture.

## License
MIT
