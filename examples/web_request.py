"""
Handler needs auth, which needs users, which needs a database,
all of which need args from CLI. diny builds the whole chain.

    python examples/web_request.py --db postgres://prod/app --secret my-key
"""

import argparse
from dataclasses import dataclass

from diny import inject, provide, provider, singleton


@singleton
@dataclass
class Args:
    db: str = "sqlite:///default.db"
    secret: str = "dev-secret"


@provider(Args)
def parse_args() -> Args:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    parser.add_argument("--secret")
    return parser.parse_args(namespace=Args())


@singleton
class Database:
    def __init__(self, args: Args):
        self.url = args.db

    def query(self, sql: str) -> dict:
        return {"id": 1, "name": "Alice", "role": "admin"}


@singleton
class UserRepo:
    def __init__(self, db: Database):
        self.db = db

    def get(self, user_id: int) -> dict:
        return self.db.query(f"SELECT * FROM users WHERE id = {user_id}")


@singleton
class Auth:
    def __init__(self, users: UserRepo, args: Args):
        self.users = users
        self.secret = args.secret

    def check(self, token: str) -> dict:
        return self.users.get(int(token))


@inject
def handle(token: str, auth: Auth) -> None:
    user = auth.check(token)
    print(f"  user: {user}")
    print(f"  db:   {auth.users.db.url}")
    print(f"  key:  {auth.secret}")


if __name__ == "__main__":
    with provide():
        handle("42")
