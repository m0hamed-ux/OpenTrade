"""Candlestick chart widget using pyqtgraph."""

from datetime import datetime
from typing import Any

import numpy as np
import pyqtgraph as pg
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QButtonGroup, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush


class CandlestickItem(pg.GraphicsObject):
    """Custom candlestick chart item."""

    def __init__(self, data: list[dict] | None = None):
        """Initialize candlestick item.

        Args:
            data: List of dicts with time, open, high, low, close
        """
        super().__init__()
        self.data = data or []
        self.picture = None
        self.generatePicture()

    def setData(self, data: list[dict]):
        """Set new data and redraw."""
        self.data = data
        self.generatePicture()
        self.informViewBoundsChanged()

    def generatePicture(self):
        """Generate the picture for drawing."""
        self.picture = pg.QtGui.QPicture()
        painter = pg.QtGui.QPainter(self.picture)

        if not self.data:
            painter.end()
            return

        # Colors
        bull_color = QColor("#00d4aa")
        bear_color = QColor("#ef4444")

        width = 0.6

        for i, candle in enumerate(self.data):
            o = candle.get("open", 0)
            h = candle.get("high", 0)
            l = candle.get("low", 0)
            c = candle.get("close", 0)

            if c >= o:
                color = bull_color
            else:
                color = bear_color

            # Draw wick
            painter.setPen(pg.mkPen(color, width=1))
            painter.drawLine(
                pg.QtCore.QPointF(i, l),
                pg.QtCore.QPointF(i, h)
            )

            # Draw body
            painter.setBrush(pg.mkBrush(color))
            body_top = max(o, c)
            body_bottom = min(o, c)
            body_height = max(body_top - body_bottom, 0.0001)

            painter.drawRect(
                pg.QtCore.QRectF(
                    i - width / 2,
                    body_bottom,
                    width,
                    body_height
                )
            )

        painter.end()

    def paint(self, painter, *args):
        """Paint the item."""
        if self.picture:
            painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        """Return bounding rectangle."""
        if self.picture:
            return pg.QtCore.QRectF(self.picture.boundingRect())
        return pg.QtCore.QRectF()


class ChartWidget(QWidget):
    """Candlestick chart with indicators and controls."""

    timeframe_changed = pyqtSignal(str)
    symbol_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_symbol = "EURUSD"
        self.current_timeframe = "15M"
        self.data = []
        self.support_levels = []
        self.resistance_levels = []

        self.setup_ui()

    def setup_ui(self):
        """Setup the chart UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QFrame()
        header.setObjectName("chartPanel")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)

        # Symbol label
        self.symbol_label = QLabel(self.current_symbol)
        self.symbol_label.setStyleSheet("""
            font-size: 18px;
            font-weight: 700;
            color: #e8eaed;
        """)
        header_layout.addWidget(self.symbol_label)

        # Timeframe buttons
        tf_group = QButtonGroup(self)
        tf_layout = QHBoxLayout()
        tf_layout.setSpacing(4)

        for tf in ["1M", "5M", "15M", "1H"]:
            btn = QPushButton(tf)
            btn.setObjectName("timeframeButton")
            btn.setCheckable(True)
            btn.setChecked(tf == self.current_timeframe)
            btn.clicked.connect(lambda checked, t=tf: self._on_timeframe_clicked(t))
            tf_group.addButton(btn)
            tf_layout.addWidget(btn)

        header_layout.addLayout(tf_layout)
        header_layout.addStretch()

        # OHLC info
        self.ohlc_label = QLabel("O: -- H: -- L: -- C: --")
        self.ohlc_label.setStyleSheet("color: #9ca3af; font-size: 12px;")
        header_layout.addWidget(self.ohlc_label)

        layout.addWidget(header)

        # Chart
        self.chart_container = QFrame()
        self.chart_container.setObjectName("chartPanel")
        chart_layout = QVBoxLayout(self.chart_container)
        chart_layout.setContentsMargins(8, 8, 8, 8)

        # Setup pyqtgraph
        pg.setConfigOptions(antialias=True)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("#111827")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.1)

        # Style axes
        axis_pen = pg.mkPen(color="#374151", width=1)
        self.plot_widget.getAxis("bottom").setPen(axis_pen)
        self.plot_widget.getAxis("left").setPen(axis_pen)
        self.plot_widget.getAxis("bottom").setTextPen(pg.mkPen("#9ca3af"))
        self.plot_widget.getAxis("left").setTextPen(pg.mkPen("#9ca3af"))

        # Create candlestick item
        self.candle_item = CandlestickItem()
        self.plot_widget.addItem(self.candle_item)

        # Support/resistance lines
        self.support_lines = []
        self.resistance_lines = []

        # Crosshair
        self.vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#374151", width=1, style=Qt.PenStyle.DashLine))
        self.hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#374151", width=1, style=Qt.PenStyle.DashLine))
        self.plot_widget.addItem(self.vline, ignoreBounds=True)
        self.plot_widget.addItem(self.hline, ignoreBounds=True)

        # Mouse tracking
        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)

        chart_layout.addWidget(self.plot_widget)
        layout.addWidget(self.chart_container, stretch=1)

    def _on_timeframe_clicked(self, timeframe: str):
        """Handle timeframe button click."""
        self.current_timeframe = timeframe
        self.timeframe_changed.emit(timeframe)

    def _on_mouse_moved(self, pos):
        """Handle mouse movement for crosshair."""
        if self.plot_widget.sceneBoundingRect().contains(pos):
            mouse_point = self.plot_widget.plotItem.vb.mapSceneToView(pos)
            self.vline.setPos(mouse_point.x())
            self.hline.setPos(mouse_point.y())

            # Update OHLC for hovered candle
            idx = int(mouse_point.x() + 0.5)
            if 0 <= idx < len(self.data):
                candle = self.data[idx]
                self.ohlc_label.setText(
                    f"O: {candle['open']:.5f}  H: {candle['high']:.5f}  "
                    f"L: {candle['low']:.5f}  C: {candle['close']:.5f}"
                )

    def set_data(self, data: list[dict], symbol: str | None = None):
        """Set chart data.

        Args:
            data: List of OHLCV dicts
            symbol: Optional symbol name
        """
        if symbol:
            self.current_symbol = symbol
            self.symbol_label.setText(symbol)

        self.data = data
        self.candle_item.setData(data)

        # Auto-range
        if data:
            self.plot_widget.setXRange(max(0, len(data) - 50), len(data))

            prices = [c["high"] for c in data] + [c["low"] for c in data]
            if prices:
                self.plot_widget.setYRange(min(prices) * 0.999, max(prices) * 1.001)

    def set_levels(self, support: list[float], resistance: list[float]):
        """Set support and resistance levels.

        Args:
            support: List of support prices
            resistance: List of resistance prices
        """
        # Clear existing
        for line in self.support_lines + self.resistance_lines:
            self.plot_widget.removeItem(line)
        self.support_lines.clear()
        self.resistance_lines.clear()

        # Add support lines
        for price in support[:3]:
            line = pg.InfiniteLine(
                pos=price,
                angle=0,
                pen=pg.mkPen("#00d4aa", width=1, style=Qt.PenStyle.DashLine),
                label=f"S: {price:.5f}",
                labelOpts={"color": "#00d4aa", "position": 0.05}
            )
            self.plot_widget.addItem(line)
            self.support_lines.append(line)

        # Add resistance lines
        for price in resistance[:3]:
            line = pg.InfiniteLine(
                pos=price,
                angle=0,
                pen=pg.mkPen("#ef4444", width=1, style=Qt.PenStyle.DashLine),
                label=f"R: {price:.5f}",
                labelOpts={"color": "#ef4444", "position": 0.05}
            )
            self.plot_widget.addItem(line)
            self.resistance_lines.append(line)

    def add_trade_marker(self, index: int, price: float, is_buy: bool, is_entry: bool):
        """Add a trade entry/exit marker.

        Args:
            index: Candle index
            price: Price level
            is_buy: True for buy, False for sell
            is_entry: True for entry, False for exit
        """
        color = "#00d4aa" if is_buy else "#ef4444"
        symbol = "t1" if is_entry else "t"  # Triangle up/down

        scatter = pg.ScatterPlotItem(
            [index],
            [price],
            symbol=symbol,
            size=12,
            pen=pg.mkPen(color, width=2),
            brush=pg.mkBrush(color if is_entry else None),
        )
        self.plot_widget.addItem(scatter)

    def clear_markers(self):
        """Clear all trade markers."""
        # Remove scatter items (trade markers)
        items = self.plot_widget.items()
        for item in items:
            if isinstance(item, pg.ScatterPlotItem):
                self.plot_widget.removeItem(item)


class MiniChart(QWidget):
    """Small inline chart for dashboard cards."""

    def __init__(self, parent=None, color: str = "#00d4aa"):
        super().__init__(parent)
        self.color = color
        self.data = []
        self.setMinimumHeight(40)
        self.setMinimumWidth(80)

    def set_data(self, data: list[float]):
        """Set chart data points."""
        self.data = data
        self.update()

    def paintEvent(self, event):
        """Paint the mini chart."""
        if not self.data or len(self.data) < 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        width = self.width()
        height = self.height()

        # Calculate scaling
        min_val = min(self.data)
        max_val = max(self.data)
        val_range = max_val - min_val or 1

        # Draw line
        pen = QPen(QColor(self.color))
        pen.setWidth(2)
        painter.setPen(pen)

        points = []
        for i, val in enumerate(self.data):
            x = int(i * width / (len(self.data) - 1))
            y = int(height - ((val - min_val) / val_range * height * 0.8 + height * 0.1))
            points.append((x, y))

        for i in range(len(points) - 1):
            painter.drawLine(points[i][0], points[i][1], points[i+1][0], points[i+1][1])

        painter.end()
