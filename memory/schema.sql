-- SQLite schema for trade journal and agent memory

-- Trade journal table
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    symbol TEXT NOT NULL,
    order_type TEXT NOT NULL,
    entry_price REAL NOT NULL,
    exit_price REAL,
    volume REAL NOT NULL,
    stop_loss REAL,
    take_profit REAL,
    profit REAL,
    status TEXT DEFAULT 'open',
    entry_reason TEXT,
    exit_reason TEXT,
    signal_confidence REAL,
    market_analysis TEXT,
    sentiment_data TEXT,
    risk_params TEXT,
    ticket INTEGER,
    magic_number INTEGER,
    CONSTRAINT valid_status CHECK (status IN ('open', 'closed', 'cancelled'))
);

-- Trade cycle logs
CREATE TABLE IF NOT EXISTS cycle_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    cycle_id TEXT UNIQUE NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    account_state TEXT,
    market_analysis TEXT,
    sentiment_analysis TEXT,
    signal TEXT,
    risk_params TEXT,
    execution_result TEXT,
    error TEXT,
    duration_ms INTEGER
);

-- Daily statistics
CREATE TABLE IF NOT EXISTS daily_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE UNIQUE NOT NULL,
    starting_balance REAL NOT NULL,
    ending_balance REAL,
    total_trades INTEGER DEFAULT 0,
    winning_trades INTEGER DEFAULT 0,
    losing_trades INTEGER DEFAULT 0,
    total_profit REAL DEFAULT 0,
    max_drawdown REAL DEFAULT 0,
    win_rate REAL DEFAULT 0,
    avg_risk_reward REAL DEFAULT 0
);

-- Agent memory (short-term context)
CREATE TABLE IF NOT EXISTS agent_memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    agent_name TEXT NOT NULL,
    symbol TEXT,
    memory_type TEXT NOT NULL,
    content TEXT NOT NULL,
    expires_at TIMESTAMP,
    CONSTRAINT valid_memory_type CHECK (memory_type IN ('observation', 'decision', 'feedback', 'pattern'))
);

-- Performance metrics
CREATE TABLE IF NOT EXISTS performance_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    metric_name TEXT NOT NULL,
    metric_value REAL NOT NULL,
    symbol TEXT,
    timeframe TEXT,
    metadata TEXT
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at);
CREATE INDEX IF NOT EXISTS idx_cycle_symbol ON cycle_logs(symbol);
CREATE INDEX IF NOT EXISTS idx_cycle_created ON cycle_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_memory_agent ON agent_memory(agent_name);
CREATE INDEX IF NOT EXISTS idx_memory_expires ON agent_memory(expires_at);
