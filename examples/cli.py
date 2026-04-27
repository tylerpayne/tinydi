"""
CLI where main() just declares what it needs. The argument parser
is built elsewhere and injected as a dependency.

    python examples/cli.py
    python examples/cli.py --db postgres://prod/app --count 3 --verbose
"""

import argparse

from diny import inject, provider, singleton


@singleton
class Args:
    db: str = "sqlite:///default.db"
    count: int = 5
    verbose: bool = False


@provider(Args)
def parse_args() -> Args:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db")
    parser.add_argument("--count", type=int)
    parser.add_argument("--verbose", action="store_true")
    return parser.parse_args(namespace=Args())


@singleton
class Database:
    def __init__(self, args: Args):
        self.url = args.db

    def execute(self, sql: str) -> None:
        print(f"  [{self.url}] {sql}")


@inject
def main(args: Args, db: Database) -> None:
    if args.verbose:
        print(f"  connecting to {db.url}")

    for i in range(args.count):
        db.execute(f"INSERT INTO users VALUES ({i})")

    print(f"  inserted {args.count} rows")


if __name__ == "__main__":
    main()
