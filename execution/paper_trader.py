from strategy.dip_buy import Lot


class PaperTrader:
    def __init__(self, initial_balance_usd: float = 10_000.0):
        self.balance_usd: float = initial_balance_usd
        self.trades: list[dict] = []

    def buy(self, lot: Lot) -> None:
        cost = lot.entry_price * lot.quantity
        self.balance_usd -= cost
        self.trades.append({
            "action": "BUY",
            "lot_id": lot.id,
            "price": lot.entry_price,
            "quantity": lot.quantity,
            "pnl_usd": 0.0,
        })

    def sell(self, lot: Lot, price: float, reason: str = "SELL") -> float:
        proceeds = price * lot.quantity
        pnl = proceeds - (lot.entry_price * lot.quantity)
        self.balance_usd += proceeds
        self.trades.append({
            "action": "SELL",
            "lot_id": lot.id,
            "price": price,
            "quantity": lot.quantity,
            "pnl_usd": pnl,
            "reason": reason,
        })
        return pnl
