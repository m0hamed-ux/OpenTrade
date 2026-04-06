"""Main window shell for the trading dashboard."""

import json
from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton, QLabel, QFrame, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon, QAction

from .dashboard import Dashboard
from .journal_view import JournalView
from .agent_inspector import AgentInspector
from .risk_monitor import RiskMonitor
from .settings_dialog import SettingsDialog
from .workers import (
    AgentStatusPoller, PriceUpdateWorker, AccountUpdateWorker,
    TradingCycleWorker, LogBuffer
)


class SideNav(QFrame):
    """Side navigation panel."""

    nav_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidePanel")
        self.setFixedWidth(200)
        self.current_view = "dashboard"
        self.buttons = {}
        self.setup_ui()

    def setup_ui(self):
        """Setup navigation UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 20, 12, 20)
        layout.setSpacing(8)

        # Header
        header_frame = QFrame()
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 0, 8, 16)

        # System status indicator
        status_row = QHBoxLayout()
        status_dot = QLabel("●")
        status_dot.setStyleSheet("color: #00d4aa; font-size: 10px;")
        status_row.addWidget(status_dot)

        status_text = QLabel("GEMINI SYSTEM")
        status_text.setStyleSheet("color: #00d4aa; font-weight: 700; font-size: 14px;")
        status_row.addWidget(status_text)
        status_row.addStretch()
        header_layout.addLayout(status_row)

        self.agents_label = QLabel("0 AGENTS ACTIVE")
        self.agents_label.setStyleSheet("color: #6b7280; font-size: 11px;")
        header_layout.addWidget(self.agents_label)

        layout.addWidget(header_frame)

        # Navigation buttons
        nav_items = [
            ("dashboard", "DASHBOARD"),
            ("journal", "JOURNAL"),
            ("inspector", "INSPECTOR"),
            ("symbols", "SYMBOLS"),
            ("risk", "RISK MONITOR"),
            ("settings", "SETTINGS"),
        ]

        for view_id, label in nav_items:
            btn = QPushButton(f"  {label}")
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            btn.setChecked(view_id == "dashboard")
            btn.clicked.connect(lambda checked, v=view_id: self._on_nav_click(v))
            layout.addWidget(btn)
            self.buttons[view_id] = btn

        layout.addStretch()

    def _on_nav_click(self, view_id: str):
        """Handle navigation button click."""
        self.current_view = view_id

        # Update button states
        for vid, btn in self.buttons.items():
            btn.setChecked(vid == view_id)

        self.nav_changed.emit(view_id)

    def set_active_agents(self, count: int):
        """Update active agents count."""
        self.agents_label.setText(f"{count} AGENTS ACTIVE")


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.settings = self._load_settings()
        self.log_buffer = LogBuffer()

        # Workers
        self.status_poller = None
        self.price_worker = None
        self.account_worker = None
        self.cycle_worker = None

        self.setup_ui()
        self.setup_connections()

    def _load_settings(self) -> dict:
        """Load settings from file."""
        settings_path = Path(__file__).parent.parent / "config" / "settings.json"
        try:
            with open(settings_path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def setup_ui(self):
        """Setup main window UI."""
        self.setWindowTitle("OpenTrade - Gemini Multi-Agent Trading System")
        self.setMinimumSize(1400, 900)

        # Load stylesheet
        self._load_stylesheet()

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Side navigation
        self.side_nav = SideNav()
        main_layout.addWidget(self.side_nav)

        # Content area
        self.content_stack = QStackedWidget()

        # Create views
        self.dashboard = Dashboard()
        self.content_stack.addWidget(self.dashboard)

        self.journal = JournalView()
        self.content_stack.addWidget(self.journal)

        self.inspector = AgentInspector()
        self.content_stack.addWidget(self.inspector)

        # Placeholder for symbols view
        symbols_placeholder = QWidget()
        symbols_layout = QVBoxLayout(symbols_placeholder)
        symbols_layout.addWidget(QLabel("Symbol Deep-Dive View"))
        symbols_layout.addStretch()
        self.content_stack.addWidget(symbols_placeholder)

        self.risk_monitor = RiskMonitor()
        self.content_stack.addWidget(self.risk_monitor)

        # Settings is a dialog, not a stacked view
        self.settings_placeholder = QWidget()
        self.content_stack.addWidget(self.settings_placeholder)

        main_layout.addWidget(self.content_stack, stretch=1)

    def _load_stylesheet(self):
        """Load the QSS stylesheet."""
        style_path = Path(__file__).parent / "styles.qss"
        try:
            with open(style_path) as f:
                self.setStyleSheet(f.read())
        except FileNotFoundError:
            pass

    def setup_connections(self):
        """Setup signal connections."""
        # Navigation
        self.side_nav.nav_changed.connect(self._on_nav_changed)

        # Dashboard signals
        self.dashboard.emergency_halt.connect(self._on_emergency_halt)
        self.dashboard.start_cycle.connect(self._on_start_cycle)
        self.dashboard.pause_cycle.connect(self._on_pause_cycle)
        self.dashboard.agent_clicked.connect(self._on_agent_clicked)
        self.dashboard.settings_requested.connect(self._show_settings)
        self.dashboard.journal_requested.connect(lambda: self._on_nav_changed("journal"))

        # Inspector signals
        self.inspector.close_requested.connect(lambda: self._on_nav_changed("dashboard"))

        # Risk monitor signals
        self.risk_monitor.close_requested.connect(lambda: self._on_nav_changed("dashboard"))
        self.risk_monitor.reset_circuit_breaker.connect(self._on_reset_circuit_breaker)
        self.risk_monitor.close_all_positions.connect(self._on_close_all_positions)

        # Log buffer
        self.log_buffer.log_added.connect(self._on_log_added)

    def _on_nav_changed(self, view_id: str):
        """Handle navigation change."""
        view_map = {
            "dashboard": 0,
            "journal": 1,
            "inspector": 2,
            "symbols": 3,
            "risk": 4,
            "settings": 5,
        }

        if view_id == "settings":
            self._show_settings()
            return

        index = view_map.get(view_id, 0)
        self.content_stack.setCurrentIndex(index)

        # Update side nav
        for vid, btn in self.side_nav.buttons.items():
            btn.setChecked(vid == view_id)

    def _on_agent_clicked(self, agent_name: str):
        """Handle agent card click."""
        self.inspector.set_agent(agent_name)
        self._on_nav_changed("inspector")

    def _show_settings(self):
        """Show settings dialog."""
        dialog = SettingsDialog(self.settings, self)
        dialog.settings_saved.connect(self._on_settings_saved)
        dialog.exec()

    def _on_settings_saved(self, settings: dict):
        """Handle settings saved."""
        self.settings = settings

        # Update dashboard mode
        mode = settings.get("trading", {}).get("mode", "paper")
        self.dashboard.set_mode(mode == "paper")

        self.log_buffer.add("system", "info", "Settings updated")

    def _on_emergency_halt(self):
        """Handle emergency halt."""
        reply = QMessageBox.warning(
            self,
            "Emergency Halt",
            "This will stop all trading and close all positions.\n\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self._stop_all_workers()
            self.log_buffer.add("system", "warning", "EMERGENCY HALT ACTIVATED")
            # Would trigger actual halt logic here

    def _on_start_cycle(self):
        """Handle start cycle."""
        self.log_buffer.add("orchestrator", "info", "Starting trading cycles...")
        # Would start cycle worker here

    def _on_pause_cycle(self):
        """Handle pause cycle."""
        self.log_buffer.add("orchestrator", "info", "Trading cycles paused")
        if self.cycle_worker:
            self.cycle_worker.pause()

    def _on_reset_circuit_breaker(self):
        """Handle circuit breaker reset."""
        reply = QMessageBox.warning(
            self,
            "Reset Circuit Breaker",
            "This will reset all daily limits.\n\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.log_buffer.add("risk", "warning", "Circuit breaker manually reset")
            # Would reset circuit breaker here

    def _on_close_all_positions(self):
        """Handle close all positions."""
        reply = QMessageBox.warning(
            self,
            "Close All Positions",
            "This will close ALL open positions at market price.\n\nAre you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.log_buffer.add("execution", "warning", "Closing all positions...")
            # Would close positions here

    def _on_log_added(self, entry):
        """Handle new log entry."""
        timestamp = entry.timestamp.strftime("%H:%M:%S")
        self.dashboard.cognition_feed.add_log(
            timestamp,
            entry.agent,
            entry.message,
            entry.level
        )

    def _stop_all_workers(self):
        """Stop all background workers."""
        if self.status_poller:
            self.status_poller.stop()
        if self.price_worker:
            self.price_worker.stop()
        if self.account_worker:
            self.account_worker.stop()
        if self.cycle_worker:
            self.cycle_worker.stop()

    def closeEvent(self, event):
        """Handle window close."""
        self._stop_all_workers()
        event.accept()

    # ==================== Public API ====================

    def update_prices(self, prices: dict[str, dict]):
        """Update price displays.

        Args:
            prices: Dict of {symbol: {bid, ask, spread}}
        """
        self.dashboard.update_prices(prices)

    def update_account(self, account: dict):
        """Update account info.

        Args:
            account: Account state dict
        """
        self.dashboard.update_account(account)
        self.risk_monitor.update_account(account)

    def update_agent_status(self, statuses: dict[str, dict]):
        """Update agent statuses.

        Args:
            statuses: Dict of {agent_name: {status, info}}
        """
        self.dashboard.update_agent_status(statuses)

        # Count active agents
        active = sum(1 for s in statuses.values() if s.get("status") in ["running", "working"])
        self.side_nav.set_active_agents(active)

    def update_positions(self, positions: list[dict], account: dict):
        """Update positions display.

        Args:
            positions: List of position dicts
            account: Account state
        """
        self.risk_monitor.update_positions(positions, account)

    def update_circuit_breaker(self, status: dict):
        """Update circuit breaker display.

        Args:
            status: Circuit breaker status dict
        """
        self.risk_monitor.update_circuit_breaker(status)

        # Update risk metrics
        max_loss = status.get("max_daily_loss_percent", 5)
        current_loss = (status.get("starting_balance", 1) - status.get("current_equity", 1)) / status.get("starting_balance", 1) * 100 if status.get("starting_balance") else 0
        trade_pct = status.get("trade_count", 0) / status.get("max_trades", 10) * 100 if status.get("max_trades") else 0

        self.dashboard.update_risk_metrics(
            trade_count=status.get("trade_count", 0),
            max_trades=status.get("max_trades", 10),
            daily_loss=abs(current_loss),
            max_loss=max_loss
        )

    def update_chart(self, data: list[dict], symbol: str):
        """Update chart with new data.

        Args:
            data: OHLCV data
            symbol: Symbol name
        """
        self.dashboard.chart.set_data(data, symbol)

    def add_signal(self, signal: dict):
        """Add a new signal to the display.

        Args:
            signal: Signal dict
        """
        from datetime import datetime
        self.dashboard.signals_card.add_signal(
            signal_type=signal.get("signal", "FLAT"),
            symbol=signal.get("symbol", ""),
            entry=signal.get("entry_price", 0),
            target=signal.get("take_profit", 0),
            timestamp=datetime.now().strftime("%H:%M:%S"),
            sentiment=signal.get("sentiment", ""),
        )

    def add_trade(self, trade: dict):
        """Add a new trade to the journal.

        Args:
            trade: Trade dict
        """
        self.journal.add_trade(trade)

    def log(self, agent: str, level: str, message: str):
        """Add a log entry.

        Args:
            agent: Agent name
            level: Log level (info, warning, error)
            message: Log message
        """
        self.log_buffer.add(agent, level, message)

    def set_inspector_data(self, agent_name: str, data: dict):
        """Set agent inspector data.

        Args:
            agent_name: Agent name
            data: Inspector data dict
        """
        if self.inspector.current_agent == agent_name:
            self.inspector.update_data(data)
