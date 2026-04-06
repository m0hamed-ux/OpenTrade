"""Risk monitor view with gauges and circuit breaker controls."""

from typing import Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGridLayout, QProgressBar, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QSpacerItem, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QFont

import math


class GaugeWidget(QWidget):
    """Circular gauge widget for risk metrics."""

    def __init__(
        self,
        title: str = "",
        max_value: float = 100,
        warning_threshold: float = 70,
        danger_threshold: float = 90,
        parent=None
    ):
        super().__init__(parent)
        self.title = title
        self.value = 0
        self.max_value = max_value
        self.warning_threshold = warning_threshold
        self.danger_threshold = danger_threshold
        self.setMinimumSize(150, 150)

    def set_value(self, value: float):
        """Set gauge value."""
        self.value = min(value, self.max_value)
        self.update()

    def paintEvent(self, event):
        """Paint the gauge."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()
        size = min(width, height) - 20

        # Center
        cx = width // 2
        cy = height // 2 - 10

        # Background arc
        pen = QPen(QColor("#1f2937"))
        pen.setWidth(12)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        rect = (cx - size // 2, cy - size // 2, size, size)
        painter.drawArc(*rect, 225 * 16, -270 * 16)

        # Value arc
        percent = self.value / self.max_value
        if percent > self.danger_threshold / 100:
            color = QColor("#ef4444")
        elif percent > self.warning_threshold / 100:
            color = QColor("#fbbf24")
        else:
            color = QColor("#00d4aa")

        pen.setColor(color)
        painter.setPen(pen)

        angle = int(-270 * percent * 16)
        painter.drawArc(*rect, 225 * 16, angle)

        # Value text
        painter.setPen(QPen(QColor("#e8eaed")))
        font = QFont()
        font.setPointSize(24)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            0, cy - 20, width, 50,
            Qt.AlignmentFlag.AlignCenter,
            f"{self.value:.1f}%"
        )

        # Title
        font.setPointSize(10)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QPen(QColor("#9ca3af")))
        painter.drawText(
            0, cy + 25, width, 30,
            Qt.AlignmentFlag.AlignCenter,
            self.title
        )

        painter.end()


class RiskMonitor(QWidget):
    """Risk monitoring view with circuit breaker controls."""

    reset_circuit_breaker = pyqtSignal()
    close_all_positions = pyqtSignal()
    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        """Setup risk monitor UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QHBoxLayout()

        title = QLabel("RISK MONITOR")
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #e8eaed;")
        header.addWidget(title)

        header.addStretch()

        close_btn = QPushButton("← Back to Dashboard")
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)

        layout.addLayout(header)

        # Gauges row
        gauges_frame = QFrame()
        gauges_frame.setObjectName("card")
        gauges_layout = QHBoxLayout(gauges_frame)
        gauges_layout.setSpacing(40)

        # Drawdown gauge
        self.drawdown_gauge = GaugeWidget(
            title="CURRENT DRAWDOWN",
            max_value=10,
            warning_threshold=50,
            danger_threshold=80
        )
        gauges_layout.addWidget(self.drawdown_gauge)

        # Daily loss gauge
        self.daily_loss_gauge = GaugeWidget(
            title="DAILY LOSS USED",
            max_value=100,
            warning_threshold=60,
            danger_threshold=80
        )
        gauges_layout.addWidget(self.daily_loss_gauge)

        # Trade count gauge
        self.trade_gauge = GaugeWidget(
            title="TRADES USED",
            max_value=100,
            warning_threshold=70,
            danger_threshold=90
        )
        gauges_layout.addWidget(self.trade_gauge)

        # Margin usage gauge
        self.margin_gauge = GaugeWidget(
            title="MARGIN USAGE",
            max_value=100,
            warning_threshold=50,
            danger_threshold=80
        )
        gauges_layout.addWidget(self.margin_gauge)

        layout.addWidget(gauges_frame)

        # Main content grid
        content = QHBoxLayout()
        content.setSpacing(20)

        # Left column - positions
        left_frame = QFrame()
        left_frame.setObjectName("card")
        left_layout = QVBoxLayout(left_frame)

        positions_title = QLabel("POSITION EXPOSURE")
        positions_title.setObjectName("sectionTitle")
        left_layout.addWidget(positions_title)

        self.positions_table = QTableWidget()
        self.positions_table.setColumnCount(6)
        self.positions_table.setHorizontalHeaderLabels([
            "Symbol", "Type", "Volume", "Entry", "Current P&L", "Exposure %"
        ])
        self.positions_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        left_layout.addWidget(self.positions_table)

        # Summary
        summary_layout = QGridLayout()

        summary_layout.addWidget(QLabel("Total Exposure:"), 0, 0)
        self.total_exposure_label = QLabel("$0.00")
        self.total_exposure_label.setStyleSheet("font-weight: 700;")
        summary_layout.addWidget(self.total_exposure_label, 0, 1)

        summary_layout.addWidget(QLabel("Correlation Risk:"), 0, 2)
        self.correlation_label = QLabel("LOW")
        self.correlation_label.setStyleSheet("font-weight: 700; color: #00d4aa;")
        summary_layout.addWidget(self.correlation_label, 0, 3)

        summary_layout.addWidget(QLabel("Total Floating P&L:"), 1, 0)
        self.floating_pnl_label = QLabel("$0.00")
        self.floating_pnl_label.setStyleSheet("font-weight: 700;")
        summary_layout.addWidget(self.floating_pnl_label, 1, 1)

        summary_layout.addWidget(QLabel("Max Position Size:"), 1, 2)
        self.max_position_label = QLabel("0.00 lots")
        summary_layout.addWidget(self.max_position_label, 1, 3)

        left_layout.addLayout(summary_layout)

        content.addWidget(left_frame, stretch=2)

        # Right column - circuit breaker
        right_frame = QFrame()
        right_frame.setObjectName("card")
        right_layout = QVBoxLayout(right_frame)

        cb_title = QLabel("CIRCUIT BREAKER")
        cb_title.setObjectName("sectionTitle")
        right_layout.addWidget(cb_title)

        # Status
        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1f2e;
                border: 1px solid #2a3441;
                border-radius: 8px;
                padding: 16px;
            }
        """)
        status_layout = QVBoxLayout(status_frame)

        status_row = QHBoxLayout()
        status_row.addWidget(QLabel("Status:"))
        self.cb_status_label = QLabel("ACTIVE")
        self.cb_status_label.setStyleSheet("font-weight: 700; color: #00d4aa;")
        status_row.addWidget(self.cb_status_label)
        status_row.addStretch()
        status_layout.addLayout(status_row)

        trip_row = QHBoxLayout()
        trip_row.addWidget(QLabel("Trip Reason:"))
        self.trip_reason_label = QLabel("None")
        self.trip_reason_label.setStyleSheet("color: #9ca3af;")
        trip_row.addWidget(self.trip_reason_label)
        trip_row.addStretch()
        status_layout.addLayout(trip_row)

        right_layout.addWidget(status_frame)

        # Limits
        limits_group = QGroupBox("Configured Limits")
        limits_layout = QGridLayout(limits_group)

        limits_layout.addWidget(QLabel("Max Daily Loss:"), 0, 0)
        self.max_loss_limit = QLabel("5.0%")
        limits_layout.addWidget(self.max_loss_limit, 0, 1)

        limits_layout.addWidget(QLabel("Max Trades/Day:"), 1, 0)
        self.max_trades_limit = QLabel("10")
        limits_layout.addWidget(self.max_trades_limit, 1, 1)

        limits_layout.addWidget(QLabel("Max Open Positions:"), 2, 0)
        self.max_positions_limit = QLabel("3")
        limits_layout.addWidget(self.max_positions_limit, 2, 1)

        limits_layout.addWidget(QLabel("Max Risk/Trade:"), 3, 0)
        self.max_risk_limit = QLabel("2.0%")
        limits_layout.addWidget(self.max_risk_limit, 3, 1)

        right_layout.addWidget(limits_group)

        # Current state
        state_group = QGroupBox("Current State")
        state_layout = QGridLayout(state_group)

        state_layout.addWidget(QLabel("Starting Balance:"), 0, 0)
        self.starting_balance_label = QLabel("$0.00")
        state_layout.addWidget(self.starting_balance_label, 0, 1)

        state_layout.addWidget(QLabel("Current Equity:"), 1, 0)
        self.current_equity_label = QLabel("$0.00")
        state_layout.addWidget(self.current_equity_label, 1, 1)

        state_layout.addWidget(QLabel("Trade Count:"), 2, 0)
        self.trade_count_label = QLabel("0")
        state_layout.addWidget(self.trade_count_label, 2, 1)

        state_layout.addWidget(QLabel("Daily P&L:"), 3, 0)
        self.daily_pnl_label = QLabel("$0.00")
        state_layout.addWidget(self.daily_pnl_label, 3, 1)

        right_layout.addWidget(state_group)

        right_layout.addStretch()

        # Manual controls
        controls_title = QLabel("MANUAL OVERRIDE")
        controls_title.setObjectName("sectionTitle")
        right_layout.addWidget(controls_title)

        reset_btn = QPushButton("Reset Circuit Breaker")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #fbbf24;
                color: #0a0e17;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #fcd34d;
            }
        """)
        reset_btn.clicked.connect(self.reset_circuit_breaker.emit)
        right_layout.addWidget(reset_btn)

        close_all_btn = QPushButton("Close All Positions")
        close_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc2626;
                color: #ffffff;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #ef4444;
            }
        """)
        close_all_btn.clicked.connect(self.close_all_positions.emit)
        right_layout.addWidget(close_all_btn)

        content.addWidget(right_frame, stretch=1)

        layout.addLayout(content)

    def update_metrics(
        self,
        drawdown: float,
        daily_loss_pct: float,
        trade_pct: float,
        margin_pct: float
    ):
        """Update gauge values."""
        self.drawdown_gauge.set_value(drawdown)
        self.daily_loss_gauge.set_value(daily_loss_pct)
        self.trade_gauge.set_value(trade_pct)
        self.margin_gauge.set_value(margin_pct)

    def update_positions(self, positions: list[dict], account: dict):
        """Update positions table and summary."""
        self.positions_table.setRowCount(len(positions))

        total_exposure = 0
        total_pnl = 0
        balance = account.get("balance", 1)

        for row, pos in enumerate(positions):
            self.positions_table.setItem(row, 0, QTableWidgetItem(pos.get("symbol", "")))

            type_item = QTableWidgetItem(pos.get("type", ""))
            if pos.get("type") == "BUY":
                type_item.setForeground(QColor("#00d4aa"))
            else:
                type_item.setForeground(QColor("#ef4444"))
            self.positions_table.setItem(row, 1, type_item)

            self.positions_table.setItem(row, 2, QTableWidgetItem(f"{pos.get('volume', 0):.2f}"))
            self.positions_table.setItem(row, 3, QTableWidgetItem(f"{pos.get('price_open', 0):.5f}"))

            pnl = pos.get("profit", 0)
            pnl_item = QTableWidgetItem(f"${pnl:+.2f}")
            if pnl >= 0:
                pnl_item.setForeground(QColor("#00d4aa"))
            else:
                pnl_item.setForeground(QColor("#ef4444"))
            self.positions_table.setItem(row, 4, pnl_item)

            exposure = pos.get("volume", 0) * 100000 * pos.get("price_open", 1)
            exposure_pct = exposure / balance * 100 if balance > 0 else 0
            self.positions_table.setItem(row, 5, QTableWidgetItem(f"{exposure_pct:.1f}%"))

            total_exposure += exposure
            total_pnl += pnl

        # Update summary
        self.total_exposure_label.setText(f"${total_exposure:,.2f}")
        self.floating_pnl_label.setText(f"${total_pnl:+.2f}")
        color = "#00d4aa" if total_pnl >= 0 else "#ef4444"
        self.floating_pnl_label.setStyleSheet(f"font-weight: 700; color: {color};")

        # Correlation risk
        symbols = [p.get("symbol", "") for p in positions]
        usd_count = sum(1 for s in symbols if "USD" in s)
        if usd_count > 2:
            self.correlation_label.setText("HIGH")
            self.correlation_label.setStyleSheet("font-weight: 700; color: #ef4444;")
        elif usd_count > 1:
            self.correlation_label.setText("MEDIUM")
            self.correlation_label.setStyleSheet("font-weight: 700; color: #fbbf24;")
        else:
            self.correlation_label.setText("LOW")
            self.correlation_label.setStyleSheet("font-weight: 700; color: #00d4aa;")

    def update_circuit_breaker(self, status: dict):
        """Update circuit breaker display."""
        is_tripped = status.get("is_tripped", False)

        if is_tripped:
            self.cb_status_label.setText("TRIPPED")
            self.cb_status_label.setStyleSheet("font-weight: 700; color: #ef4444;")
            self.trip_reason_label.setText(status.get("trip_reason", "Unknown"))
        else:
            self.cb_status_label.setText("ACTIVE")
            self.cb_status_label.setStyleSheet("font-weight: 700; color: #00d4aa;")
            self.trip_reason_label.setText("None")

        # Limits
        self.max_loss_limit.setText(f"{status.get('max_daily_loss_percent', 5.0)}%")
        self.max_trades_limit.setText(str(status.get("max_trades", 10)))

        # State
        self.starting_balance_label.setText(f"${status.get('starting_balance', 0):,.2f}")
        self.trade_count_label.setText(f"{status.get('trade_count', 0)} / {status.get('max_trades', 10)}")
        self.daily_pnl_label.setText(f"${status.get('daily_pnl', 0):+.2f}")

    def update_account(self, account: dict):
        """Update account info."""
        self.current_equity_label.setText(f"${account.get('equity', 0):,.2f}")
        self.max_position_label.setText(f"{account.get('free_margin', 0) / 1000:.2f} lots")
