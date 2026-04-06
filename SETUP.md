# OpenTrade Setup Guide

Complete installation and configuration guide for the Gemini Multi-Agent Trading System.

## Prerequisites

### System Requirements
- **Operating System**: Windows 10/11 (required for MetaTrader 5)
- **Python**: 3.11 or higher
- **MetaTrader 5**: Installed with an active broker account

### API Keys Required
1. **Google Gemini API Key**: Get from [Google AI Studio](https://aistudio.google.com/)
2. **MetaTrader 5 Account**: Login, password, and server from your broker
3. **NewsAPI Key** (optional): Get from [NewsAPI](https://newsapi.org/)

---

## Installation

### Step 1: Clone or Download the Project

```bash
cd C:\Users\YourName\Desktop
# If using git:
git clone <repository-url> OpenTrade
cd OpenTrade/trading_bot
```

### Step 2: Create Virtual Environment

```bash
# Create virtual environment
python -m venv venv

# Activate it
venv\Scripts\activate
```

### Step 3: Install Dependencies

```bash
pip install -r requirements.txt
```

**Note**: The `MetaTrader5` package only works on Windows. If you see installation errors, ensure you're on Windows with Python 3.11+.

### Step 4: Configure Environment Variables

Copy the example environment file:

```bash
copy .env.example .env
```

Edit `.env` with your credentials:

```env
# Google Gemini API
GEMINI_API_KEY=your_actual_gemini_api_key

# MetaTrader 5 Credentials
MT5_LOGIN=12345678
MT5_PASSWORD=your_mt5_password
MT5_SERVER=YourBroker-Server
MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe

# News API (Optional - set to false if not using)
NEWS_API_KEY=your_newsapi_key
NEWS_API_ENABLED=false

# Trading Mode
TRADING_MODE=paper
LOG_LEVEL=INFO
```

### Step 5: Configure Trading Settings

Edit `config/settings.json` to customize:

```json
{
  "trading": {
    "symbols": ["EURUSD", "GBPUSD"],
    "timeframe": "M15",
    "candle_count": 100,
    "cycle_interval_seconds": 60
  },
  "risk": {
    "max_risk_percent": 2.0,
    "max_daily_loss_percent": 5.0,
    "max_trades_per_day": 10,
    "max_open_positions": 3
  }
}
```

---

## MetaTrader 5 Setup

### 1. Enable Algo Trading

In MetaTrader 5:
1. Go to **Tools > Options > Expert Advisors**
2. Check "Allow automated trading"
3. Check "Allow DLL imports"

### 2. Verify Python Connection

Test that MT5 connects properly:

```bash
python -c "import MetaTrader5 as mt5; print(mt5.initialize())"
```

Should output `True` if successful.

### 3. Enable Symbols

Ensure the symbols you want to trade are visible in MT5:
1. Right-click in Market Watch
2. Select "Show All" or add specific symbols

---

## Running the System

### Paper Trading (Recommended First)

Test with real market data but simulated execution:

```bash
python scripts/paper_trade.py --symbols EURUSD --interval 60 --cycles 10
```

Options:
- `--symbols`: Space-separated list of symbols
- `--interval`: Seconds between cycles
- `--cycles`: Number of cycles (omit for unlimited)

### Single Cycle Test

Run one analysis cycle without trading:

```bash
python main.py --mode single --symbol EURUSD
```

### Live Trading

**WARNING**: This executes real trades with real money.

```bash
python main.py --mode live
```

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR                           │
│  Coordinates cycle, enforces limits, routes to agents       │
└─────────────────────┬───────────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
┌───────────────┐           ┌───────────────┐
│ MARKET ANALYST│           │SENTIMENT AGENT│
│ (Gemini Pro)  │           │ (Gemini Flash)│
│               │           │               │
│ - OHLCV Data  │           │ - News        │
│ - TA Tools    │           │ - Headlines   │
│ - Patterns    │           │ - Sentiment   │
└───────┬───────┘           └───────┬───────┘
        │                           │
        └─────────────┬─────────────┘
                      ▼
              ┌───────────────┐
              │STRATEGY AGENT │
              │ (Gemini Pro)  │
              │               │
              │ BUY/SELL/FLAT │
              │ + Confidence  │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ RISK MANAGER  │
              │ (Gemini Flash)│
              │               │
              │ - Lot Size    │
              │ - SL/TP       │
              │ - Validation  │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │   EXECUTION   │
              │    AGENT      │
              │               │
              │ - MT5 Orders  │
              │ - Confirmation│
              └───────────────┘
```

---

## LangGraph Workflow

The system uses LangGraph for structured agent orchestration:

```
START
  │
  ▼
[check_preconditions] ──(fail)──► [log_cycle] ──► END
  │
  │ (pass)
  ▼
[run_analysis] ◄── Market Analyst + Sentiment Agent (parallel)
  │
  ▼
[generate_signal] ──(FLAT)──► [log_cycle] ──► END
  │
  │ (BUY/SELL)
  ▼
[validate_risk] ──(rejected)──► [log_cycle] ──► END
  │
  │ (approved)
  ▼
[execute_trade]
  │
  ▼
[log_cycle] ──► END
```

---

## Risk Management

### Circuit Breaker (Hard Limits)
These limits are enforced INDEPENDENTLY of AI decisions:

| Limit | Default | Description |
|-------|---------|-------------|
| Max Risk Per Trade | 2% | Maximum account risk per position |
| Max Daily Loss | 5% | Trading halts if exceeded |
| Max Trades/Day | 10 | Maximum trades per session |
| Max Open Positions | 3 | Maximum concurrent positions |

### Position Sizing
- **Fixed Fractional**: Risk X% of account per trade
- **ATR-Based Stops**: 1.5x ATR for SL, 2.5x ATR for TP
- **Minimum R:R**: 1.5:1 required for trade approval

---

## Database Schema

Trade journal stored in SQLite (`data/journal.db`):

### trades table
- Entry/exit prices, volume, SL/TP
- Signal confidence and reasoning
- Full market analysis snapshot

### cycle_logs table
- Complete audit trail per cycle
- Agent outputs at each step
- Timing and performance data

### daily_stats table
- Daily P/L and trade counts
- Win rate and drawdown tracking

---

## Testing

Run the test suite:

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_risk.py -v

# Run with coverage
pytest --cov=. --cov-report=html
```

---

## Scripts

### Backtest
```bash
python scripts/backtest.py --data historical_eurusd.csv --balance 10000
```

### Analyze Journal
```bash
python scripts/analyze_journal.py --days 30
```

---

## Troubleshooting

### MT5 Connection Fails
1. Ensure MT5 terminal is running
2. Check credentials in `.env`
3. Verify `MT5_PATH` points to correct executable
4. Try running MT5 as administrator

### "No module named MetaTrader5"
- Only works on Windows
- Requires Python 3.11+
- Try: `pip install --upgrade MetaTrader5`

### Gemini API Errors
- Verify API key is correct
- Check rate limits (free tier: 60 req/min)
- Ensure billing is enabled for production use

### Circuit Breaker Tripped
- Check `data/circuit_breaker.json` for state
- Reset with: delete the JSON file
- Review daily loss and trade count

---

## Configuration Reference

### settings.json

```json
{
  "trading": {
    "symbols": ["EURUSD"],        // Symbols to trade
    "timeframe": "M15",           // Candle timeframe
    "candle_count": 100,          // Candles for analysis
    "cycle_interval_seconds": 60  // Seconds between cycles
  },
  "risk": {
    "max_risk_percent": 2.0,      // Max risk per trade
    "max_daily_loss_percent": 5.0, // Daily loss limit
    "max_trades_per_day": 10,     // Max trades
    "max_open_positions": 3,      // Max concurrent positions
    "default_lot_size": 0.01,     // Minimum lot
    "min_rr_ratio": 1.5           // Minimum reward:risk
  },
  "models": {
    "orchestrator": "gemini-2.5-pro",
    "market_analyst": "gemini-2.5-pro",
    "sentiment_agent": "gemini-2.5-flash",
    "strategy_agent": "gemini-2.5-pro",
    "risk_manager": "gemini-2.5-flash"
  },
  "confidence": {
    "min_signal_confidence": 0.65 // Below this = FLAT
  }
}
```

---

## Security Notes

1. **Never commit `.env`** - Contains API keys and passwords
2. **Use paper trading first** - Test before risking real money
3. **Monitor actively** - AI systems can malfunction
4. **Set broker-level limits** - Use broker's risk controls as backup
5. **Regular backups** - Export journal data regularly

---

## Support

- Create issues at: [GitHub Issues](https://github.com/your-repo/issues)
- Review logs in `logs/` directory
- Check trade journal with `scripts/analyze_journal.py`

---

## Disclaimer

**TRADING INVOLVES SIGNIFICANT RISK OF LOSS**

This software is provided for educational purposes. Trading forex and other financial instruments carries substantial risk. Past performance does not guarantee future results. Only trade with money you can afford to lose. The authors are not responsible for any financial losses incurred using this system.
