"""
Swap implementations at startup. Handlers don't know which one they got.

    python examples/polymorphism.py
    USE_ELASTIC=1 python examples/polymorphism.py
"""

import os

from diny import inject, provide, singleton


@singleton
class Search:
    def query(self, term: str) -> list[str]:
        raise NotImplementedError


class ElasticSearch(Search):
    def query(self, term: str) -> list[str]:
        return [f"elastic:{term}:result1", f"elastic:{term}:result2"]


class SQLiteSearch(Search):
    def query(self, term: str) -> list[str]:
        return [f"sqlite:{term}:result1"]


@inject
def search_products(term: str, search: Search) -> list[str]:
    return search.query(term)


@inject
def autocomplete(prefix: str, search: Search) -> list[str]:
    return search.query(prefix)[:1]


if __name__ == "__main__":
    backend = ElasticSearch if os.environ.get("USE_ELASTIC") else SQLiteSearch

    with provide(Search=backend):
        print(f"  search:       {search_products('shoes')}")
        print(f"  autocomplete: {autocomplete('sho')}")
