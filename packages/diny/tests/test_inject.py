"""Tests for the @inject decorator: param passthrough, caller overrides, mixed args."""

from diny import Factory, Singleton, inject


class Dep:
    def __init__(self):
        self.x = "auto"


def test_plain_params_untouched(di):
    @inject
    def f(x: int):
        return x

    assert f(5) == 5


def test_plain_params_with_default(di):
    @inject
    def f(x: int = 10):
        return x

    assert f() == 10
    assert f(3) == 3


def test_mixed_plain_and_injected(di):
    @inject
    def f(x: int, dep: Singleton[Dep]):
        return x, dep

    x, dep = f(42)
    assert x == 42
    assert isinstance(dep, Dep)


def test_positional_and_injected(di):
    @inject
    def f(a: int, b: str, dep: Singleton[Dep]):
        return a, b, dep.x

    assert f(1, "hi") == (1, "hi", "auto")


def test_caller_overrides_singleton(di):
    custom = Dep()
    custom.x = "manual"

    @inject
    def f(dep: Singleton[Dep]):
        return dep.x

    assert f(dep=custom) == "manual"


def test_caller_overrides_factory(di):
    custom = Dep()
    custom.x = "manual"

    @inject
    def f(dep: Factory[Dep]):
        return dep.x

    assert f(dep=custom) == "manual"


def test_caller_override_positional(di):
    @inject
    def f(dep: Singleton[Dep]):
        return dep.x

    custom = Dep()
    custom.x = "pos"
    assert f(custom) == "pos"


def test_no_injected_params(di):
    @inject
    def f(x: int, y: str):
        return f"{x}-{y}"

    assert f(1, "a") == "1-a"


def test_all_injected(di):
    class Other:
        pass

    @inject
    def f(dep: Singleton[Dep], other: Singleton[Other]):
        return dep, other

    dep, other = f()
    assert isinstance(dep, Dep)
    assert isinstance(other, Other)


def test_kwargs_passthrough(di):
    @inject
    def f(dep: Singleton[Dep], **kw):
        return dep, kw

    dep, kw = f(extra=42)
    assert isinstance(dep, Dep)
    assert kw == {"extra": 42}


def test_preserves_function_metadata():
    @inject
    def my_func(dep: Singleton[Dep]):
        """My docstring."""
        pass

    assert my_func.__name__ == "my_func"
    assert my_func.__doc__ == "My docstring."


def test_multiple_calls_independent_factories(di):
    results = []

    @inject
    def f(dep: Factory[Dep]):
        results.append(dep)

    f()
    f()
    f()
    assert len(results) == 3
    assert len(set(id(r) for r in results)) == 3


def test_return_annotation_ignored(di):
    """@inject should skip return type hints and only inject parameters."""

    @inject
    def f(dep: Singleton[Dep]) -> str:
        return dep.x

    assert f() == "auto"
