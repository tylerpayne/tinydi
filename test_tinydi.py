"""Smoke tests for the annotation-based API."""

import asyncio

import pytest

from tinydi import Factory, Singleton, aprovide, factory, inject, provide, singleton


class Config:
    def __init__(self):
        self.url = "postgres://localhost"


class Database:
    def __init__(self, config: Singleton[Config]):
        self.config = config


class UserRepo:
    def __init__(self, db: Singleton[Database]):
        self.db = db


class OrderRepo:
    def __init__(self, db: Singleton[Database]):
        self.db = db


@inject
def handler(users: Singleton[UserRepo], orders: Singleton[OrderRepo]):
    assert users.db is orders.db, "shared dep should be cached"
    return users.db.config.url


@inject
def with_arg(user_id: int, repo: Singleton[UserRepo]):
    return f"user={user_id} url={repo.db.config.url}"


counter = {"n": 0}


class RequestId:
    def __init__(self):
        counter["n"] += 1
        self.value = counter["n"]


@inject
def two_ids(a: Factory[RequestId], b: Factory[RequestId]):
    return a.value, b.value


@inject
def mixed_scope(
    a: Singleton[RequestId], b: Singleton[RequestId], c: Factory[RequestId]
):
    return a.value, b.value, c.value


class FakeDatabase(Database):
    def __init__(self, config: Singleton[Config]):
        self.config = config
        self.fake = True


@inject
async def ahandler(users: Singleton[UserRepo]):
    await asyncio.sleep(0)
    return users.db.config.url


class SelfCycle:
    def __init__(self, other: "Singleton[SelfCycle]"):
        self.other = other


@inject
def cyclic(x: Singleton[SelfCycle]):
    return x


@singleton
class Service:
    def __init__(self, config: Singleton[Config]):
        self.config = config


@factory
class Token:
    counter = 0

    def __init__(self):
        Token.counter += 1
        self.n = Token.counter


@pytest.fixture
def di():
    with provide():
        yield


def test_basic_wiring(di):
    assert handler() == "postgres://localhost"


def test_mixed_args(di):
    assert with_arg(42) == "user=42 url=postgres://localhost"


def test_factory_annotation(di):
    a, b = two_ids()
    assert a != b, f"Factory should give distinct instances, got {a} and {b}"


def test_mixed_singleton_and_factory(di):
    a, b, c = mixed_scope()
    assert a == b, "Singleton sites should share a singleton"
    assert c != a, "Factory site should get a fresh instance"


def test_factory_overrides_registered_instance():
    pre_built = RequestId()
    with provide(pre_built):

        @inject
        def grab(x: Singleton[RequestId], y: Factory[RequestId]):
            return x, y

        x, y = grab()
        assert x is pre_built, "Singleton should return the registered instance"
        assert y is not pre_built, "Factory should rebuild, not return the instance"
        assert isinstance(y, RequestId), "Factory rebuild should produce same type"


def test_instance_override():
    custom = Config()
    custom.url = "test://"
    with provide(custom):
        assert handler() == "test://"


def test_class_override():
    with provide(Database=FakeDatabase):

        @inject
        def check(db: Singleton[Database]):
            return getattr(db, "fake", False)

        assert check() is True


def test_nesting():
    outer = Config()
    outer.url = "outer"
    inner = Config()
    inner.url = "inner"
    with provide(outer):
        with provide(inner):
            assert handler() == "inner"
        assert handler() == "outer"


def test_async():
    async def amain():
        async with aprovide():
            return await ahandler()

    assert asyncio.run(amain()) == "postgres://localhost"


def test_cycle_detection(di):
    with pytest.raises(RuntimeError, match="Circular"):
        cyclic()


def test_plain_params_untouched(di):
    @inject
    def not_injected(x: int):
        return x

    assert not_injected(5) == 5


def test_caller_override_of_injected_param(di):
    custom_repo = UserRepo(Database(Config()))
    assert with_arg(1, repo=custom_repo).startswith("user=1")


def test_zero_arg_callable_provider():
    with provide(Config=lambda: Config()):

        @inject
        def grab_cfg(c: Singleton[Config]):
            return c

        cfg = grab_cfg()
        assert cfg.url == "postgres://localhost"


def test_callable_provider_with_di_resolved_args():
    def make_db(config: Singleton[Config]):
        db = Database.__new__(Database)
        db.config = config
        db.built_via_fn = True
        return db

    with provide(Database=make_db):

        @inject
        def grab_db(db: Singleton[Database]):
            return db

        db1 = grab_db()
        db2 = grab_db()
        assert db1 is db2, "singleton: should cache"
        assert db1.built_via_fn, "should come from factory fn"


def test_callable_provider_honored_by_factory():
    call_count = {"n": 0}

    def make_rid():
        call_count["n"] += 1
        r = RequestId.__new__(RequestId)
        r.value = call_count["n"] + 1000
        return r

    with provide(RequestId=make_rid):

        @inject
        def two(a: Factory[RequestId], b: Factory[RequestId]):
            return a.value, b.value

        va, vb = two()
        assert va != vb, "factory provider should be called twice"


def test_async_callable_provider():
    async def make_db_async(config: Singleton[Config]):
        await asyncio.sleep(0)
        db = Database.__new__(Database)
        db.config = config
        db.async_built = True
        return db

    async def amain():
        async with aprovide(Database=make_db_async):

            @inject
            async def grab(db: Singleton[Database]):
                return db

            return await grab()

    result = asyncio.run(amain())
    assert result.async_built


def test_async_provider_in_sync_path_errors():
    async def make_db_async(config: Singleton[Config]):
        db = Database.__new__(Database)
        db.config = config
        return db

    with provide(Database=make_db_async):

        @inject
        def grab_sync(db: Singleton[Database]):
            return db

        with pytest.raises(RuntimeError, match="async"):
            grab_sync()


def test_class_decorators(di):
    @inject
    def bare_handler(svc: Service, t1: Token, t2: Token):
        return svc.config.url, t1.n, t2.n

    url, n1, n2 = bare_handler()
    assert url == "postgres://localhost"
    assert n1 != n2, "@factory class should give fresh instances"


def test_site_annotation_overrides_class_decorator(di):
    @inject
    def override_handler(t_same: Singleton[Token]):
        return t_same

    a = override_handler()
    b = override_handler()
    assert a is b, "site Singleton[] should override class @factory"


def test_undecorated_bare_type_is_caller_supplied(di):
    class Plain:
        pass

    @inject
    def no_decorator(x: Plain):
        return x

    p = Plain()
    assert no_decorator(p) is p
