"""Investment Portfolio Tracker.

Track and analyze investment portfolios:
- Multi-asset support (stocks, bonds, crypto, ETFs, mutual funds)
- Portfolio creation and management
- Transaction recording (buy/sell/dividend)
- Performance calculation (time-weighted return)
- Asset allocation analysis
- Risk metrics (Sharpe ratio, max drawdown)
- Dividend tracking
- Rebalancing suggestions
"""

import logging
import math
from collections import defaultdict
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

logger = logging.getLogger("finmind.portfolio")


class AssetType(str, Enum):
    STOCK = "stock"
    BOND = "bond"
    CRYPTO = "crypto"
    ETF = "etf"
    MUTUAL_FUND = "mutual_fund"
    REAL_ESTATE = "real_estate"
    COMMODITY = "commodity"


class TransactionType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    DIVIDEND = "dividend"
    SPLIT = "split"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"


class Holding:
    def __init__(self, symbol: str, asset_type: str, name: str = ""):
        self.symbol = symbol
        self.asset_type = asset_type
        self.name = name or symbol
        self.shares = 0.0
        self.total_cost = 0.0
        self.transactions = []

    @property
    def avg_cost(self) -> float:
        return self.total_cost / max(self.shares, 0.0001)

    @property
    def cost_basis(self) -> float:
        return self.total_cost

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "asset_type": self.asset_type,
            "name": self.name,
            "shares": round(self.shares, 6),
            "avg_cost": round(self.avg_cost, 4),
            "total_cost": round(self.total_cost, 2),
            "transaction_count": len(self.transactions),
        }


class Portfolio:
    def __init__(self, portfolio_id: str, name: str, owner_id: str,
                 currency: str = "USD"):
        self.portfolio_id = portfolio_id
        self.name = name
        self.owner_id = owner_id
        self.currency = currency
        self.holdings = {}  # symbol -> Holding
        self.cash_balance = 0.0
        self.created_at = datetime.utcnow().isoformat()

    def to_dict(self):
        return {
            "portfolio_id": self.portfolio_id,
            "name": self.name,
            "owner_id": self.owner_id,
            "currency": self.currency,
            "cash_balance": round(self.cash_balance, 2),
            "holdings": {s: h.to_dict() for s, h in self.holdings.items()},
            "holding_count": len(self.holdings),
            "created_at": self.created_at,
        }


class InvestmentPortfolioService:
    """Investment portfolio management and analytics."""

    def __init__(self):
        self.portfolios = {}

    def create_portfolio(self, name: str, owner_id: str,
                          currency: str = "USD",
                          initial_cash: float = 0) -> dict:
        """Create a new portfolio."""
        pid = str(uuid4())[:8]
        portfolio = Portfolio(pid, name, owner_id, currency)
        portfolio.cash_balance = initial_cash
        self.portfolios[pid] = portfolio
        return portfolio.to_dict()

    def record_transaction(self, portfolio_id: str, symbol: str,
                            transaction_type: str, shares: float,
                            price: float, fee: float = 0,
                            date: str = None, notes: str = "") -> dict:
        """Record a buy/sell/dividend transaction."""
        if portfolio_id not in self.portfolios:
            return {"error": "Portfolio not found"}

        portfolio = self.portfolios[portfolio_id]
        total = shares * price + fee

        tx = {
            "id": str(uuid4())[:8],
            "symbol": symbol,
            "type": transaction_type,
            "shares": shares,
            "price": price,
            "fee": fee,
            "total": round(total, 2),
            "date": date or datetime.utcnow().isoformat(),
            "notes": notes,
        }

        if symbol not in portfolio.holdings:
            portfolio.holdings[symbol] = Holding(symbol, "stock", symbol)

        holding = portfolio.holdings[symbol]

        if transaction_type == TransactionType.BUY.value:
            holding.shares += shares
            holding.total_cost += total
            portfolio.cash_balance -= total

        elif transaction_type == TransactionType.SELL.value:
            if holding.shares < shares:
                return {"error": "Insufficient shares"}
            # FIFO cost basis
            cost_per_share = holding.avg_cost
            holding.shares -= shares
            holding.total_cost -= cost_per_share * shares
            portfolio.cash_balance += shares * price - fee
            if holding.shares <= 0.0001:
                holding.shares = 0
                holding.total_cost = 0

        elif transaction_type == TransactionType.DIVIDEND.value:
            portfolio.cash_balance += shares * price - fee

        holding.transactions.append(tx)
        return {"status": "recorded", "transaction": tx}

    def get_portfolio_value(self, portfolio_id: str,
                             current_prices: dict) -> dict:
        """Calculate total portfolio value with current prices."""
        if portfolio_id not in self.portfolios:
            return {"error": "Portfolio not found"}

        portfolio = self.portfolios[portfolio_id]
        total_value = portfolio.cash_balance
        total_cost = 0
        holdings_value = []

        for symbol, holding in portfolio.holdings.items():
            if holding.shares <= 0:
                continue
            current_price = current_prices.get(symbol, holding.avg_cost)
            market_value = holding.shares * current_price
            gain_loss = market_value - holding.cost_basis
            gain_pct = (gain_loss / max(holding.cost_basis, 0.01)) * 100

            total_value += market_value
            total_cost += holding.cost_basis

            holdings_value.append({
                "symbol": symbol,
                "shares": round(holding.shares, 6),
                "avg_cost": round(holding.avg_cost, 4),
                "current_price": current_price,
                "market_value": round(market_value, 2),
                "cost_basis": round(holding.cost_basis, 2),
                "gain_loss": round(gain_loss, 2),
                "gain_pct": round(gain_pct, 2),
            })

        total_gain = total_value - total_cost - portfolio.cash_balance
        total_gain_pct = (total_gain / max(total_cost, 0.01)) * 100

        return {
            "portfolio_id": portfolio_id,
            "total_value": round(total_value, 2),
            "cash_balance": round(portfolio.cash_balance, 2),
            "invested_value": round(total_value - portfolio.cash_balance, 2),
            "total_gain_loss": round(total_gain, 2),
            "total_gain_pct": round(total_gain_pct, 2),
            "holdings": holdings_value,
        }

    def get_allocation(self, portfolio_id: str,
                        current_prices: dict) -> dict:
        """Get asset allocation breakdown."""
        value_data = self.get_portfolio_value(portfolio_id, current_prices)
        if "error" in value_data:
            return value_data

        total = value_data["total_value"]
        if total <= 0:
            return {"allocation": [], "total_value": 0}

        allocation = []
        for h in value_data["holdings"]:
            pct = (h["market_value"] / total) * 100
            allocation.append({
                "symbol": h["symbol"],
                "value": h["market_value"],
                "percentage": round(pct, 1),
            })

        # Add cash allocation
        cash_pct = (value_data["cash_balance"] / total) * 100
        if cash_pct > 0.1:
            allocation.append({
                "symbol": "CASH",
                "value": value_data["cash_balance"],
                "percentage": round(cash_pct, 1),
            })

        return {
            "allocation": sorted(allocation, key=lambda x: x["percentage"], reverse=True),
            "total_value": round(total, 2),
            "diversification_score": self._diversification_score(allocation),
        }

    def _diversification_score(self, allocation: list) -> float:
        """Calculate diversification score (0-100)."""
        if not allocation:
            return 0
        hhi = sum((a["percentage"] / 100) ** 2 for a in allocation)
        # Perfect diversification = 1/N, HHI = 1/N
        n = len(allocation)
        perfect = 1 / max(n, 1)
        score = (1 - hhi) / (1 - perfect) * 100 if perfect < 1 else 100
        return round(max(0, min(100, score)), 1)

    def calculate_performance(self, portfolio_id: str,
                                historical_values: list[dict]) -> dict:
        """Calculate portfolio performance metrics."""
        if len(historical_values) < 2:
            return {"error": "Need at least 2 data points"}

        values = [v["value"] for v in sorted(historical_values,
                                              key=lambda x: x["date"])]

        # Total return
        total_return = (values[-1] - values[0]) / max(values[0], 0.01) * 100

        # Max drawdown
        peak = values[0]
        max_dd = 0
        for v in values:
            peak = max(peak, v)
            dd = (peak - v) / max(peak, 0.01) * 100
            max_dd = max(max_dd, dd)

        # Volatility (simplified)
        returns = [(values[i] - values[i-1]) / max(values[i-1], 0.01)
                   for i in range(1, len(values))]
        if returns:
            avg_ret = sum(returns) / len(returns)
            variance = sum((r - avg_ret) ** 2 for r in returns) / len(returns)
            volatility = math.sqrt(variance) * 100
        else:
            volatility = 0

        # Sharpe ratio (simplified, assume risk-free = 2% annual)
        if volatility > 0:
            annualized_return = total_return * (252 / max(len(values), 1))
            sharpe = (annualized_return - 2) / volatility
        else:
            sharpe = 0

        return {
            "total_return": round(total_return, 2),
            "max_drawdown": round(max_dd, 2),
            "volatility": round(volatility, 2),
            "sharpe_ratio": round(sharpe, 2),
            "data_points": len(values),
            "period_start": historical_values[0].get("date"),
            "period_end": historical_values[-1].get("date"),
        }

    def suggest_rebalance(self, portfolio_id: str, target_allocation: dict,
                           current_prices: dict) -> dict:
        """Suggest rebalancing trades to match target allocation."""
        allocation = self.get_allocation(portfolio_id, current_prices)
        if "error" in allocation:
            return allocation

        total = allocation["total_value"]
        suggestions = []

        current_map = {a["symbol"]: a["percentage"] for a in allocation["allocation"]}

        for symbol, target_pct in target_allocation.items():
            current_pct = current_map.get(symbol, 0)
            diff = target_pct - current_pct
            if abs(diff) > 1:  # Only suggest if >1% off
                amount = total * diff / 100
                action = "buy" if diff > 0 else "sell"
                suggestions.append({
                    "symbol": symbol,
                    "action": action,
                    "amount": round(abs(amount), 2),
                    "current_pct": round(current_pct, 1),
                    "target_pct": target_pct,
                    "diff_pct": round(diff, 1),
                })

        return {
            "suggestions": sorted(suggestions, key=lambda x: abs(x["diff_pct"]), reverse=True),
            "total_rebalance_amount": round(sum(abs(s["amount"]) for s in suggestions), 2),
        }

    def list_portfolios(self, owner_id: str) -> list[dict]:
        """List all portfolios for a user."""
        return [p.to_dict() for p in self.portfolios.values()
                if p.owner_id == owner_id]
