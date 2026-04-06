# OpenTrade - Gemini Multi-Agent Trading System

A fully automated forex trading system using 5 specialized Gemini-powered AI agents coordinated by LangGraph, executing trades on MetaTrader 5.

## Features

- **5 Specialized Agents**: Market Analyst, Sentiment Agent, Strategy Agent, Risk Manager, Execution Agent
- **LangGraph Orchestration**: Structured workflow with conditional routing
- **Risk Management**: Circuit breaker, position sizing, hard limits
- **Persistence**: SQLite trade journal with full audit trail
- **Real-time Trading**: MetaTrader 5 integration for live execution

## Quick Start

1. Copy `.env.example` to `.env` and fill in credentials
2. Install dependencies: `pip install -r requirements.txt`
3. Run paper trading: `python scripts/paper_trade.py`

## Documentation

See [SETUP.md](SETUP.md) for detailed installation and configuration instructions.

## License

MIT
