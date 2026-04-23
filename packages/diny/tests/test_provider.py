"""Tests for @provider(Type) decorator."""

import asyncio
from typing import Any

import pytest

from diny import (
    Factory,
    Singleton,
    aprovide,
    inject,
    provide,
    provider,
    singleton,
)


# Use unique classes per test to avoid @provider duplicate errors across tests.


# --- Basic registration ---


class DBConfig:
    def __init__(self):
        self.url = "default"


class DBPool:
    config: Any = None
    custom: bool = False


@provider(DBPool)
def make_pool(config: Singleton[DBConfig]):
    pool = DBPool()
    pool.config = config
    pool.custom = True
    return pool


def test_basic_provider(di):
    @inject
    def grab(pool: DBPool):
        return pool

    pool = grab()
    assert isinstance(pool, DBPool)
    assert pool.custom is True
    assert isinstance(pool.config, DBConfig)


def test_provider_singleton_by_default(di):
    @inject
    def grab(pool: DBPool):
        return pool

    assert grab() is grab()


def test_provider_with_singleton_annotation(di):
    @inject
    def grab(pool: Singleton[DBPool]):
        return pool

    assert grab() is grab()


def test_provider_with_factory_annotation(di):
    @inject
    def grab(pool: Factory[DBPool]):
        return pool

    assert grab() is not grab()


# --- provide() overrides @provider ---


class OverrideTarget:
    from_provider: bool = False


@provider(OverrideTarget)
def make_override_target():
    t = OverrideTarget()
    t.from_provider = True
    return t


def test_provide_overrides_provider(di):
    @inject
    def grab(t: Singleton[OverrideTarget]):
        return t

    # Without override: uses @provider
    assert grab().from_provider is True

    # With override: provide() wins
    manual = OverrideTarget()
    manual.from_provider = False
    with provide(manual):
        assert grab().from_provider is False

    # After scope exits: back to @provider
    assert grab().from_provider is True


def test_provide_class_overrides_provider():
    class Sub(OverrideTarget):
        pass

    with provide(OverrideTarget=Sub):

        @inject
        def grab(t: Singleton[OverrideTarget]):
            return t

        assert isinstance(grab(), Sub)


# --- Duplicate registration ---


def test_duplicate_provider_raises():
    class Unique:
        pass

    @provider(Unique)
    def first():
        return Unique()

    with pytest.raises(ValueError, match="Duplicate"):

        @provider(Unique)
        def second():
            return Unique()

    # Clean up so other tests aren't affected
    from diny import _providers

    del _providers[Unique]


# --- Provider with injected deps ---


class DepA:
    pass


class DepB:
    def __init__(self, a: Singleton[DepA]):
        self.a = a


class Built:
    b: Any = None


@provider(Built)
def make_built(b: Singleton[DepB]):
    obj = Built()
    obj.b = b
    return obj


def test_provider_deps_injected(di):
    @inject
    def grab(x: Built):
        return x

    x = grab()
    assert isinstance(x.b, DepB)
    assert isinstance(x.b.a, DepA)


def test_provider_deps_shared_with_other_singletons(di):
    @inject
    def grab(x: Built, a: Singleton[DepA]):
        return x, a

    x, a = grab()
    assert x.b.a is a


# --- Interaction with @singleton decorator ---


@singleton
class DecoratedService:
    pass


class ServiceConsumer:
    svc: Any = None


@provider(ServiceConsumer)
def make_consumer(svc: DecoratedService):
    obj = ServiceConsumer()
    obj.svc = svc
    return obj


def test_provider_consumes_singleton_decorated(di):
    @inject
    def grab(c: ServiceConsumer):
        return c

    c1 = grab()
    c2 = grab()
    assert c1 is c2  # provider defaults to singleton
    assert isinstance(c1.svc, DecoratedService)


def test_provider_and_singleton_share_instances(di):
    @inject
    def grab(c: ServiceConsumer, svc: DecoratedService):
        return c, svc

    c, svc = grab()
    assert c.svc is svc


# --- Async ---


class AsyncTarget:
    async_built: bool = False


@provider(AsyncTarget)
async def make_async_target():
    await asyncio.sleep(0)
    t = AsyncTarget()
    t.async_built = True
    return t


def test_async_provider_in_aprovide():
    @inject
    async def grab(t: AsyncTarget):
        return t

    async def main():
        async with aprovide():
            return await grab()

    t = asyncio.run(main())
    assert t.async_built is True


def test_async_provider_errors_in_sync(di):
    @inject
    def grab(t: AsyncTarget):
        return t

    with pytest.raises(RuntimeError, match="async"):
        grab()


# --- String forward references ---


class Widget:
    source: str = ""

    @provider("Widget")
    @classmethod
    def create(cls):
        w = cls()
        w.source = "classmethod"
        return w


def test_string_forward_ref_classmethod(di):
    @inject
    def grab(w: Widget):
        return w

    w = grab()
    assert isinstance(w, Widget)
    assert w.source == "classmethod"


def test_string_forward_ref_singleton(di):
    @inject
    def grab(w: Singleton[Widget]):
        return w

    assert grab() is grab()


def test_string_forward_ref_factory(di):
    @inject
    def grab(w: Factory[Widget]):
        return w

    assert grab() is not grab()


class Connection:
    url: str = ""


@provider("Connection")
def make_connection(config: Singleton[DBConfig]):
    c = Connection()
    c.url = config.url
    return c


def test_string_forward_ref_standalone(di):
    @inject
    def grab(c: Connection):
        return c

    c = grab()
    assert isinstance(c, Connection)
    assert c.url == "default"


def test_string_forward_ref_with_provide_override(di):
    @inject
    def grab(c: Connection):
        return c

    manual = Connection()
    manual.url = "override"
    with provide(manual):
        assert grab().url == "override"

    assert grab().url == "default"


def test_string_forward_ref_duplicate_raises():
    class Ephemeral:
        pass

    @provider("Ephemeral")
    def first():
        return Ephemeral()

    with pytest.raises(ValueError, match="Duplicate"):

        @provider("Ephemeral")
        def second():
            return Ephemeral()

    from diny import _deferred_providers

    _deferred_providers.pop("Ephemeral", None)


def test_deferred_collides_with_direct_provider():
    """A string forward ref that resolves to a type already registered via @provider(Type)."""

    class Collider:
        pass

    from diny import _deferred_providers, _providers

    # Simulate: someone registered @provider("Collider") in one module
    _deferred_providers["Collider"] = lambda: Collider()
    # And @provider(Collider) directly in another
    _providers[Collider] = lambda: Collider()

    with pytest.raises(ValueError, match="Duplicate"):
        # Trigger deferred resolution
        from diny import _resolve_deferred

        _resolve_deferred(Collider)

    # Clean up
    _providers.pop(Collider, None)
    _deferred_providers.pop("Collider", None)
