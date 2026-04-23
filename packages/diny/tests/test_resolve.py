"""Tests for resolve() / aresolve() public API."""

import asyncio

from diny import Singleton, aresolve, inject, provide, resolve, singleton


class Config:
    def __init__(self):
        self.url = "default"


class Database:
    def __init__(self, config: Singleton[Config]):
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
    def grab(cfg: Singleton[Config]):
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
