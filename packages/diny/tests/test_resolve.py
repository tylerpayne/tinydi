"""Tests for resolve() / aresolve() public API."""

import asyncio

import pytest

from diny import Factory, Singleton, aresolve, inject, provide, resolve, singleton


@singleton
class Config:
    def __init__(self):
        self.url = "default"


@singleton
class Database:
    def __init__(self, config: Config):
        self.config = config


def test_resolve_basic(di):
    cfg = resolve(Config)
    assert isinstance(cfg, Config)
    assert cfg.url == "default"


def test_resolve_caches(di):
    assert resolve(Config) is resolve(Config)


def test_resolve_with_deps(di):
    db = resolve(Database)
    assert isinstance(db, Database)
    assert isinstance(db.config, Config)
    assert db.config is resolve(Config)


def test_resolve_respects_provide():
    custom = Config()
    custom.url = "custom"
    with provide(custom):
        assert resolve(Config).url == "custom"
        assert resolve(Config) is custom


def test_resolve_different_scopes():
    with provide():
        a = resolve(Config)
    with provide():
        b = resolve(Config)
    assert a is not b


def test_resolve_singleton_decorated(di):
    @singleton
    class Service:
        pass

    a = resolve(Service)
    b = resolve(Service)
    assert a is b


def test_resolve_matches_inject(di):
    @inject
    def grab(cfg: Config):
        return cfg

    assert resolve(Config) is grab()


def test_aresolve_basic():
    async def main():
        from diny import aprovide

        async with aprovide():
            cfg = await aresolve(Config)
            assert isinstance(cfg, Config)
            return cfg

    asyncio.run(main())


def test_aresolve_caches():
    async def main():
        from diny import aprovide

        async with aprovide():
            a = await aresolve(Config)
            b = await aresolve(Config)
            assert a is b

    asyncio.run(main())


def test_aresolve_respects_provide():
    async def main():
        from diny import aprovide

        custom = Config()
        custom.url = "async-custom"
        async with aprovide(custom):
            cfg = await aresolve(Config)
            assert cfg.url == "async-custom"

    asyncio.run(main())


# --- Annotated resolve ---


def test_resolve_factory(di):
    a = resolve(Factory[Config])
    b = resolve(Factory[Config])
    assert a is not b
    assert isinstance(a, Config)


def test_resolve_singleton_annotation(di):
    a = resolve(Singleton[Config])
    b = resolve(Singleton[Config])
    assert a is b


def test_resolve_factory_vs_singleton(di):
    s = resolve(Singleton[Config])
    f = resolve(Factory[Config])
    assert s is not f
    assert resolve(Singleton[Config]) is s


def test_aresolve_factory():
    async def main():
        from diny import aprovide

        async with aprovide():
            a = await aresolve(Factory[Config])
            b = await aresolve(Factory[Config])
            assert a is not b

    asyncio.run(main())


def test_aresolve_singleton_annotation():
    async def main():
        from diny import aprovide

        async with aprovide():
            a = await aresolve(Singleton[Config])
            b = await aresolve(Singleton[Config])
            assert a is b

    asyncio.run(main())


# --- Unregistered types ---


def test_resolve_unregistered_raises(di):
    class Plain:
        pass

    with pytest.raises(TypeError, match="not registered"):
        resolve(Plain)


def test_aresolve_unregistered_raises():
    class Plain:
        pass

    async def main():
        from diny import aprovide

        async with aprovide():
            await aresolve(Plain)

    with pytest.raises(TypeError, match="not registered"):
        asyncio.run(main())
