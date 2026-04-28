```
diny
       __      
  .^^^/o_)   dead simple         
 / ____/     dependency injection
</|_|_|      in python           
                                 
$ pip install diny               
```

[![PyPI](https://img.shields.io/pypi/v/diny)](https://pypi.org/project/diny/)

## Works with your existing code

Drop in `@singleton` / `@inject` and delete your glue code:

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

-# Lots of lines of glue code
-config = ...
-db = ...
-
-list_users(db)
+list_users()   # Config and Database built on first call, cached after
```

The cache is process-wide until you [scope it](#providers).

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

## Custom providers

For types you don't own or that need custom construction, use `@provider(Type)`:

```python
from diny import provider

@provider(Database)
def make_db(config: Config):
    return PostgresDB(config.url, pool_size=10)

# Now Database is auto-injected using make_db — no provide() needed
list_users()
```

The provider function's own typed parameters are injected too. Scope is determined by the call site (`Singleton[T]` / `Factory[T]`), defaulting to singleton. `provide()` overrides `@provider` within its scope.

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

## Scoped overrides

Open a scope with `provide()` to override any dependency — classes, instances, or functions. This overrides both `@singleton`/`@factory` and `@provider` registrations within the scope:

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

Scopes nest. Use `inherit=True` to keep the parent's cached instances while overriding specific deps:

```python
with provide(Config(url="prod")):
    handler()                          # prod config, fresh database

    with provide(Database=AdminDB, inherit=True):
        handler()                      # admin database, same config instance

    with provide(Config(url="test")):
        handler()                      # test config, fresh everything
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
