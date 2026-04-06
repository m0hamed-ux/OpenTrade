"""Settings dialog for configuring the trading bot."""

from pathlib import Path
from typing import Any
import json
import os

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
    QCheckBox, QTabWidget, QWidget, QGridLayout, QGroupBox,
    QMessageBox, QFormLayout, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal


class SettingsDialog(QDialog):
    """Settings dialog for editing configuration."""

    settings_saved = pyqtSignal(dict)
    test_connection = pyqtSignal()

    def __init__(self, settings: dict | None = None, parent=None):
        super().__init__(parent)
        self.settings = settings or {}
        self.setWindowTitle("Settings")
        self.setMinimumSize(600, 700)
        self.setup_ui()
        self.load_settings()

    def setup_ui(self):
        """Setup settings UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Title
        title = QLabel("SETTINGS")
        title.setStyleSheet("font-size: 20px; font-weight: 700;")
        layout.addWidget(title)

        # Tabs
        tabs = QTabWidget()

        # Trading tab
        trading_tab = QWidget()
        trading_layout = QVBoxLayout(trading_tab)

        # Symbols
        symbols_group = QGroupBox("Trading Symbols")
        symbols_layout = QFormLayout(symbols_group)

        self.symbols_edit = QLineEdit()
        self.symbols_edit.setPlaceholderText("EURUSD, GBPUSD, USDJPY")
        symbols_layout.addRow("Symbols:", self.symbols_edit)

        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(["M1", "M5", "M15", "M30", "H1", "H4", "D1"])
        symbols_layout.addRow("Timeframe:", self.timeframe_combo)

        self.candle_count = QSpinBox()
        self.candle_count.setRange(50, 500)
        self.candle_count.setValue(100)
        symbols_layout.addRow("Candle Count:", self.candle_count)

        self.cycle_interval = QSpinBox()
        self.cycle_interval.setRange(10, 3600)
        self.cycle_interval.setValue(60)
        self.cycle_interval.setSuffix(" seconds")
        symbols_layout.addRow("Cycle Interval:", self.cycle_interval)

        trading_layout.addWidget(symbols_group)

        # Mode
        mode_group = QGroupBox("Trading Mode")
        mode_layout = QFormLayout(mode_group)

        self.paper_mode = QCheckBox("Paper Trading Mode")
        self.paper_mode.setChecked(True)
        mode_layout.addRow(self.paper_mode)

        self.auto_trade = QCheckBox("Auto-execute trades")
        mode_layout.addRow(self.auto_trade)

        trading_layout.addWidget(mode_group)
        trading_layout.addStretch()

        tabs.addTab(trading_tab, "Trading")

        # Risk tab
        risk_tab = QWidget()
        risk_layout = QVBoxLayout(risk_tab)

        risk_group = QGroupBox("Risk Limits")
        risk_form = QFormLayout(risk_group)

        self.max_risk = QDoubleSpinBox()
        self.max_risk.setRange(0.1, 10.0)
        self.max_risk.setValue(2.0)
        self.max_risk.setSuffix(" %")
        self.max_risk.setDecimals(1)
        risk_form.addRow("Max Risk per Trade:", self.max_risk)

        self.max_daily_loss = QDoubleSpinBox()
        self.max_daily_loss.setRange(1.0, 20.0)
        self.max_daily_loss.setValue(5.0)
        self.max_daily_loss.setSuffix(" %")
        self.max_daily_loss.setDecimals(1)
        risk_form.addRow("Max Daily Loss:", self.max_daily_loss)

        self.max_trades = QSpinBox()
        self.max_trades.setRange(1, 100)
        self.max_trades.setValue(10)
        risk_form.addRow("Max Trades/Day:", self.max_trades)

        self.max_positions = QSpinBox()
        self.max_positions.setRange(1, 20)
        self.max_positions.setValue(3)
        risk_form.addRow("Max Open Positions:", self.max_positions)

        self.min_rr = QDoubleSpinBox()
        self.min_rr.setRange(0.5, 5.0)
        self.min_rr.setValue(1.5)
        self.min_rr.setDecimals(1)
        risk_form.addRow("Min R:R Ratio:", self.min_rr)

        self.default_lot = QDoubleSpinBox()
        self.default_lot.setRange(0.01, 10.0)
        self.default_lot.setValue(0.01)
        self.default_lot.setDecimals(2)
        risk_form.addRow("Default Lot Size:", self.default_lot)

        risk_layout.addWidget(risk_group)
        risk_layout.addStretch()

        tabs.addTab(risk_tab, "Risk")

        # Connections tab
        conn_tab = QWidget()
        conn_layout = QVBoxLayout(conn_tab)

        # MT5 settings
        mt5_group = QGroupBox("MetaTrader 5")
        mt5_form = QFormLayout(mt5_group)

        self.mt5_login = QLineEdit()
        self.mt5_login.setPlaceholderText("Account number")
        mt5_form.addRow("Login:", self.mt5_login)

        self.mt5_password = QLineEdit()
        self.mt5_password.setEchoMode(QLineEdit.EchoMode.Password)
        mt5_form.addRow("Password:", self.mt5_password)

        self.mt5_server = QLineEdit()
        self.mt5_server.setPlaceholderText("Broker server name")
        mt5_form.addRow("Server:", self.mt5_server)

        self.mt5_path = QLineEdit()
        self.mt5_path.setPlaceholderText("C:\\Program Files\\MetaTrader 5\\terminal64.exe")
        mt5_form.addRow("MT5 Path:", self.mt5_path)

        test_mt5_btn = QPushButton("Test Connection")
        test_mt5_btn.clicked.connect(self._test_mt5_connection)
        mt5_form.addRow("", test_mt5_btn)

        self.mt5_status = QLabel("")
        mt5_form.addRow("Status:", self.mt5_status)

        conn_layout.addWidget(mt5_group)

        # Gemini settings
        gemini_group = QGroupBox("Google Gemini API")
        gemini_form = QFormLayout(gemini_group)

        self.gemini_key = QLineEdit()
        self.gemini_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.gemini_key.setPlaceholderText("API Key")
        gemini_form.addRow("API Key:", self.gemini_key)

        conn_layout.addWidget(gemini_group)

        # News API
        news_group = QGroupBox("News API (Optional)")
        news_form = QFormLayout(news_group)

        self.news_enabled = QCheckBox("Enable News Sentiment")
        news_form.addRow(self.news_enabled)

        self.news_key = QLineEdit()
        self.news_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.news_key.setPlaceholderText("NewsAPI Key")
        news_form.addRow("API Key:", self.news_key)

        conn_layout.addWidget(news_group)
        conn_layout.addStretch()

        tabs.addTab(conn_tab, "Connections")

        # Models tab
        models_tab = QWidget()
        models_layout = QVBoxLayout(models_tab)

        models_group = QGroupBox("AI Models")
        models_form = QFormLayout(models_group)

        model_options = ["gemini-2.5-pro", "gemini-2.5-flash"]

        self.orchestrator_model = QComboBox()
        self.orchestrator_model.addItems(model_options)
        models_form.addRow("Orchestrator:", self.orchestrator_model)

        self.analyst_model = QComboBox()
        self.analyst_model.addItems(model_options)
        models_form.addRow("Market Analyst:", self.analyst_model)

        self.sentiment_model = QComboBox()
        self.sentiment_model.addItems(model_options)
        self.sentiment_model.setCurrentText("gemini-2.5-flash")
        models_form.addRow("Sentiment Agent:", self.sentiment_model)

        self.strategy_model = QComboBox()
        self.strategy_model.addItems(model_options)
        models_form.addRow("Strategy Agent:", self.strategy_model)

        self.risk_model = QComboBox()
        self.risk_model.addItems(model_options)
        self.risk_model.setCurrentText("gemini-2.5-flash")
        models_form.addRow("Risk Manager:", self.risk_model)

        models_layout.addWidget(models_group)

        # Confidence settings
        conf_group = QGroupBox("Confidence Settings")
        conf_form = QFormLayout(conf_group)

        self.min_confidence = QDoubleSpinBox()
        self.min_confidence.setRange(0.1, 1.0)
        self.min_confidence.setValue(0.65)
        self.min_confidence.setDecimals(2)
        conf_form.addRow("Min Signal Confidence:", self.min_confidence)

        models_layout.addWidget(conf_group)
        models_layout.addStretch()

        tabs.addTab(models_tab, "AI Models")

        layout.addWidget(tabs)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("Save Settings")
        save_btn.setObjectName("primaryButton")
        save_btn.clicked.connect(self._save_settings)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)

    def load_settings(self):
        """Load settings into UI."""
        trading = self.settings.get("trading", {})
        risk = self.settings.get("risk", {})
        models = self.settings.get("models", {})
        confidence = self.settings.get("confidence", {})

        # Trading
        symbols = trading.get("symbols", ["EURUSD"])
        self.symbols_edit.setText(", ".join(symbols))
        self.timeframe_combo.setCurrentText(trading.get("timeframe", "M15"))
        self.candle_count.setValue(trading.get("candle_count", 100))
        self.cycle_interval.setValue(trading.get("cycle_interval_seconds", 60))

        # Risk
        self.max_risk.setValue(risk.get("max_risk_percent", 2.0))
        self.max_daily_loss.setValue(risk.get("max_daily_loss_percent", 5.0))
        self.max_trades.setValue(risk.get("max_trades_per_day", 10))
        self.max_positions.setValue(risk.get("max_open_positions", 3))
        self.min_rr.setValue(risk.get("min_rr_ratio", 1.5))
        self.default_lot.setValue(risk.get("default_lot_size", 0.01))

        # Models
        self.orchestrator_model.setCurrentText(models.get("orchestrator", "gemini-2.5-pro"))
        self.analyst_model.setCurrentText(models.get("market_analyst", "gemini-2.5-pro"))
        self.sentiment_model.setCurrentText(models.get("sentiment_agent", "gemini-2.5-flash"))
        self.strategy_model.setCurrentText(models.get("strategy_agent", "gemini-2.5-pro"))
        self.risk_model.setCurrentText(models.get("risk_manager", "gemini-2.5-flash"))

        # Confidence
        self.min_confidence.setValue(confidence.get("min_signal_confidence", 0.65))

        # Load from .env if exists
        self._load_env()

    def _load_env(self):
        """Load credentials from .env file."""
        env_path = Path(__file__).parent.parent / ".env"
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        if key == "MT5_LOGIN":
                            self.mt5_login.setText(value)
                        elif key == "MT5_PASSWORD":
                            self.mt5_password.setText(value)
                        elif key == "MT5_SERVER":
                            self.mt5_server.setText(value)
                        elif key == "MT5_PATH":
                            self.mt5_path.setText(value)
                        elif key == "GEMINI_API_KEY":
                            self.gemini_key.setText(value)
                        elif key == "NEWS_API_KEY":
                            self.news_key.setText(value)
                        elif key == "NEWS_API_ENABLED":
                            self.news_enabled.setChecked(value.lower() == "true")
                        elif key == "TRADING_MODE":
                            self.paper_mode.setChecked(value.lower() == "paper")

    def _save_settings(self):
        """Save settings to files."""
        # Build settings dict
        symbols = [s.strip() for s in self.symbols_edit.text().split(",") if s.strip()]

        settings = {
            "trading": {
                "symbols": symbols,
                "timeframe": self.timeframe_combo.currentText(),
                "candle_count": self.candle_count.value(),
                "cycle_interval_seconds": self.cycle_interval.value(),
            },
            "risk": {
                "max_risk_percent": self.max_risk.value(),
                "max_daily_loss_percent": self.max_daily_loss.value(),
                "max_trades_per_day": self.max_trades.value(),
                "max_open_positions": self.max_positions.value(),
                "min_rr_ratio": self.min_rr.value(),
                "default_lot_size": self.default_lot.value(),
            },
            "models": {
                "orchestrator": self.orchestrator_model.currentText(),
                "market_analyst": self.analyst_model.currentText(),
                "sentiment_agent": self.sentiment_model.currentText(),
                "strategy_agent": self.strategy_model.currentText(),
                "risk_manager": self.risk_model.currentText(),
            },
            "confidence": {
                "min_signal_confidence": self.min_confidence.value(),
            },
        }

        # Save settings.json
        settings_path = Path(__file__).parent.parent / "config" / "settings.json"
        with open(settings_path, "w") as f:
            json.dump(settings, f, indent=2)

        # Save .env
        env_lines = [
            f"GEMINI_API_KEY={self.gemini_key.text()}",
            f"MT5_LOGIN={self.mt5_login.text()}",
            f"MT5_PASSWORD={self.mt5_password.text()}",
            f"MT5_SERVER={self.mt5_server.text()}",
            f"MT5_PATH={self.mt5_path.text()}",
            f"NEWS_API_KEY={self.news_key.text()}",
            f"NEWS_API_ENABLED={'true' if self.news_enabled.isChecked() else 'false'}",
            f"TRADING_MODE={'paper' if self.paper_mode.isChecked() else 'live'}",
            "LOG_LEVEL=INFO",
        ]

        env_path = Path(__file__).parent.parent / ".env"
        with open(env_path, "w") as f:
            f.write("\n".join(env_lines))

        self.settings_saved.emit(settings)
        self.accept()

    def _test_mt5_connection(self):
        """Test MT5 connection."""
        self.mt5_status.setText("Testing...")
        self.mt5_status.setStyleSheet("color: #fbbf24;")

        # This would be async in production
        try:
            import MetaTrader5 as mt5

            init_result = mt5.initialize()
            if not init_result:
                self.mt5_status.setText("Failed to initialize MT5")
                self.mt5_status.setStyleSheet("color: #ef4444;")
                return

            login = int(self.mt5_login.text()) if self.mt5_login.text() else 0
            password = self.mt5_password.text()
            server = self.mt5_server.text()

            if mt5.login(login, password=password, server=server):
                self.mt5_status.setText("Connected successfully!")
                self.mt5_status.setStyleSheet("color: #00d4aa;")
            else:
                error = mt5.last_error()
                self.mt5_status.setText(f"Login failed: {error}")
                self.mt5_status.setStyleSheet("color: #ef4444;")

            mt5.shutdown()

        except ImportError:
            self.mt5_status.setText("MT5 module not available")
            self.mt5_status.setStyleSheet("color: #ef4444;")
        except Exception as e:
            self.mt5_status.setText(f"Error: {str(e)}")
            self.mt5_status.setStyleSheet("color: #ef4444;")

    def get_settings(self) -> dict:
        """Get current settings."""
        return self.settings
