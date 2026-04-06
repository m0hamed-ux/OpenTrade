"""Trade journal view with table and charts."""

from datetime import datetime, date
from typing import Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QDateEdit, QSplitter, QTabWidget, QFileDialog,
    QAbstractItemView, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QDate
from PyQt6.QtGui import QColor

import pyqtgraph as pg


class JournalView(QWidget):
    """Trade journal with filterable table and performance charts."""

    trade_selected = pyqtSignal(dict)  # Emits trade details

    def __init__(self, parent=None):
        super().__init__(parent)
        self.trades = []
        self.setup_ui()

    def setup_ui(self):
        """Setup journal UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QHBoxLayout()

        title = QLabel("TRADE JOURNAL")
        title.setStyleSheet("font-size: 24px; font-weight: 700; color: #e8eaed;")
        header.addWidget(title)

        header.addStretch()

        # Filters
        self.symbol_filter = QComboBox()
        self.symbol_filter.addItem("All Symbols")
        self.symbol_filter.addItems(["EURUSD", "GBPUSD", "USDJPY"])
        self.symbol_filter.currentTextChanged.connect(self._apply_filters)
        header.addWidget(self.symbol_filter)

        header.addSpacing(8)

        self.date_from = QDateEdit()
        self.date_from.setDate(QDate.currentDate().addDays(-30))
        self.date_from.setCalendarPopup(True)
        self.date_from.dateChanged.connect(self._apply_filters)
        header.addWidget(QLabel("From:"))
        header.addWidget(self.date_from)

        header.addSpacing(8)

        self.date_to = QDateEdit()
        self.date_to.setDate(QDate.currentDate())
        self.date_to.setCalendarPopup(True)
        self.date_to.dateChanged.connect(self._apply_filters)
        header.addWidget(QLabel("To:"))
        header.addWidget(self.date_to)

        header.addSpacing(16)

        export_btn = QPushButton("Export CSV")
        export_btn.clicked.connect(self._export_csv)
        header.addWidget(export_btn)

        layout.addLayout(header)

        # Main content splitter
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Trade table
        table_frame = QFrame()
        table_frame.setObjectName("card")
        table_layout = QVBoxLayout(table_frame)

        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels([
            "Date/Time", "Symbol", "Type", "Entry", "Exit",
            "Lots", "SL", "TP", "P&L", "Reason"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.setAlternatingRowColors(True)

        table_layout.addWidget(self.table)
        splitter.addWidget(table_frame)

        # Charts
        charts_frame = QFrame()
        charts_frame.setObjectName("card")
        charts_layout = QVBoxLayout(charts_frame)

        chart_tabs = QTabWidget()

        # Equity curve tab
        equity_tab = QWidget()
        equity_layout = QVBoxLayout(equity_tab)
        self.equity_chart = pg.PlotWidget()
        self.equity_chart.setBackground("#111827")
        self.equity_chart.showGrid(x=True, y=True, alpha=0.1)
        self.equity_chart.setLabel("left", "Equity", color="#9ca3af")
        self.equity_chart.setLabel("bottom", "Trade #", color="#9ca3af")
        equity_layout.addWidget(self.equity_chart)
        chart_tabs.addTab(equity_tab, "Equity Curve")

        # Win rate by symbol tab
        winrate_tab = QWidget()
        winrate_layout = QVBoxLayout(winrate_tab)
        self.winrate_chart = pg.PlotWidget()
        self.winrate_chart.setBackground("#111827")
        self.winrate_chart.showGrid(y=True, alpha=0.1)
        self.winrate_chart.setLabel("left", "Win Rate %", color="#9ca3af")
        winrate_layout.addWidget(self.winrate_chart)
        chart_tabs.addTab(winrate_tab, "Win Rate by Symbol")

        # P&L distribution tab
        pnl_tab = QWidget()
        pnl_layout = QVBoxLayout(pnl_tab)
        self.pnl_chart = pg.PlotWidget()
        self.pnl_chart.setBackground("#111827")
        self.pnl_chart.showGrid(y=True, alpha=0.1)
        self.pnl_chart.setLabel("left", "Count", color="#9ca3af")
        self.pnl_chart.setLabel("bottom", "P&L", color="#9ca3af")
        pnl_layout.addWidget(self.pnl_chart)
        chart_tabs.addTab(pnl_tab, "P&L Distribution")

        charts_layout.addWidget(chart_tabs)
        splitter.addWidget(charts_frame)

        splitter.setSizes([400, 300])
        layout.addWidget(splitter)

        # Trade details panel (expandable)
        self.details_frame = QFrame()
        self.details_frame.setObjectName("card")
        self.details_frame.setVisible(False)
        details_layout = QVBoxLayout(self.details_frame)

        details_header = QHBoxLayout()
        details_title = QLabel("TRADE DETAILS")
        details_title.setObjectName("sectionTitle")
        details_header.addWidget(details_title)
        details_header.addStretch()

        close_btn = QPushButton("×")
        close_btn.setFixedSize(24, 24)
        close_btn.clicked.connect(lambda: self.details_frame.setVisible(False))
        details_header.addWidget(close_btn)
        details_layout.addLayout(details_header)

        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(150)
        details_layout.addWidget(self.details_text)

        layout.addWidget(self.details_frame)

    def set_trades(self, trades: list[dict]):
        """Set trade data."""
        self.trades = trades
        self._populate_table(trades)
        self._update_charts(trades)

    def _populate_table(self, trades: list[dict]):
        """Populate table with trades."""
        self.table.setRowCount(len(trades))

        for row, trade in enumerate(trades):
            # Date/Time
            self.table.setItem(row, 0, QTableWidgetItem(
                trade.get("created_at", "")[:19]
            ))

            # Symbol
            self.table.setItem(row, 1, QTableWidgetItem(trade.get("symbol", "")))

            # Type
            type_item = QTableWidgetItem(trade.get("order_type", ""))
            if trade.get("order_type") == "BUY":
                type_item.setForeground(QColor("#00d4aa"))
            else:
                type_item.setForeground(QColor("#ef4444"))
            self.table.setItem(row, 2, type_item)

            # Entry
            self.table.setItem(row, 3, QTableWidgetItem(
                f"{trade.get('entry_price', 0):.5f}"
            ))

            # Exit
            exit_price = trade.get("exit_price")
            self.table.setItem(row, 4, QTableWidgetItem(
                f"{exit_price:.5f}" if exit_price else "--"
            ))

            # Lots
            self.table.setItem(row, 5, QTableWidgetItem(
                f"{trade.get('volume', 0):.2f}"
            ))

            # SL
            self.table.setItem(row, 6, QTableWidgetItem(
                f"{trade.get('stop_loss', 0):.5f}" if trade.get('stop_loss') else "--"
            ))

            # TP
            self.table.setItem(row, 7, QTableWidgetItem(
                f"{trade.get('take_profit', 0):.5f}" if trade.get('take_profit') else "--"
            ))

            # P&L
            profit = trade.get("profit", 0)
            pnl_item = QTableWidgetItem(f"${profit:+.2f}" if profit else "--")
            if profit and profit > 0:
                pnl_item.setForeground(QColor("#00d4aa"))
            elif profit and profit < 0:
                pnl_item.setForeground(QColor("#ef4444"))
            self.table.setItem(row, 8, pnl_item)

            # Reason (truncated)
            reason = trade.get("entry_reason", "")[:50]
            self.table.setItem(row, 9, QTableWidgetItem(reason))

    def _update_charts(self, trades: list[dict]):
        """Update performance charts."""
        if not trades:
            return

        # Equity curve
        self.equity_chart.clear()
        closed_trades = [t for t in trades if t.get("profit") is not None]

        if closed_trades:
            equity = [10000]  # Starting balance
            for t in closed_trades:
                equity.append(equity[-1] + t.get("profit", 0))

            self.equity_chart.plot(
                range(len(equity)),
                equity,
                pen=pg.mkPen("#00d4aa", width=2)
            )

        # Win rate by symbol
        self.winrate_chart.clear()
        symbols = {}
        for t in closed_trades:
            sym = t.get("symbol", "Unknown")
            if sym not in symbols:
                symbols[sym] = {"wins": 0, "total": 0}
            symbols[sym]["total"] += 1
            if t.get("profit", 0) > 0:
                symbols[sym]["wins"] += 1

        if symbols:
            x = list(range(len(symbols)))
            y = [s["wins"] / s["total"] * 100 if s["total"] > 0 else 0 for s in symbols.values()]

            bar = pg.BarGraphItem(
                x=x, height=y, width=0.6,
                brush=pg.mkBrush("#00d4aa")
            )
            self.winrate_chart.addItem(bar)

            # Add symbol labels
            axis = self.winrate_chart.getAxis("bottom")
            axis.setTicks([[(i, sym) for i, sym in enumerate(symbols.keys())]])

        # P&L distribution
        self.pnl_chart.clear()
        pnls = [t.get("profit", 0) for t in closed_trades if t.get("profit") is not None]

        if pnls:
            import numpy as np
            hist, bins = np.histogram(pnls, bins=20)
            bar = pg.BarGraphItem(
                x=bins[:-1], height=hist, width=(bins[1] - bins[0]) * 0.8,
                brush=pg.mkBrush("#3b82f6")
            )
            self.pnl_chart.addItem(bar)

    def _apply_filters(self):
        """Apply filters and refresh table."""
        symbol = self.symbol_filter.currentText()
        from_date = self.date_from.date().toPyDate()
        to_date = self.date_to.date().toPyDate()

        filtered = []
        for trade in self.trades:
            # Symbol filter
            if symbol != "All Symbols" and trade.get("symbol") != symbol:
                continue

            # Date filter
            trade_date_str = trade.get("created_at", "")[:10]
            if trade_date_str:
                try:
                    trade_date = datetime.fromisoformat(trade_date_str).date()
                    if trade_date < from_date or trade_date > to_date:
                        continue
                except ValueError:
                    pass

            filtered.append(trade)

        self._populate_table(filtered)
        self._update_charts(filtered)

    def _on_selection_changed(self):
        """Handle trade selection."""
        rows = self.table.selectionModel().selectedRows()
        if rows:
            row = rows[0].row()
            if row < len(self.trades):
                trade = self.trades[row]
                self._show_details(trade)
                self.trade_selected.emit(trade)

    def _show_details(self, trade: dict):
        """Show trade details panel."""
        self.details_frame.setVisible(True)

        details = f"""
<b>Symbol:</b> {trade.get('symbol', 'N/A')} | <b>Type:</b> {trade.get('order_type', 'N/A')}
<b>Entry:</b> {trade.get('entry_price', 0):.5f} | <b>Exit:</b> {trade.get('exit_price', '--')}
<b>Volume:</b> {trade.get('volume', 0):.2f} lots
<b>SL:</b> {trade.get('stop_loss', '--')} | <b>TP:</b> {trade.get('take_profit', '--')}
<b>P&L:</b> ${trade.get('profit', 0):+.2f}

<b>Entry Reason:</b>
{trade.get('entry_reason', 'N/A')}

<b>Signal Confidence:</b> {trade.get('signal_confidence', 0):.1%}
"""
        self.details_text.setHtml(details)

    def _export_csv(self):
        """Export trades to CSV."""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Trades", "trades.csv", "CSV Files (*.csv)"
        )

        if filename:
            import csv
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Date", "Symbol", "Type", "Entry", "Exit",
                    "Volume", "SL", "TP", "Profit", "Reason"
                ])
                for trade in self.trades:
                    writer.writerow([
                        trade.get("created_at", ""),
                        trade.get("symbol", ""),
                        trade.get("order_type", ""),
                        trade.get("entry_price", ""),
                        trade.get("exit_price", ""),
                        trade.get("volume", ""),
                        trade.get("stop_loss", ""),
                        trade.get("take_profit", ""),
                        trade.get("profit", ""),
                        trade.get("entry_reason", ""),
                    ])

    def add_trade(self, trade: dict):
        """Add a new trade to the journal."""
        self.trades.insert(0, trade)
        self._populate_table(self.trades)
        self._update_charts(self.trades)
