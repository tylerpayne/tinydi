# tinydi

Dependency injection in 180 lines. Annotations, not containers.

## Just works

Drop in `@singleton` / `@inject` and delete the wiring:

```diff
+from tinydi import inject, singleton
+
+@singleton
 class Config:
     def __init__(self):
         self.url = "postgres://localhost"

+@singleton
 class Database:
     def __init__(self, config: Config):
         self.conn = connect(config.url)

+@inject
 def list_users(db: Database):
     return db.query("SELECT * FROM users")

-# Lots of lines of orchestration and lifecycle code
-config = ...
-db = ...
-
-list_users(db)
+list_users()   # Config and Database built on first call, cached after
```

No `provide()` needed — the cache is process-wide until you scope it.

## Mix injected and regular params

```python
@inject
def get_user(user_id: int, db: Singleton[Database]):
    return db.query("SELECT * FROM users WHERE id = %s", user_id)

get_user(42)
```

## Singleton vs Factory

```python
from uuid import uuid4

class RequestId:
    def __init__(self):
        self.value = uuid4()

@inject
def handler(
    session: Singleton[RequestId],   # same value across the scope
    op_id:   Factory[RequestId],     # fresh each injection
):
    ...
```

## Mark the class instead

For classes that are always one scope, decorate and drop the brackets:

```python
from tinydi import singleton, factory

@singleton
class Database:
    def __init__(self, config: Singleton[Config]): ...

@factory
class RequestId:
    def __init__(self): self.value = uuid4()

@inject
def handler(db: Database, req: RequestId):   # no brackets needed
    ...
```

Site annotations still win when both are set — `Singleton[RequestId]` forces singleton even if the class is `@factory`.

## Override for tests

```python
from tinydi import provide

class FakeDatabase(Database):
    def __init__(self, config: Singleton[Config]):
        self.fake = True

with provide(Database=FakeDatabase):
    list_users()   # uses FakeDatabase

with provide(Config(url="test://")):
    list_users()   # uses the test config
```

## Factory functions as providers

```python
def make_db(config: Singleton[Config]):
    return PostgresDB(config.url, pool_size=10)

with provide(Database=make_db):
    list_users()
```

The function's own `Singleton[]` params are injected.

## Nesting

```python
with provide(Config(url="prod")):
    handler()                          # prod
    with provide(Config(url="test")):
        handler()                      # test
    handler()                          # prod again
```

## Async

```python
from tinydi import inject, aprovide, Singleton

@inject
async def handler(db: Singleton[Database]):
    return await db.fetch_all()

async def main():
    async with aprovide():
        await handler()
```

Async provider functions work in async scopes:

```python
async def make_pool(config: Singleton[Config]):
    return await asyncpg.create_pool(config.url)

async with aprovide(Pool=make_pool):
    await handler()
```

## pytest

```python
@pytest.fixture
def di():
    with provide(Database=FakeDatabase):
        yield

def test_users(di):
    list_users()
```

## Resolution

For a site requesting `T`:

| Registry contains | `Singleton[T]` | `Factory[T]` |
|---|---|---|
| nothing | build T, cache | build T |
| class `C` | build C, cache | build C |
| callable `f` | call f, cache | call f |
| instance `i` | return i | build `type(i)` |

## Out of scope

Lifecycle hooks, config loading, named deps, framework glue, string forward refs. Pass resources in, use `with` for cleanup, use real types.

## License

MIT.
