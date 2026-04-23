"""
tinydi — a dead-simple dependency injection library.

Annotation-driven: mark parameters with Singleton[T] to request injection.
"""
import sys
import inspect
from contextvars import ContextVar
from contextlib import contextmanager, asynccontextmanager
from functools import wraps
from inspect import signature, iscoroutinefunction
from typing import Annotated, get_type_hints, get_args

__all__ = ["inject", "provide", "aprovide", "Singleton", "Factory",
           "singleton", "factory"]

_registry: ContextVar[dict] = ContextVar("registry", default={})
_cache: ContextVar[dict] = ContextVar("cache", default={})


class Singleton:
    """Marker: `Singleton[T]` → one instance per scope (cached)."""
    def __class_getitem__(cls, tp):
        return Annotated[tp, cls]


class Factory:
    """Marker: `Factory[T]` → fresh instance at this site (not cached)."""
    def __class_getitem__(cls, tp):
        return Annotated[tp, cls]


def singleton(cls):
    """Class decorator: bare references to this class inject as Singleton."""
    cls._di_default_scope = "singleton"
    return cls


def factory(cls):
    """Class decorator: bare references to this class inject as Factory."""
    cls._di_default_scope = "factory"
    return cls


def _unwrap(hint):
    """Return (type, is_factory) if injected, else None.

    Site annotations (Singleton[T] / Factory[T]) are authoritative.
    For bare class references, falls back to the class's @singleton/@factory
    decorator if present. Undecorated classes are not auto-injected.
    """
    args = get_args(hint)
    if len(args) >= 2:
        for a in args[1:]:
            if a is Singleton:
                return args[0], False
            if a is Factory:
                return args[0], True
    if isinstance(hint, type):
        scope = getattr(hint, "_di_default_scope", None)
        if scope == "singleton":
            return hint, False
        if scope == "factory":
            return hint, True
    return None


def _is_fn(x):
    """Is x a provider function (not a class, not an instance)?"""
    return inspect.isfunction(x) or inspect.ismethod(x) or inspect.isbuiltin(x)


def _injectable_params(target):
    """Yield (name, type, is_factory) for injected params.

    Works on classes (inspects __init__) and on functions.
    """
    fn = target.__init__ if isinstance(target, type) else target
    hints = get_type_hints(fn, include_extras=True)
    for name, hint in hints.items():
        if name == "return":
            continue
        info = _unwrap(hint)
        if info is not None:
            yield (name, *info)


def _resolve(tp, is_factory=False, seen=frozenset()):
    cache = _cache.get()
    if not is_factory and tp in cache:
        return cache[tp]
    if tp in seen:
        raise RuntimeError(f"Circular dependency on {tp.__name__}")
    target = _registry.get().get(tp, tp)
    if not isinstance(target, type) and not _is_fn(target):
        # Plain instance.
        if not is_factory:
            cache[tp] = target
            return target
        # Factory over an instance: rebuild from its concrete type.
        target = type(target)
    if iscoroutinefunction(target):
        raise RuntimeError(f"Provider for {tp.__name__} is async; use aprovide()")
    seen = seen | {tp}
    kwargs = {n: _resolve(a, f, seen) for n, a, f in _injectable_params(target)}
    instance = target(**kwargs)
    if not is_factory:
        cache[tp] = instance
    return instance


async def _aresolve(tp, is_factory=False, seen=frozenset()):
    cache = _cache.get()
    if not is_factory and tp in cache:
        return cache[tp]
    if tp in seen:
        raise RuntimeError(f"Circular dependency on {tp.__name__}")
    target = _registry.get().get(tp, tp)
    if not isinstance(target, type) and not _is_fn(target):
        if not is_factory:
            cache[tp] = target
            return target
        target = type(target)
    seen = seen | {tp}
    kwargs = {n: await _aresolve(a, f, seen) for n, a, f in _injectable_params(target)}
    if iscoroutinefunction(target):
        instance = await target(**kwargs)
    else:
        instance = target(**kwargs)
    if not is_factory:
        cache[tp] = instance
    return instance


def inject(func):
    """Decorate a function so its Singleton[T] / Factory[T] params auto-resolve.

    Non-injected params are passed through to the caller unchanged.
    Caller-supplied values for injected params take precedence.
    """
    sig = signature(func)
    injectable = list(_injectable_params(func))

    if iscoroutinefunction(func):
        @wraps(func)
        async def aw(*args, **kwargs):
            given = sig.bind_partial(*args, **kwargs).arguments
            for name, tp, is_factory in injectable:
                if name not in given and name not in kwargs:
                    kwargs[name] = await _aresolve(tp, is_factory)
            return await func(*args, **kwargs)
        return aw

    @wraps(func)
    def w(*args, **kwargs):
        given = sig.bind_partial(*args, **kwargs).arguments
        for name, tp, is_factory in injectable:
            if name not in given and name not in kwargs:
                kwargs[name] = _resolve(tp, is_factory)
        return func(*args, **kwargs)
    return w


def _lookup(name):
    f = sys._getframe(1)
    while f:
        if name in f.f_locals:
            return f.f_locals[name]
        if name in f.f_globals:
            return f.f_globals[name]
        f = f.f_back
    raise NameError(name)


def _build_reg(instances, mappings):
    reg = {type(i): i for i in instances}
    for k, v in mappings.items():
        reg[k if isinstance(k, type) else _lookup(k)] = v
    return reg


@contextmanager
def provide(*instances, **mappings):
    """Open a scope with the given dependency registrations."""
    r = _registry.set({**_registry.get(), **_build_reg(instances, mappings)})
    c = _cache.set({})
    try:
        yield
    finally:
        _cache.reset(c)
        _registry.reset(r)


@asynccontextmanager
async def aprovide(*instances, **mappings):
    """Async variant of provide()."""
    r = _registry.set({**_registry.get(), **_build_reg(instances, mappings)})
    c = _cache.set({})
    try:
        yield
    finally:
        _cache.reset(c)
        _registry.reset(r)
