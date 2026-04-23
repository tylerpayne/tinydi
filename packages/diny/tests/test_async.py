"""Tests for async support: @inject on coroutines, aprovide(), async providers."""

import asyncio

import pytest

from diny import Factory, Singleton, aprovide, inject, provide, singleton


class Config:
    def __init__(self):
        self.url = "default"


class Database:
    def __init__(self, config: Singleton[Config]):
        self.config = config


# --- Basic async inject ---


def test_async_inject():
    @inject
    async def grab(c: Singleton[Config]):
        return c.url

    async def main():
        async with aprovide():
            return await grab()

    assert asyncio.run(main()) == "default"


def test_async_inject_with_plain_params():
    @inject
    async def f(x: int, c: Singleton[Config]):
        return x, c.url

    async def main():
        async with aprovide():
            return await f(42)

    assert asyncio.run(main()) == (42, "default")


def test_async_inject_caller_override():
    @inject
    async def f(c: Singleton[Config]):
        return c.url

    async def main():
        async with aprovide():
            custom = Config()
            custom.url = "override"
            return await f(c=custom)

    assert asyncio.run(main()) == "override"


def test_async_inject_factory():
    @inject
    async def f(a: Factory[Config], b: Factory[Config]):
        return a, b

    async def main():
        async with aprovide():
            return await f()

    a, b = asyncio.run(main())
    assert a is not b


# --- aprovide with overrides ---


def test_aprovide_instance_override():
    @inject
    async def grab(c: Singleton[Config]):
        return c.url

    async def main():
        cfg = Config()
        cfg.url = "async-custom"
        async with aprovide(cfg):
            return await grab()

    assert asyncio.run(main()) == "async-custom"


def test_aprovide_class_override():
    class FakeDB(Database):
        def __init__(self, config: Singleton[Config]):
            super().__init__(config)
            self.fake = True

    @inject
    async def grab(db: Singleton[Database]):
        return db

    async def main():
        async with aprovide(Database=FakeDB):
            return await grab()

    db = asyncio.run(main())
    assert isinstance(db, FakeDB)
    assert db.fake is True


def test_aprovide_nesting():
    @inject
    async def grab(c: Singleton[Config]):
        return c.url

    async def main():
        c1, c2 = Config(), Config()
        c1.url, c2.url = "outer", "inner"
        async with aprovide(c1):
            outer = await grab()
            async with aprovide(c2):
                inner = await grab()
            restored = await grab()
        return outer, inner, restored

    assert asyncio.run(main()) == ("outer", "inner", "outer")


# --- Async callable providers ---


def test_async_callable_provider():
    async def make_db(config: Singleton[Config]):
        await asyncio.sleep(0)
        db = Database.__new__(Database)
        db.config = config
        db.async_built = True
        return db

    @inject
    async def grab(db: Singleton[Database]):
        return db

    async def main():
        async with aprovide(Database=make_db):
            return await grab()

    db = asyncio.run(main())
    assert db.async_built is True
    assert isinstance(db.config, Config)


def test_async_callable_provider_cached():
    call_count = 0

    async def make_cfg():
        nonlocal call_count
        call_count += 1
        return Config()

    @inject
    async def grab(c: Singleton[Config]):
        return c

    async def main():
        async with aprovide(Config=make_cfg):
            await grab()
            await grab()

    asyncio.run(main())
    assert call_count == 1


def test_async_callable_provider_factory():
    call_count = 0

    async def make_cfg():
        nonlocal call_count
        call_count += 1
        return Config()

    @inject
    async def grab(c: Factory[Config]):
        return c

    async def main():
        async with aprovide(Config=make_cfg):
            a = await grab()
            b = await grab()
            return a, b

    a, b = asyncio.run(main())
    assert a is not b
    assert call_count == 2


def test_async_provider_in_sync_context_errors():
    async def make_cfg():
        return Config()

    with provide(Config=make_cfg):

        @inject
        def grab(c: Singleton[Config]):
            return c

        with pytest.raises(RuntimeError, match="async"):
            grab()


def test_sync_provider_in_async_context():
    def make_cfg():
        c = Config()
        c.url = "sync-in-async"
        return c

    @inject
    async def grab(c: Singleton[Config]):
        return c.url

    async def main():
        async with aprovide(Config=make_cfg):
            return await grab()

    assert asyncio.run(main()) == "sync-in-async"


# --- @singleton decorator in async ---


def test_singleton_decorator_async(di):
    @singleton
    class Service:
        pass

    @inject
    async def grab(s: Service):
        return s

    async def main():
        async with aprovide():
            a = await grab()
            b = await grab()
            return a, b

    a, b = asyncio.run(main())
    assert a is b


def test_preserves_coroutine_metadata():
    @inject
    async def my_async_func(c: Singleton[Config]):
        """Async docstring."""
        pass

    assert my_async_func.__name__ == "my_async_func"
    assert my_async_func.__doc__ == "Async docstring."


# --- Async circular dependency ---


class AsyncSelfRef:
    def __init__(self, other: "Singleton[AsyncSelfRef]"):
        self.other = other


def test_async_circular_dependency():
    @inject
    async def grab(x: Singleton[AsyncSelfRef]):
        return x

    async def main():
        async with aprovide():
            return await grab()

    with pytest.raises(RuntimeError, match="Circular"):
        asyncio.run(main())


# --- Async factory over instance ---


def test_async_factory_over_instance():
    @inject
    async def grab(c: Factory[Config]):
        return c

    async def main():
        original = Config()
        original.url = "original"
        async with aprovide(original):
            c = await grab()
            return c, original

    c, original = asyncio.run(main())
    assert c is not original
    assert isinstance(c, Config)
