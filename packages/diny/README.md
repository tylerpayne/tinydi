# diny

[![PyPI](https://img.shields.io/pypi/v/diny)](https://pypi.org/project/diny/)

Dead simple dependency injection for Python.

```bash
pip install diny
```

## Just works

Drop in `@singleton` / `@inject` and delete your orchestration, lifecycle, and wiring code:

```diff
+from diny import inject, singleton
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

## Decorators

`@singleton` caches one instance per scope. `@factory` builds a fresh one at each site. `@inject` resolves a function's typed deps on call.

```python
from diny import inject, singleton, factory
from uuid import uuid4

@singleton
class Database:
    def __init__(self, config: Config): ...

@factory
class RequestId:
    def __init__(self): self.value = uuid4()

@inject
def handler(db: Database, req: RequestId):
    # db is cached across calls; req is fresh every time
    ...
```

Plain params pass through untouched:

```python
@inject
def get_user(user_id: int, db: Database):
    return db.query("SELECT * FROM users WHERE id = %s", user_id)

get_user(42)
```

## Annotations

For classes you don't own — or to override a class's default scope at one call site — use `Singleton[T]` / `Factory[T]`:

```python
from diny import Singleton, Factory

@inject
def handler(
    client: Singleton[ThirdPartyClient],   # cached
    id_a:   Factory[RequestId],            # fresh
    id_b:   Factory[RequestId],            # fresh, different instance
):
    ...
```

Site annotations beat class decorators — `Singleton[RequestId]` forces singleton even if `RequestId` is `@factory`.

Undecorated classes without a site annotation are passed through to the caller. Nothing is auto-injected behind your back.

## Providers

Open a scope with `provide()` to override any dep — classes, instances, or factory functions:

```python
from diny import provide

class FakeDatabase(Database):
    def __init__(self, config: Config):
        self.fake = True

with provide(Database=FakeDatabase):
    list_users()                     # uses FakeDatabase

with provide(Config(url="test://")):
    list_users()                     # uses this Config instance
```

A provider can be a function — its own typed deps get injected too:

```python
def make_db(config: Config):
    return PostgresDB(config.url, pool_size=10)

with provide(Database=make_db):
    list_users()
```

Scopes nest:

```python
with provide(Config(url="prod")):
    handler()                          # prod
    with provide(Config(url="test")):
        handler()                      # test
    handler()                          # prod again
```

### Async

```python
from diny import inject, aprovide

@inject
async def handler(db: Database):
    return await db.fetch_all()

async def main():
    async with aprovide():
        await handler()
```

Async provider functions work inside `aprovide`:

```python
async def make_pool(config: Config):
    return await asyncpg.create_pool(config.url)

async with aprovide(Pool=make_pool):
    await handler()
```
