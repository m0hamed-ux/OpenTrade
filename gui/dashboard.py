"""Main dashboard view."""

from datetime import datetime
from typing import Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QGridLayout, QProgressBar, QSizePolicy,
    QSpacerItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor

from .chart_widget import ChartWidget, MiniChart


class MetricCard(QFrame):
    """Dashboard metric card widget."""

    def __init__(
        self,
        title: str,
        value: str = "--",
        subtitle: str = "",
        show_progress: bool = False,
        parent=None
    ):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumWidth(200)
        self.setMinimumHeight(100)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header with title and icon
        header = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setObjectName("metricLabel")
        header.addWidget(self.title_label)
        header.addStretch()

        # Optional icon placeholder
        self.icon_label = QLabel()
        header.addWidget(self.icon_label)
        layout.addLayout(header)

        # Value
        self.value_label = QLabel(value)
        self.value_label.setObjectName("metricValue")
        layout.addWidget(self.value_label)

        # Subtitle or change indicator
        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setObjectName("percentChange")
        self.subtitle_label.setStyleSheet("color: #00d4aa;")
        layout.addWidget(self.subtitle_label)

        # Optional progress bar
        self.progress_bar = None
        if show_progress:
            self.progress_bar = QProgressBar()
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setMaximumHeight(8)
            layout.addWidget(self.progress_bar)

        layout.addStretch()

    def set_value(self, value: str, color: str = "#ffffff"):
        """Update the metric value."""
        self.value_label.setText(value)
        self.value_label.setStyleSheet(f"font-size: 28px; font-weight: 700; color: {color};")

    def set_subtitle(self, text: str, color: str = "#9ca3af"):
        """Update the subtitle."""
        self.subtitle_label.setText(text)
        self.subtitle_label.setStyleSheet(f"font-size: 12px; color: {color};")

    def set_progress(self, value: int, warning: bool = False, danger: bool = False):
        """Update progress bar value."""
        if self.progress_bar:
            self.progress_bar.setValue(value)
            if danger:
                self.progress_bar.setObjectName("dangerProgress")
            elif warning:
                self.progress_bar.setObjectName("warningProgress")
            else:
                self.progress_bar.setObjectName("")
            self.progress_bar.setStyleSheet(self.progress_bar.styleSheet())


class AgentStatusCard(QFrame):
    """Agent status card for the control matrix."""

    clicked = pyqtSignal(str)  # agent name

    STATUS_COLORS = {
        "running": "#00d4aa",
        "idle": "#6b7280",
        "working": "#fbbf24",
        "error": "#ef4444",
    }

    def __init__(self, agent_name: str, agent_type: str = "", parent=None):
        super().__init__(parent)
        self.agent_name = agent_name
        self.setObjectName("statusCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(150)
        self.setMinimumHeight(70)

        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        layout.setContentsMargins(12, 12, 12, 12)

        # Header with name and status dot
        header = QHBoxLayout()

        self.name_label = QLabel(agent_name)
        self.name_label.setObjectName("agentName")
        header.addWidget(self.name_label)

        header.addStretch()

        # Status indicator
        self.status_label = QLabel("IDLE")
        self.status_label.setStyleSheet(f"color: {self.STATUS_COLORS['idle']}; font-size: 11px; font-weight: 600;")
        header.addWidget(self.status_label)

        # Status dot
        self.status_dot = QLabel("●")
        self.status_dot.setStyleSheet(f"color: {self.STATUS_COLORS['idle']}; font-size: 10px;")
        header.addWidget(self.status_dot)

        layout.addLayout(header)

        # Agent type
        self.type_label = QLabel(agent_type)
        self.type_label.setObjectName("agentStatus")
        layout.addWidget(self.type_label)

    def set_status(self, status: str, info: str = ""):
        """Update agent status.

        Args:
            status: One of 'running', 'idle', 'working', 'error'
            info: Additional status info
        """
        color = self.STATUS_COLORS.get(status.lower(), self.STATUS_COLORS["idle"])
        self.status_label.setText(status.upper())
        self.status_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600;")
        self.status_dot.setStyleSheet(f"color: {color}; font-size: 10px;")

        if info:
            self.type_label.setText(info)

    def mousePressEvent(self, event):
        """Handle click to open inspector."""
        self.clicked.emit(self.agent_name)
        super().mousePressEvent(event)


class SignalCard(QFrame):
    """Latest signal display card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumWidth(250)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        header = QHBoxLayout()
        self.title = QLabel("LATEST SIGNALS")
        self.title.setObjectName("sectionTitle")
        header.addWidget(self.title)
        header.addStretch()

        self.live_badge = QLabel("LIVE")
        self.live_badge.setStyleSheet("""
            background-color: #00d4aa;
            color: #0a0e17;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 10px;
            font-weight: 700;
        """)
        header.addWidget(self.live_badge)
        layout.addLayout(header)

        # Signals container
        self.signals_layout = QVBoxLayout()
        self.signals_layout.setSpacing(12)
        layout.addLayout(self.signals_layout)

        layout.addStretch()

        # Store signal widgets
        self.signal_widgets = []

    def add_signal(
        self,
        signal_type: str,
        symbol: str,
        entry: float,
        target: float,
        timestamp: str,
        sentiment: str = "",
        status: str = ""
    ):
        """Add a signal entry."""
        signal_frame = QFrame()
        signal_frame.setStyleSheet("""
            QFrame {
                border-bottom: 1px solid #1f2937;
                padding-bottom: 12px;
            }
        """)
        signal_layout = QVBoxLayout(signal_frame)
        signal_layout.setSpacing(4)
        signal_layout.setContentsMargins(0, 0, 0, 8)

        # Header row
        header = QHBoxLayout()

        # Signal type badge
        type_label = QLabel(f"{signal_type} {symbol}")
        if signal_type.upper() == "BUY":
            type_label.setStyleSheet("color: #00d4aa; font-weight: 700;")
        else:
            type_label.setStyleSheet("color: #ef4444; font-weight: 700;")
        header.addWidget(type_label)

        header.addStretch()

        # Timestamp
        time_label = QLabel(timestamp)
        time_label.setObjectName("timestamp")
        header.addWidget(time_label)

        signal_layout.addLayout(header)

        # Entry/Target info
        info_label = QLabel(f"Entry: {entry:.5f} | TP: {target:.5f}")
        info_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        signal_layout.addWidget(info_label)

        # Status or sentiment badge
        if status:
            status_label = QLabel(status)
            status_label.setStyleSheet("""
                color: #fbbf24;
                font-size: 11px;
            """)
            signal_layout.addWidget(status_label)
        elif sentiment:
            sentiment_label = QLabel(sentiment)
            if "bullish" in sentiment.lower():
                sentiment_label.setObjectName("sentimentBullish")
            else:
                sentiment_label.setObjectName("sentimentBearish")
            signal_layout.addWidget(sentiment_label)

        self.signals_layout.insertWidget(0, signal_frame)
        self.signal_widgets.insert(0, signal_frame)

        # Keep only last 5 signals
        while len(self.signal_widgets) > 5:
            widget = self.signal_widgets.pop()
            self.signals_layout.removeWidget(widget)
            widget.deleteLater()


class CognitionFeed(QFrame):
    """Real-time agent log feed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumWidth(300)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(16, 16, 16, 16)

        # Header
        self.title = QLabel("COGNITION FEED")
        self.title.setObjectName("sectionTitle")
        layout.addWidget(self.title)

        # Scroll area for logs
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.log_container = QWidget()
        self.log_layout = QVBoxLayout(self.log_container)
        self.log_layout.setSpacing(8)
        self.log_layout.setContentsMargins(0, 0, 0, 0)
        self.log_layout.addStretch()

        scroll.setWidget(self.log_container)
        layout.addWidget(scroll, stretch=1)

        self.log_entries = []

    def add_log(self, timestamp: str, agent: str, message: str, level: str = "info"):
        """Add a log entry."""
        entry = QFrame()
        entry_layout = QHBoxLayout(entry)
        entry_layout.setContentsMargins(0, 4, 0, 4)
        entry_layout.setSpacing(8)

        # Timestamp
        time_label = QLabel(timestamp)
        time_label.setObjectName("timestamp")
        time_label.setMinimumWidth(60)
        entry_layout.addWidget(time_label)

        # Agent badge
        agent_label = QLabel(f"[{agent}]")
        color = self._get_agent_color(agent, level)
        agent_label.setStyleSheet(f"color: {color}; font-weight: 600; font-size: 11px;")
        agent_label.setMinimumWidth(100)
        entry_layout.addWidget(agent_label)

        # Message
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        entry_layout.addWidget(msg_label, stretch=1)

        # Insert at top
        self.log_layout.insertWidget(0, entry)
        self.log_entries.insert(0, entry)

        # Keep only last 50 entries
        while len(self.log_entries) > 50:
            widget = self.log_entries.pop()
            self.log_layout.removeWidget(widget)
            widget.deleteLater()

    def _get_agent_color(self, agent: str, level: str) -> str:
        """Get color for agent based on level."""
        if level == "error":
            return "#ef4444"
        if level == "warning":
            return "#fbbf24"

        agent_colors = {
            "orchestrator": "#00d4aa",
            "analyst": "#3b82f6",
            "sentiment": "#8b5cf6",
            "strategy": "#f59e0b",
            "risk": "#ef4444",
            "execution": "#10b981",
        }
        return agent_colors.get(agent.lower(), "#9ca3af")


class Dashboard(QWidget):
    """Main dashboard view."""

    emergency_halt = pyqtSignal()
    start_cycle = pyqtSignal()
    pause_cycle = pyqtSignal()
    agent_clicked = pyqtSignal(str)
    settings_requested = pyqtSignal()
    journal_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.is_running = False
        self.is_paper_mode = True

        self.setup_ui()

        # Start clock update timer
        self.clock_timer = QTimer()
        self.clock_timer.timeout.connect(self._update_clock)
        self.clock_timer.start(1000)

    def setup_ui(self):
        """Setup dashboard UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ==================== TOP BAR ====================
        top_bar = QFrame()
        top_bar.setObjectName("topBar")
        top_bar.setFixedHeight(56)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(20, 0, 20, 0)

        # Logo
        logo = QLabel("QUANT EDGE")
        logo.setStyleSheet("font-size: 18px; font-weight: 700; color: #00d4aa;")
        top_layout.addWidget(logo)

        top_layout.addSpacing(24)

        # Live prices
        self.price_labels = {}
        for symbol in ["EURUSD", "BTCUSD"]:
            price_frame = QFrame()
            price_layout = QHBoxLayout(price_frame)
            price_layout.setContentsMargins(0, 0, 0, 0)
            price_layout.setSpacing(8)

            dot = QLabel("●")
            dot.setStyleSheet("color: #00d4aa; font-size: 8px;")
            price_layout.addWidget(dot)

            sym_label = QLabel(symbol)
            sym_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
            price_layout.addWidget(sym_label)

            price_label = QLabel("--")
            price_label.setObjectName("symbolPrice")
            price_layout.addWidget(price_label)

            self.price_labels[symbol] = price_label
            top_layout.addWidget(price_frame)
            top_layout.addSpacing(16)

        top_layout.addStretch()

        # Mode badge
        self.mode_badge = QLabel("PAPER MODE")
        self.mode_badge.setObjectName("badgePaper")
        top_layout.addWidget(self.mode_badge)

        top_layout.addSpacing(16)

        # Clock
        self.clock_label = QLabel("UTC 00:00:00")
        self.clock_label.setStyleSheet("color: #9ca3af; font-size: 13px;")
        top_layout.addWidget(self.clock_label)

        top_layout.addSpacing(16)

        # Settings button
        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(36, 36)
        settings_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid #374151;
                border-radius: 18px;
                font-size: 18px;
            }
            QPushButton:hover {
                background-color: #1f2937;
            }
        """)
        settings_btn.clicked.connect(self.settings_requested.emit)
        top_layout.addWidget(settings_btn)

        layout.addWidget(top_bar)

        # ==================== MAIN CONTENT ====================
        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setSpacing(20)
        content_layout.setContentsMargins(20, 20, 20, 20)

        # Left column - main content
        left_column = QVBoxLayout()
        left_column.setSpacing(20)

        # Metrics row
        metrics_row = QHBoxLayout()
        metrics_row.setSpacing(16)

        self.equity_card = MetricCard("EQUITY BALANCE", "$0.00", "+0.0% Today")
        metrics_row.addWidget(self.equity_card)

        self.pnl_card = MetricCard("OPEN P&L", "$0.00", "0 Active Positions")
        metrics_row.addWidget(self.pnl_card)

        self.trades_card = MetricCard("TRADES LIMIT", "0%", "0 / 10", show_progress=True)
        metrics_row.addWidget(self.trades_card)

        self.loss_card = MetricCard("DAILY LOSS", "0%", "$0 / $500", show_progress=True)
        metrics_row.addWidget(self.loss_card)

        left_column.addLayout(metrics_row)

        # Chart
        self.chart = ChartWidget()
        left_column.addWidget(self.chart, stretch=2)

        # Agent control matrix
        matrix_frame = QFrame()
        matrix_frame.setObjectName("card")
        matrix_layout = QVBoxLayout(matrix_frame)

        matrix_title = QLabel("MULTI-AGENT CONTROL MATRIX")
        matrix_title.setObjectName("sectionTitle")
        matrix_layout.addWidget(matrix_title)

        agents_grid = QGridLayout()
        agents_grid.setSpacing(12)

        self.agent_cards = {}
        agents = [
            ("Orchestrator", "CORE RUNTIME"),
            ("Analyst", "LMM-V3"),
            ("Sentiment", "X/NEWS FEED"),
            ("Strategy", "SCALP_HFT_01"),
            ("Risk", "GLOBAL_MONITOR"),
            ("Execution", "BRIDGE_ACTIVE"),
        ]

        for i, (name, type_info) in enumerate(agents):
            card = AgentStatusCard(name, type_info)
            card.clicked.connect(self.agent_clicked.emit)
            agents_grid.addWidget(card, i // 3, i % 3)
            self.agent_cards[name.lower()] = card

        matrix_layout.addLayout(agents_grid)
        left_column.addWidget(matrix_frame)

        content_layout.addLayout(left_column, stretch=3)

        # Right column - signals and logs
        right_column = QVBoxLayout()
        right_column.setSpacing(20)

        # Signals
        self.signals_card = SignalCard()
        right_column.addWidget(self.signals_card)

        # Cognition feed
        self.cognition_feed = CognitionFeed()
        right_column.addWidget(self.cognition_feed, stretch=1)

        content_layout.addLayout(right_column, stretch=1)

        layout.addWidget(content, stretch=1)

        # ==================== BOTTOM BAR ====================
        bottom_bar = QFrame()
        bottom_bar.setObjectName("topBar")
        bottom_bar.setFixedHeight(64)
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(20, 0, 20, 0)

        # Nav buttons
        nav_buttons = ["Home", "Market", "Trades", "Portfolio"]
        for btn_text in nav_buttons:
            btn = QPushButton(btn_text)
            btn.setObjectName("navButton")
            btn.setCheckable(True)
            if btn_text == "Home":
                btn.setChecked(True)
            bottom_layout.addWidget(btn)

        bottom_layout.addStretch()

        # Control buttons
        self.start_btn = QPushButton("START CYCLE")
        self.start_btn.setObjectName("startButton")
        self.start_btn.setMinimumWidth(120)
        self.start_btn.clicked.connect(self._on_start_clicked)
        bottom_layout.addWidget(self.start_btn)

        self.pause_btn = QPushButton("PAUSE")
        self.pause_btn.setObjectName("pauseButton")
        self.pause_btn.setMinimumWidth(100)
        self.pause_btn.clicked.connect(self._on_pause_clicked)
        bottom_layout.addWidget(self.pause_btn)

        bottom_layout.addSpacing(20)

        # Emergency halt
        self.halt_btn = QPushButton("⊘  EMERGENCY HALT")
        self.halt_btn.setObjectName("emergencyHalt")
        self.halt_btn.clicked.connect(self._on_halt_clicked)
        bottom_layout.addWidget(self.halt_btn)

        layout.addWidget(bottom_bar)

    def _update_clock(self):
        """Update the clock display."""
        now = datetime.utcnow()
        self.clock_label.setText(f"UTC {now.strftime('%H:%M:%S')}")

    def _on_start_clicked(self):
        """Handle start button click."""
        self.is_running = True
        self.start_btn.setText("RUNNING")
        self.start_btn.setEnabled(False)
        self.start_cycle.emit()

    def _on_pause_clicked(self):
        """Handle pause button click."""
        if self.is_running:
            self.is_running = False
            self.start_btn.setText("START CYCLE")
            self.start_btn.setEnabled(True)
            self.pause_cycle.emit()

    def _on_halt_clicked(self):
        """Handle emergency halt."""
        self.is_running = False
        self.start_btn.setText("START CYCLE")
        self.start_btn.setEnabled(True)
        self.emergency_halt.emit()

    def update_prices(self, prices: dict[str, dict]):
        """Update price displays."""
        for symbol, price_data in prices.items():
            if symbol in self.price_labels:
                bid = price_data.get("bid", 0)
                self.price_labels[symbol].setText(f"{bid:.5f}")

    def update_account(self, account: dict):
        """Update account metrics."""
        balance = account.get("balance", 0)
        equity = account.get("equity", 0)
        profit = account.get("floating_pnl", 0)
        positions = account.get("open_positions", 0)

        # Equity card
        self.equity_card.set_value(f"${equity:,.2f}")
        change = ((equity - balance) / balance * 100) if balance > 0 else 0
        color = "#00d4aa" if change >= 0 else "#ef4444"
        self.equity_card.set_subtitle(f"{change:+.1f}% Today", color)

        # P&L card
        pnl_color = "#00d4aa" if profit >= 0 else "#ef4444"
        self.pnl_card.set_value(f"${profit:+,.2f}", pnl_color)
        self.pnl_card.set_subtitle(f"{positions} Active Positions")

    def update_risk_metrics(self, trade_count: int, max_trades: int, daily_loss: float, max_loss: float):
        """Update risk metric cards."""
        # Trades limit
        trade_pct = int(trade_count / max_trades * 100) if max_trades > 0 else 0
        self.trades_card.set_value(f"{trade_pct}%")
        self.trades_card.set_subtitle(f"{trade_count} / {max_trades}")
        self.trades_card.set_progress(trade_pct, warning=trade_pct > 70)

        # Daily loss
        loss_pct = int(daily_loss / max_loss * 100) if max_loss > 0 else 0
        self.loss_card.set_value(f"{loss_pct}%", "#ef4444" if loss_pct > 50 else "#ffffff")
        self.loss_card.set_subtitle(f"${daily_loss:.0f} / ${max_loss:.0f}")
        self.loss_card.set_progress(loss_pct, warning=loss_pct > 50, danger=loss_pct > 80)

    def update_agent_status(self, statuses: dict[str, dict]):
        """Update agent status cards."""
        for agent_name, status in statuses.items():
            if agent_name in self.agent_cards:
                self.agent_cards[agent_name].set_status(
                    status.get("status", "idle"),
                    status.get("info", "")
                )

    def set_mode(self, is_paper: bool):
        """Set trading mode display."""
        self.is_paper_mode = is_paper
        if is_paper:
            self.mode_badge.setText("PAPER MODE")
            self.mode_badge.setObjectName("badgePaper")
        else:
            self.mode_badge.setText("LIVE")
            self.mode_badge.setObjectName("badgeLive")
        self.mode_badge.setStyleSheet(self.mode_badge.styleSheet())
