"""Async workers for background tasks using QThread."""

from typing import Any, Callable
from datetime import datetime

from PyQt6.QtCore import QThread, QObject, pyqtSignal, QTimer, QMutex


class WorkerSignals(QObject):
    """Signals for worker communication."""
    finished = pyqtSignal()
    error = pyqtSignal(str)
    result = pyqtSignal(object)
    progress = pyqtSignal(int)


class AsyncWorker(QThread):
    """Generic async worker for running tasks in background."""

    def __init__(self, func: Callable, *args, **kwargs):
        """Initialize worker with function to run.

        Args:
            func: Async or sync function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments
        """
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()
        self._is_running = True

    def run(self):
        """Execute the function in the thread."""
        try:
            import asyncio

            # Check if function is async
            if asyncio.iscoroutinefunction(self.func):
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result = loop.run_until_complete(
                        self.func(*self.args, **self.kwargs)
                    )
                finally:
                    loop.close()
            else:
                result = self.func(*self.args, **self.kwargs)

            if self._is_running:
                self.signals.result.emit(result)

        except Exception as e:
            if self._is_running:
                self.signals.error.emit(str(e))

        finally:
            self.signals.finished.emit()

    def stop(self):
        """Stop the worker."""
        self._is_running = False
        self.quit()
        self.wait()


class AgentStatusPoller(QThread):
    """Polls agent status every 500ms."""

    status_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, get_status_func: Callable):
        """Initialize poller.

        Args:
            get_status_func: Function that returns agent status dict
        """
        super().__init__()
        self.get_status_func = get_status_func
        self._running = True
        self._interval_ms = 500

    def run(self):
        """Poll status in a loop."""
        import asyncio
        import time

        while self._running:
            try:
                if asyncio.iscoroutinefunction(self.get_status_func):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    try:
                        status = loop.run_until_complete(self.get_status_func())
                    finally:
                        loop.close()
                else:
                    status = self.get_status_func()

                self.status_updated.emit(status)

            except Exception as e:
                self.error_occurred.emit(str(e))

            time.sleep(self._interval_ms / 1000)

    def stop(self):
        """Stop polling."""
        self._running = False
        self.quit()
        self.wait()


class PriceUpdateWorker(QThread):
    """Updates prices for watched symbols."""

    prices_updated = pyqtSignal(dict)  # {symbol: {bid, ask, spread}}
    error_occurred = pyqtSignal(str)

    def __init__(self, get_prices_func: Callable, symbols: list[str]):
        """Initialize price worker.

        Args:
            get_prices_func: Async function to get prices
            symbols: List of symbols to watch
        """
        super().__init__()
        self.get_prices_func = get_prices_func
        self.symbols = symbols
        self._running = True
        self._interval_ms = 1000  # 1 second

    def run(self):
        """Fetch prices in a loop."""
        import asyncio
        import time

        while self._running:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    prices = {}
                    for symbol in self.symbols:
                        price = loop.run_until_complete(
                            self.get_prices_func(symbol)
                        )
                        if price:
                            prices[symbol] = price
                finally:
                    loop.close()

                if prices:
                    self.prices_updated.emit(prices)

            except Exception as e:
                self.error_occurred.emit(str(e))

            time.sleep(self._interval_ms / 1000)

    def update_symbols(self, symbols: list[str]):
        """Update watched symbols."""
        self.symbols = symbols

    def stop(self):
        """Stop worker."""
        self._running = False
        self.quit()
        self.wait()


class TradingCycleWorker(QThread):
    """Runs trading cycles in background."""

    cycle_started = pyqtSignal(str)  # symbol
    cycle_completed = pyqtSignal(dict)  # result
    cycle_error = pyqtSignal(str, str)  # symbol, error
    trade_executed = pyqtSignal(dict)  # trade details

    def __init__(self, run_cycle_func: Callable, symbols: list[str], interval: int):
        """Initialize cycle worker.

        Args:
            run_cycle_func: Async function to run a cycle
            symbols: Symbols to trade
            interval: Seconds between cycles
        """
        super().__init__()
        self.run_cycle_func = run_cycle_func
        self.symbols = symbols
        self.interval = interval
        self._running = True
        self._paused = False
        self._mutex = QMutex()

    def run(self):
        """Run trading cycles."""
        import asyncio
        import time

        while self._running:
            if not self._paused:
                for symbol in self.symbols:
                    if not self._running or self._paused:
                        break

                    self.cycle_started.emit(symbol)

                    try:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            result = loop.run_until_complete(
                                self.run_cycle_func(symbol)
                            )
                        finally:
                            loop.close()

                        self.cycle_completed.emit(result)

                        # Check if trade was executed
                        if result.get("execution_result", {}).get("success"):
                            self.trade_executed.emit(result["execution_result"])

                    except Exception as e:
                        self.cycle_error.emit(symbol, str(e))

            time.sleep(self.interval)

    def pause(self):
        """Pause trading."""
        self._mutex.lock()
        self._paused = True
        self._mutex.unlock()

    def resume(self):
        """Resume trading."""
        self._mutex.lock()
        self._paused = False
        self._mutex.unlock()

    @property
    def is_paused(self) -> bool:
        """Check if paused."""
        return self._paused

    def stop(self):
        """Stop worker."""
        self._running = False
        self.quit()
        self.wait()


class LogEntry:
    """Represents a log entry."""

    def __init__(
        self,
        timestamp: datetime,
        agent: str,
        level: str,
        message: str,
    ):
        self.timestamp = timestamp
        self.agent = agent
        self.level = level
        self.message = message


class LogBuffer(QObject):
    """Thread-safe log buffer with signals."""

    log_added = pyqtSignal(object)  # LogEntry
    logs_cleared = pyqtSignal()

    def __init__(self, max_entries: int = 500):
        super().__init__()
        self._entries: list[LogEntry] = []
        self._max_entries = max_entries
        self._mutex = QMutex()

    def add(self, agent: str, level: str, message: str):
        """Add a log entry."""
        entry = LogEntry(
            timestamp=datetime.now(),
            agent=agent,
            level=level,
            message=message,
        )

        self._mutex.lock()
        self._entries.append(entry)

        # Trim if over max
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        self._mutex.unlock()

        self.log_added.emit(entry)

    def get_entries(self, count: int | None = None) -> list[LogEntry]:
        """Get log entries."""
        self._mutex.lock()
        if count:
            entries = self._entries[-count:]
        else:
            entries = self._entries.copy()
        self._mutex.unlock()
        return entries

    def clear(self):
        """Clear all entries."""
        self._mutex.lock()
        self._entries.clear()
        self._mutex.unlock()
        self.logs_cleared.emit()


class AccountUpdateWorker(QThread):
    """Updates account info periodically."""

    account_updated = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, get_account_func: Callable):
        """Initialize worker.

        Args:
            get_account_func: Async function to get account info
        """
        super().__init__()
        self.get_account_func = get_account_func
        self._running = True
        self._interval_ms = 2000  # 2 seconds

    def run(self):
        """Fetch account info in a loop."""
        import asyncio
        import time

        while self._running:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    account = loop.run_until_complete(self.get_account_func())
                finally:
                    loop.close()

                self.account_updated.emit(account)

            except Exception as e:
                self.error_occurred.emit(str(e))

            time.sleep(self._interval_ms / 1000)

    def stop(self):
        """Stop worker."""
        self._running = False
        self.quit()
        self.wait()
