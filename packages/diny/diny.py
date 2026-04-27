"""
diny - dead-simple dependency injection.

Mark classes, wire functions, resolve dependencies:

    from diny import singleton, inject, provide

    @singleton
    class Config:
        def __init__(self):
            self.url = "postgres://localhost"

    @singleton
    class Database:
        def __init__(self, config: Config):
            self.conn = connect(config.url)

    @inject
    def list_users(db: Database):
        return db.query("SELECT * FROM users")

    list_users()

Override in tests:

    with provide(Config(url="test://")):
        list_users()
"""

import sys
import inspect
from contextvars import ContextVar
from contextlib import contextmanager, asynccontextmanager
from functools import wraps
from inspect import signature, iscoroutinefunction
from typing import Annotated, get_type_hints, get_args

__all__ = [
    "inject",
    "provide",
    "aprovide",
    "Singleton",
    "Factory",
    "singleton",
    "factory",
    "provider",
    "resolve",
    "aresolve",
]

_registry: ContextVar[dict] = ContextVar("registry", default={})
_cache: ContextVar[dict] = ContextVar("cache", default={})
_providers: dict = {}
_deferred_providers: dict[str, object] = {}


class Singleton:
    """Marker: Singleton[T] - one instance per scope (cached).

    Example::

        @inject
        def handler(db: Singleton[Database]):
            ...
    """

    def __class_getitem__(cls, tp):
        return Annotated[tp, cls]


class Factory:
    """Marker: Factory[T] - fresh instance at this site (not cached).

    Example::

        @inject
        def handler(id_a: Factory[RequestId], id_b: Factory[RequestId]):
            # id_a and id_b are different instances
            ...
    """

    def __class_getitem__(cls, tp):
        return Annotated[tp, cls]


def singleton(cls):
    """Class decorator: bare references to this class inject as Singleton.

    Example::

        @singleton
        class Database:
            def __init__(self, config: Config): ...

        @inject
        # no annotation needed
        def handler(db: Database):
            ...
    """
    cls._di_default_scope = "singleton"
    return cls


def factory(cls):
    """Class decorator: bare references to this class inject as Factory.

    Example::

        @factory
        class RequestId:
            def __init__(self): self.value = uuid4()

        @inject
        def handler(a: RequestId, b: RequestId):
            # a and b are different instances
            ...
    """
    cls._di_default_scope = "factory"
    return cls


def provider(tp):
    """Register a function as the default provider for tp.

    tp can be a type or a string name (forward reference). String references
    are resolved lazily the first time the type is requested.

    The decorated function's typed parameters are injected automatically.
    Scope (singleton vs factory) is determined by the call site annotation.
    provide() overrides @provider registrations.

    Raises ValueError if tp already has a registered @provider.

    Example::

        @provider(Database)
        def make_database(config: Config):
            return PostgresDatabase(config.url, pool_size=10)

    Forward reference for use inside a class body::

        class Connection:
            @provider("Connection")
            @classmethod
            def create(cls, config: Config):
                return cls(config.url)
    """

    def decorator(func):
        if isinstance(tp, str):
            if tp in _deferred_providers:
                raise ValueError(f"Duplicate @provider for {tp!r}")
            _deferred_providers[tp] = func
        else:
            if tp in _providers:
                raise ValueError(f"Duplicate @provider for {tp.__name__}")
            _providers[tp] = func
        return func

    return decorator


def _resolve_deferred(tp):
    """Move any deferred provider matching *tp* into the live registry."""
    name = tp.__name__
    if name in _deferred_providers:
        fn = _deferred_providers.pop(name)
        if isinstance(fn, classmethod):
            fn = fn.__get__(None, tp)
        if tp in _providers:
            raise ValueError(f"Duplicate @provider for {tp.__name__}")
        _providers[tp] = fn


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
        _resolve_deferred(hint)
        if hint in _providers:
            return hint, False
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
    target = _registry.get().get(tp, _providers.get(tp, tp))
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
    target = _registry.get().get(tp, _providers.get(tp, tp))
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

    Example::

        @inject
        def get_user(user_id: int, database: Singleton[Database]):
            return database.query(user_id)

        # database is resolved automatically
        get_user(42)
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


def resolve(tp):
    """Return the instance for tp within the current scope.

    Accepts bare types, Singleton[T], or Factory[T].
    Bare types respect their @singleton/@factory/@provider registration.
    Raises TypeError for unregistered types.

    Example::

        with provide():
            # cached singleton
            database = resolve(Database)
            # fresh each call
            request = resolve(Factory[RequestId])
    """
    info = _unwrap(tp)
    if info is not None:
        real_tp, is_factory = info
        _resolve_deferred(real_tp)
        return _resolve(real_tp, is_factory)
    if isinstance(tp, type):
        _resolve_deferred(tp)
        if tp in _providers or tp in _registry.get():
            return _resolve(tp)
    raise TypeError(
        f"{tp} is not registered; use @singleton, @factory, @provider, or Singleton[T]/Factory[T]"
    )


async def aresolve(tp):
    """Async variant of resolve().

    Example::

        async with aprovide():
            database = await aresolve(Database)
    """
    info = _unwrap(tp)
    if info is not None:
        real_tp, is_factory = info
        _resolve_deferred(real_tp)
        return await _aresolve(real_tp, is_factory)
    if isinstance(tp, type):
        _resolve_deferred(tp)
        if tp in _providers or tp in _registry.get():
            return await _aresolve(tp)
    raise TypeError(
        f"{tp} is not registered; use @singleton, @factory, @provider, or Singleton[T]/Factory[T]"
    )


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
def provide(*instances, inherit=False, **mappings):
    """Open a scope with the given dependency registrations.

    When inherit is False (default), the scope starts with a fresh cache.
    When inherit is True, the parent's cached singletons carry through,
    so already-built instances are shared rather than rebuilt.

    Example::

        with provide(Config(url="test://")):
            # uses the test config
            handler()

        with provide(Database=AdminDB, inherit=True):
            # new database, but keeps the parent's mailer, cache, etc.
            handler()
    """
    overrides = _build_reg(instances, mappings)
    r = _registry.set({**_registry.get(), **overrides})
    if inherit:
        cache = {**_cache.get()}
        for tp in overrides:
            cache.pop(tp, None)
    else:
        cache = {}
    c = _cache.set(cache)
    try:
        yield
    finally:
        _cache.reset(c)
        _registry.reset(r)


@asynccontextmanager
async def aprovide(*instances, inherit=False, **mappings):
    """Async variant of provide().

    Example::

        async with aprovide(Database=FakeDatabase):
            await handler()
    """
    overrides = _build_reg(instances, mappings)
    r = _registry.set({**_registry.get(), **overrides})
    if inherit:
        cache = {**_cache.get()}
        for tp in overrides:
            cache.pop(tp, None)
    else:
        cache = {}
    c = _cache.set(cache)
    try:
        yield
    finally:
        _cache.reset(c)
        _registry.reset(r)
