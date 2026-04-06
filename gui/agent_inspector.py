"""Agent inspector for debugging agent decisions."""

from datetime import datetime
from typing import Any

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTextEdit, QSplitter, QTabWidget, QScrollArea,
    QGridLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QSyntaxHighlighter, QTextCharFormat, QColor

import json


class JsonHighlighter(QSyntaxHighlighter):
    """Syntax highlighter for JSON content."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Define formats
        self.key_format = QTextCharFormat()
        self.key_format.setForeground(QColor("#f59e0b"))

        self.string_format = QTextCharFormat()
        self.string_format.setForeground(QColor("#00d4aa"))

        self.number_format = QTextCharFormat()
        self.number_format.setForeground(QColor("#8b5cf6"))

        self.bool_format = QTextCharFormat()
        self.bool_format.setForeground(QColor("#3b82f6"))

        self.null_format = QTextCharFormat()
        self.null_format.setForeground(QColor("#ef4444"))

    def highlightBlock(self, text: str):
        """Apply syntax highlighting."""
        import re

        # Keys
        for match in re.finditer(r'"([^"]+)"(?=\s*:)', text):
            self.setFormat(match.start(), match.end() - match.start(), self.key_format)

        # String values
        for match in re.finditer(r':\s*"([^"]*)"', text):
            self.setFormat(match.start() + 1, match.end() - match.start() - 1, self.string_format)

        # Numbers
        for match in re.finditer(r':\s*(-?\d+\.?\d*)', text):
            self.setFormat(match.start() + 1, match.end() - match.start() - 1, self.number_format)

        # Booleans
        for match in re.finditer(r'\b(true|false)\b', text):
            self.setFormat(match.start(), match.end() - match.start(), self.bool_format)

        # Null
        for match in re.finditer(r'\bnull\b', text):
            self.setFormat(match.start(), match.end() - match.start(), self.null_format)


class AgentInspector(QWidget):
    """Inspector view for debugging individual agents."""

    close_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_agent = None
        self.history = []
        self.setup_ui()

    def setup_ui(self):
        """Setup inspector UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Header
        header = QHBoxLayout()

        self.title = QLabel("AGENT INSPECTOR")
        self.title.setStyleSheet("font-size: 24px; font-weight: 700; color: #e8eaed;")
        header.addWidget(self.title)

        header.addStretch()

        # Agent selector
        self.agent_label = QLabel("Select an agent from the dashboard")
        self.agent_label.setStyleSheet("color: #9ca3af;")
        header.addWidget(self.agent_label)

        header.addSpacing(16)

        close_btn = QPushButton("← Back to Dashboard")
        close_btn.clicked.connect(self.close_requested.emit)
        header.addWidget(close_btn)

        layout.addLayout(header)

        # Agent info card
        info_card = QFrame()
        info_card.setObjectName("card")
        info_layout = QGridLayout(info_card)
        info_layout.setSpacing(16)

        # Status
        info_layout.addWidget(QLabel("Status:"), 0, 0)
        self.status_label = QLabel("--")
        self.status_label.setStyleSheet("font-weight: 700;")
        info_layout.addWidget(self.status_label, 0, 1)

        # Last run
        info_layout.addWidget(QLabel("Last Run:"), 0, 2)
        self.last_run_label = QLabel("--")
        info_layout.addWidget(self.last_run_label, 0, 3)

        # Token usage
        info_layout.addWidget(QLabel("Tokens:"), 1, 0)
        self.tokens_label = QLabel("--")
        info_layout.addWidget(self.tokens_label, 1, 1)

        # Latency
        info_layout.addWidget(QLabel("Latency:"), 1, 2)
        self.latency_label = QLabel("--")
        info_layout.addWidget(self.latency_label, 1, 3)

        # Model
        info_layout.addWidget(QLabel("Model:"), 2, 0)
        self.model_label = QLabel("--")
        info_layout.addWidget(self.model_label, 2, 1)

        # Calls today
        info_layout.addWidget(QLabel("Calls Today:"), 2, 2)
        self.calls_label = QLabel("--")
        info_layout.addWidget(self.calls_label, 2, 3)

        layout.addWidget(info_card)

        # Main content - splitter with prompt and response
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Prompt section
        prompt_frame = QFrame()
        prompt_frame.setObjectName("card")
        prompt_layout = QVBoxLayout(prompt_frame)

        prompt_header = QHBoxLayout()
        prompt_title = QLabel("LAST PROMPT")
        prompt_title.setObjectName("sectionTitle")
        prompt_header.addWidget(prompt_title)
        prompt_header.addStretch()

        copy_prompt_btn = QPushButton("Copy")
        copy_prompt_btn.clicked.connect(self._copy_prompt)
        prompt_header.addWidget(copy_prompt_btn)
        prompt_layout.addLayout(prompt_header)

        self.prompt_text = QTextEdit()
        self.prompt_text.setReadOnly(True)
        self.prompt_text.setFont(QFont("JetBrains Mono", 11))
        prompt_layout.addWidget(self.prompt_text)

        splitter.addWidget(prompt_frame)

        # Response section
        response_frame = QFrame()
        response_frame.setObjectName("card")
        response_layout = QVBoxLayout(response_frame)

        response_header = QHBoxLayout()
        response_title = QLabel("RAW RESPONSE")
        response_title.setObjectName("sectionTitle")
        response_header.addWidget(response_title)
        response_header.addStretch()

        copy_response_btn = QPushButton("Copy")
        copy_response_btn.clicked.connect(self._copy_response)
        response_header.addWidget(copy_response_btn)
        response_layout.addLayout(response_header)

        self.response_text = QTextEdit()
        self.response_text.setReadOnly(True)
        self.response_text.setFont(QFont("JetBrains Mono", 11))
        self.response_highlighter = JsonHighlighter(self.response_text.document())
        response_layout.addWidget(self.response_text)

        splitter.addWidget(response_frame)

        # Decision reasoning section
        reasoning_frame = QFrame()
        reasoning_frame.setObjectName("card")
        reasoning_layout = QVBoxLayout(reasoning_frame)

        reasoning_title = QLabel("DECISION REASONING")
        reasoning_title.setObjectName("sectionTitle")
        reasoning_layout.addWidget(reasoning_title)

        self.reasoning_text = QTextEdit()
        self.reasoning_text.setReadOnly(True)
        self.reasoning_text.setMaximumHeight(150)
        reasoning_layout.addWidget(self.reasoning_text)

        splitter.addWidget(reasoning_frame)

        splitter.setSizes([300, 300, 150])
        layout.addWidget(splitter, stretch=1)

        # History tabs
        history_frame = QFrame()
        history_frame.setObjectName("card")
        history_layout = QVBoxLayout(history_frame)

        history_header = QHBoxLayout()
        history_title = QLabel("RECENT CALLS")
        history_title.setObjectName("sectionTitle")
        history_header.addWidget(history_title)
        history_header.addStretch()

        clear_btn = QPushButton("Clear History")
        clear_btn.clicked.connect(self._clear_history)
        history_header.addWidget(clear_btn)
        history_layout.addLayout(history_header)

        self.history_scroll = QScrollArea()
        self.history_scroll.setWidgetResizable(True)
        self.history_scroll.setMaximumHeight(120)

        self.history_container = QWidget()
        self.history_layout = QHBoxLayout(self.history_container)
        self.history_layout.setContentsMargins(0, 0, 0, 0)
        self.history_layout.addStretch()

        self.history_scroll.setWidget(self.history_container)
        history_layout.addWidget(self.history_scroll)

        layout.addWidget(history_frame)

    def set_agent(self, agent_name: str):
        """Set the current agent to inspect."""
        self.current_agent = agent_name
        self.agent_label.setText(f"Inspecting: {agent_name}")
        self.title.setText(f"AGENT INSPECTOR - {agent_name.upper()}")

    def update_data(self, data: dict):
        """Update inspector with new agent data.

        Args:
            data: Dict with prompt, response, status, tokens, latency, etc.
        """
        # Update status
        status = data.get("status", "unknown")
        color = {
            "running": "#00d4aa",
            "idle": "#6b7280",
            "working": "#fbbf24",
            "error": "#ef4444",
        }.get(status.lower(), "#9ca3af")
        self.status_label.setText(status.upper())
        self.status_label.setStyleSheet(f"font-weight: 700; color: {color};")

        # Update metrics
        self.last_run_label.setText(data.get("last_run", "--"))
        self.tokens_label.setText(f"{data.get('tokens', 0):,}")
        self.latency_label.setText(f"{data.get('latency_ms', 0)}ms")
        self.model_label.setText(data.get("model", "gemini-2.5-pro"))
        self.calls_label.setText(str(data.get("calls_today", 0)))

        # Update prompt
        prompt = data.get("prompt", "")
        self.prompt_text.setPlainText(prompt)

        # Update response
        response = data.get("response", "")
        if isinstance(response, dict):
            response = json.dumps(response, indent=2)
        self.response_text.setPlainText(response)

        # Update reasoning
        reasoning = data.get("reasoning", "")
        if not reasoning and isinstance(data.get("response"), dict):
            reasoning = data["response"].get("entry_reason") or data["response"].get("summary", "")
        self.reasoning_text.setPlainText(reasoning)

        # Add to history
        self._add_to_history(data)

    def _add_to_history(self, data: dict):
        """Add entry to history."""
        timestamp = datetime.now().strftime("%H:%M:%S")

        btn = QPushButton(timestamp)
        btn.setFixedWidth(80)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #1f2937;
                border: 1px solid #374151;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #374151;
            }
        """)

        # Store data in button
        btn.setProperty("data", data)
        btn.clicked.connect(lambda: self.update_data(btn.property("data")))

        # Insert at beginning
        self.history_layout.insertWidget(0, btn)

        # Keep only last 10
        while self.history_layout.count() > 11:  # 10 + stretch
            item = self.history_layout.takeAt(10)
            if item.widget():
                item.widget().deleteLater()

        self.history.insert(0, data)
        self.history = self.history[:10]

    def _copy_prompt(self):
        """Copy prompt to clipboard."""
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.prompt_text.toPlainText())

    def _copy_response(self):
        """Copy response to clipboard."""
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.response_text.toPlainText())

    def _clear_history(self):
        """Clear history."""
        while self.history_layout.count() > 1:
            item = self.history_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.history.clear()
