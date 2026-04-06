"""GUI entry point for OpenTrade trading dashboard."""

import sys
from pathlib import Path

# Add trading_bot to path
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from gui.main_window import MainWindow


def main():
    """Launch the trading dashboard GUI."""
    # High DPI support
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    # Set application info
    app.setApplicationName("OpenTrade")
    app.setApplicationDisplayName("OpenTrade - Gemini Trading System")
    app.setOrganizationName("OpenTrade")

    # Set default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Create and show main window
    window = MainWindow()
    window.show()

    # Demo data for testing
    _load_demo_data(window)

    sys.exit(app.exec())


def _load_demo_data(window: MainWindow):
    """Load demo data for testing the UI."""
    import random
    from datetime import datetime, timedelta

    # Demo prices
    window.update_prices({
        "EURUSD": {"bid": 1.08421, "ask": 1.08423, "spread": 2},
        "BTCUSD": {"bid": 64210.50, "ask": 64215.00, "spread": 450},
    })

    # Demo account
    window.update_account({
        "balance": 1248502.12,
        "equity": 1260952.12,
        "floating_pnl": 12450.00,
        "margin": 5000,
        "free_margin": 1255952.12,
        "margin_level": 25219.04,
        "open_positions": 3,
        "currency": "USD",
        "leverage": 100,
    })

    # Demo agent statuses
    window.update_agent_status({
        "orchestrator": {"status": "running", "info": "CORE RUNTIME"},
        "analyst": {"status": "idle", "info": "LMM-V3"},
        "sentiment": {"status": "working", "info": "X/NEWS FEED"},
        "strategy": {"status": "idle", "info": "SCALP_HFT_01"},
        "risk": {"status": "running", "info": "GLOBAL_MONITOR"},
        "execution": {"status": "error", "info": "BRIDGE_ERROR"},
    })

    # Demo circuit breaker
    window.update_circuit_breaker({
        "is_tripped": False,
        "trip_reason": None,
        "starting_balance": 1248502.12,
        "current_equity": 1260952.12,
        "trade_count": 22,
        "max_trades": 50,
        "max_daily_loss_percent": 5.0,
        "daily_pnl": 12450.00,
    })

    # Demo positions
    window.update_positions([
        {
            "symbol": "EURUSD",
            "type": "BUY",
            "volume": 1.0,
            "price_open": 1.08350,
            "price_current": 1.08421,
            "profit": 710.00,
        },
        {
            "symbol": "GBPUSD",
            "type": "BUY",
            "volume": 0.5,
            "price_open": 1.26420,
            "price_current": 1.26510,
            "profit": 450.00,
        },
    ], {
        "balance": 1248502.12,
        "equity": 1260952.12,
    })

    # Demo chart data
    chart_data = []
    base_price = 1.0842
    for i in range(100):
        change = random.uniform(-0.0010, 0.0010)
        o = base_price + change
        h = o + random.uniform(0, 0.0008)
        l = o - random.uniform(0, 0.0008)
        c = o + random.uniform(-0.0005, 0.0005)
        chart_data.append({
            "time": (datetime.now() - timedelta(minutes=15*(100-i))).isoformat(),
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": random.randint(100, 1000),
        })
        base_price = c

    window.update_chart(chart_data, "EURUSD")

    # Demo signals
    window.add_signal({
        "signal": "BUY",
        "symbol": "EURUSD",
        "entry_price": 1.08420,
        "take_profit": 1.08650,
        "sentiment": "Sentiment Bullish",
    })
    window.add_signal({
        "signal": "SELL",
        "symbol": "BTCUSD",
        "entry_price": 64200.00,
        "take_profit": 63500.00,
        "sentiment": "Closed @ Break-even",
    })
    window.add_signal({
        "signal": "BUY",
        "symbol": "GBPUSD",
        "entry_price": 1.26420,
        "take_profit": 1.26800,
        "stop_loss": 1.26100,
    })

    # Demo logs
    window.log("orchestrator", "info", "Polling sentiment agents for market bias shift...")
    window.log("risk", "warning", "Volatility index spike detected on EUR pairs.")
    window.log("sentiment", "info", "Processed 450 X posts. Net bias: +0.62 (Bullish).")
    window.log("analyst", "info", "Descending wedge pattern confirmed on 15M EURUSD.")
    window.log("orchestrator", "info", "System heartbeat OK. Latency: 45ms")


if __name__ == "__main__":
    main()
