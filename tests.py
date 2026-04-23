"""Smoke tests for the annotation-based API."""
import asyncio
from tinydi import inject, provide, aprovide, Singleton, Factory


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


# Mixed: one site wants singleton, another wants fresh
@inject
def mixed_scope(a: Singleton[RequestId], b: Singleton[RequestId], c: Factory[RequestId]):
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
    def __init__(self, other: "Singleton[SelfCycle]"): self.other = other

@inject
def cyclic(x: Singleton[SelfCycle]): return x


def run():
    with provide():
        assert handler() == "postgres://localhost"
    print("  basic wiring ok")

    with provide():
        assert with_arg(42) == "user=42 url=postgres://localhost"
    print("  mixed args ok")

    with provide():
        a, b = two_ids()
        assert a != b, f"Factory should give distinct instances, got {a} and {b}"
    print("  Factory annotation ok")

    with provide():
        a, b, c = mixed_scope()
        assert a == b, "Singleton sites should share a singleton"
        assert c != a, "Factory site should get a fresh instance"
    print("  mixed Singleton + Factory on same type ok")

    # Factory overrides registered instance: rebuild from the instance's type.
    pre_built = RequestId()
    with provide(pre_built):
        @inject
        def grab(x: Singleton[RequestId], y: Factory[RequestId]):
            return x, y
        x, y = grab()
        assert x is pre_built, "Singleton should return the registered instance"
        assert y is not pre_built, "Factory should rebuild, not return the instance"
        assert isinstance(y, RequestId), "Factory rebuild should produce same type"
    print("  Factory overrides registered instance ok")

    custom = Config()
    custom.url = "test://"
    with provide(custom):
        assert handler() == "test://"
    print("  instance override ok")

    with provide(Database=FakeDatabase):
        @inject
        def check(db: Singleton[Database]):
            return getattr(db, "fake", False)
        assert check() is True
    print("  class override ok")

    outer = Config(); outer.url = "outer"
    inner = Config(); inner.url = "inner"
    with provide(outer):
        with provide(inner):
            assert handler() == "inner"
        assert handler() == "outer"
    print("  nesting ok")

    async def amain():
        async with aprovide():
            return await ahandler()
    assert asyncio.run(amain()) == "postgres://localhost"
    print("  async ok")

    with provide():
        try:
            cyclic()
        except RuntimeError as e:
            assert "Circular" in str(e)
            print("  cycle detection ok")
        else:
            raise AssertionError("should have raised")

    @inject
    def not_injected(x: int):
        return x
    with provide():
        assert not_injected(5) == 5
    print("  plain-typed params untouched ok")

    # Caller override of an injectable param
    with provide():
        custom_repo = UserRepo(Database(Config()))
        assert with_arg(1, repo=custom_repo).startswith("user=1")
    print("  caller override of injected param ok")

    # Callable provider: zero-arg factory function
    with provide(Config=lambda: Config()):
        @inject
        def grab_cfg(c: Singleton[Config]):
            return c
        cfg = grab_cfg()
        assert cfg.url == "postgres://localhost"
    print("  zero-arg callable provider ok")

    # Callable provider with DI-resolved params
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
    print("  callable provider with DI-resolved args ok")

    # Callable provider with Factory at site: called fresh each time
    call_count = {"n": 0}
    def make_rid():
        call_count["n"] += 1
        r = RequestId.__new__(RequestId)
        r.value = call_count["n"] + 1000  # distinct from class-built ones
        return r

    with provide(RequestId=make_rid):
        @inject
        def two(a: Factory[RequestId], b: Factory[RequestId]):
            return a.value, b.value
        va, vb = two()
        assert va != vb, "factory provider should be called twice"
    print("  callable provider honored by Factory ok")

    # Async callable provider
    async def make_db_async(config: Singleton[Config]):
        await asyncio.sleep(0)
        db = Database.__new__(Database)
        db.config = config
        db.async_built = True
        return db

    async def amain2():
        async with aprovide(Database=make_db_async):
            @inject
            async def grab(db: Singleton[Database]):
                return db
            return await grab()

    result = asyncio.run(amain2())
    assert result.async_built
    print("  async callable provider ok")

    # Sync path rejects async providers loudly
    with provide(Database=make_db_async):
        @inject
        def grab_sync(db: Singleton[Database]):
            return db
        try:
            grab_sync()
        except RuntimeError as e:
            assert "async" in str(e)
            print("  async provider in sync path errors clearly ok")

    # Class decorators: bare annotations get auto-injected with marked scope
    from tinydi import singleton, factory as factory_decorator

    @singleton
    class Service:
        def __init__(self, config: Singleton[Config]):
            self.config = config

    @factory_decorator
    class Token:
        counter = 0
        def __init__(self):
            Token.counter += 1
            self.n = Token.counter

    @inject
    def bare_handler(svc: Service, t1: Token, t2: Token):
        return svc.config.url, t1.n, t2.n

    with provide():
        url, n1, n2 = bare_handler()
        assert url == "postgres://localhost"
        assert n1 != n2, "@factory class should give fresh instances"
    print("  @singleton / @factory class decorators ok")

    # Site annotation overrides class default
    @inject
    def override_handler(t_same: Singleton[Token]):
        # Token is @factory at class level, but Singleton[] at site → singleton here
        return t_same

    with provide():
        a = override_handler()
        b = override_handler()
        assert a is b, "site Singleton[] should override class @factory"
    print("  site annotation overrides class decorator ok")

    # Undecorated plain type still passes through to caller
    class Plain: pass
    @inject
    def no_decorator(x: Plain):  # Plain has no @singleton/@factory
        return x
    with provide():
        p = Plain()
        assert no_decorator(p) is p   # caller must supply
    print("  undecorated bare type still caller-supplied ok")

    print("\nall smoke tests passed")


if __name__ == "__main__":
    run()
