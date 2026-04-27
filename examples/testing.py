"""
Testing without mocks. provide() replaces unittest.mock.patch.

    python examples/testing.py
"""

from diny import inject, provide, singleton


@singleton
class PaymentGateway:
    def charge(self, amount: float) -> str:
        raise RuntimeError("Would hit Stripe for real")


@singleton
class Inventory:
    def reserve(self, item: str) -> bool:
        raise RuntimeError("Would hit the warehouse API for real")


@inject
def checkout(
    item: str, price: float, payments: PaymentGateway, stock: Inventory
) -> dict:
    if not stock.reserve(item):
        return {"ok": False, "reason": "out of stock"}
    charge_id = payments.charge(price)
    return {"ok": True, "charge": charge_id, "item": item}


# --- Tests ---


class FakePayments(PaymentGateway):
    def charge(self, amount: float) -> str:
        return f"fake-charge-{amount}"


class FakeInventory(Inventory):
    def __init__(self):
        self.available = {"widget", "gadget"}

    def reserve(self, item: str) -> bool:
        return item in self.available


def test_successful_checkout():
    with provide(PaymentGateway=FakePayments, Inventory=FakeInventory):
        result = checkout("widget", 9.99)
        assert result == {"ok": True, "charge": "fake-charge-9.99", "item": "widget"}


def test_out_of_stock():
    with provide(PaymentGateway=FakePayments, Inventory=FakeInventory):
        result = checkout("unobtainium", 999.99)
        assert result == {"ok": False, "reason": "out of stock"}


if __name__ == "__main__":
    test_successful_checkout()
    print("  test_successful_checkout passed")

    test_out_of_stock()
    print("  test_out_of_stock passed")
