"""Tests for provide(): class overrides, instance overrides, callable providers, nesting."""

import pytest

from diny import Factory, Singleton, inject, provide


class Config:
    def __init__(self):
        self.url = "default"


class Database:
    def __init__(self, config: Singleton[Config]):
        self.config = config


class FakeDatabase(Database):
    def __init__(self, config: Singleton[Config]):
        super().__init__(config)
        self.fake = True


# --- Instance overrides ---


def test_instance_override():
    cfg = Config()
    cfg.url = "custom"
    with provide(cfg):

        @inject
        def grab(c: Singleton[Config]):
            return c

        assert grab().url == "custom"


def test_instance_override_inferred_type():
    cfg = Config()
    cfg.url = "inferred"
    with provide(cfg):

        @inject
        def grab(c: Singleton[Config]):
            return c

        assert grab() is cfg


def test_instance_override_with_factory_rebuilds():
    original = Config()
    original.url = "original"
    with provide(original):

        @inject
        def grab(c: Factory[Config]):
            return c

        c = grab()
        assert c is not original
        assert isinstance(c, Config)


# --- Class overrides ---


def test_class_override():
    with provide(Database=FakeDatabase):

        @inject
        def grab(db: Singleton[Database]):
            return db

        db = grab()
        assert isinstance(db, FakeDatabase)
        assert db.fake is True


def test_class_override_inherits_deps():
    cfg = Config()
    cfg.url = "test"
    with provide(cfg, Database=FakeDatabase):

        @inject
        def grab(db: Singleton[Database]):
            return db

        db = grab()
        assert db.config.url == "test"


def test_class_override_with_factory():
    with provide(Database=FakeDatabase):

        @inject
        def grab(a: Factory[Database], b: Factory[Database]):
            return a, b

        a, b = grab()
        assert a is not b
        assert isinstance(a, FakeDatabase)
        assert isinstance(b, FakeDatabase)


# --- Callable providers ---


def test_zero_arg_callable():
    def make_cfg():
        c = Config()
        c.url = "from-fn"
        return c

    with provide(Config=make_cfg):

        @inject
        def grab(c: Singleton[Config]):
            return c

        assert grab().url == "from-fn"


def test_callable_with_injected_deps():
    def make_db(config: Singleton[Config]):
        db = Database.__new__(Database)
        db.config = config
        db.custom = True
        return db

    with provide(Database=make_db):

        @inject
        def grab(db: Singleton[Database]):
            return db

        db = grab()
        assert db.custom is True
        assert isinstance(db.config, Config)


def test_callable_singleton_cached():
    call_count = 0

    def make_cfg():
        nonlocal call_count
        call_count += 1
        return Config()

    with provide(Config=make_cfg):

        @inject
        def grab(c: Singleton[Config]):
            return c

        grab()
        grab()
        assert call_count == 1


def test_callable_factory_called_each_time():
    call_count = 0

    def make_cfg():
        nonlocal call_count
        call_count += 1
        return Config()

    with provide(Config=make_cfg):

        @inject
        def grab(c: Factory[Config]):
            return c

        grab()
        grab()
        grab()
        assert call_count == 3


def test_lambda_provider():
    with provide(Config=lambda: Config()):

        @inject
        def grab(c: Singleton[Config]):
            return c

        assert isinstance(grab(), Config)


# --- Nesting ---


def test_nesting_inner_wins():
    outer = Config()
    outer.url = "outer"
    inner = Config()
    inner.url = "inner"

    with provide(outer):

        @inject
        def grab(c: Singleton[Config]):
            return c

        assert grab().url == "outer"
        with provide(inner):
            assert grab().url == "inner"
        assert grab().url == "outer"


def test_nesting_three_levels():
    @inject
    def grab(c: Singleton[Config]):
        return c.url

    c1, c2, c3 = Config(), Config(), Config()
    c1.url, c2.url, c3.url = "L1", "L2", "L3"

    with provide(c1):
        assert grab() == "L1"
        with provide(c2):
            assert grab() == "L2"
            with provide(c3):
                assert grab() == "L3"
            assert grab() == "L2"
        assert grab() == "L1"


def test_nesting_different_types():
    with provide(Database=FakeDatabase):

        @inject
        def grab(db: Singleton[Database], cfg: Singleton[Config]):
            return db, cfg

        db, cfg = grab()
        assert isinstance(db, FakeDatabase)
        assert cfg.url == "default"

        custom = Config()
        custom.url = "nested"
        with provide(custom):
            db2, cfg2 = grab()
            assert isinstance(db2, FakeDatabase)
            assert cfg2.url == "nested"


def test_empty_provide_creates_fresh_scope():
    @inject
    def grab(c: Singleton[Config]):
        return c

    with provide():
        a = grab()
    with provide():
        b = grab()

    assert a is not b


def test_outer_registration_visible_in_inner():
    cfg = Config()
    cfg.url = "outer"

    with provide(cfg):
        with provide():

            @inject
            def grab(c: Singleton[Config]):
                return c

            assert grab().url == "outer"


def test_string_key_not_found_raises():
    """provide(SomeString=val) where SomeString isn't a name in any caller frame."""
    with pytest.raises(NameError):
        with provide(NoSuchTypeAnywhere=lambda: None):
            pass
