"""Tests for risk management components."""

import pytest
from pathlib import Path
import tempfile
import json


class TestCircuitBreaker:
    """Tests for CircuitBreaker class."""

    @pytest.fixture
    def circuit_breaker(self):
        """Create circuit breaker for testing."""
        from risk.circuit_breaker import CircuitBreaker

        return CircuitBreaker(
            max_daily_loss_percent=5.0,
            max_trades_per_day=10,
            max_open_positions=3,
            max_risk_percent=2.0,
        )

    def test_initialize_day(self, circuit_breaker):
        """Test day initialization."""
        circuit_breaker.initialize_day(10000.0)

        assert circuit_breaker._starting_balance == 10000.0
        assert circuit_breaker._trade_count == 0
        assert circuit_breaker._is_tripped is False

    def test_check_preconditions_passes(self, circuit_breaker):
        """Test preconditions pass when under limits."""
        circuit_breaker.initialize_day(10000.0)

        allowed, reason = circuit_breaker.check_preconditions(
            current_equity=9800.0,  # 2% loss, under 5% limit
            open_position_count=2,  # Under 3 max
        )

        assert allowed is True
        assert reason is None

    def test_check_preconditions_daily_loss_exceeded(self, circuit_breaker):
        """Test preconditions fail when daily loss exceeded."""
        circuit_breaker.initialize_day(10000.0)

        allowed, reason = circuit_breaker.check_preconditions(
            current_equity=9400.0,  # 6% loss, exceeds 5% limit
            open_position_count=0,
        )

        assert allowed is False
        assert "loss limit" in reason.lower()
        assert circuit_breaker._is_tripped is True

    def test_check_preconditions_max_trades_exceeded(self, circuit_breaker):
        """Test preconditions fail when max trades reached."""
        circuit_breaker.initialize_day(10000.0)

        # Record 10 trades
        for _ in range(10):
            circuit_breaker.record_trade()

        allowed, reason = circuit_breaker.check_preconditions(
            current_equity=10000.0,
            open_position_count=0,
        )

        assert allowed is False
        assert "trades" in reason.lower()

    def test_check_preconditions_max_positions_exceeded(self, circuit_breaker):
        """Test preconditions fail when max positions reached."""
        circuit_breaker.initialize_day(10000.0)

        allowed, reason = circuit_breaker.check_preconditions(
            current_equity=10000.0,
            open_position_count=3,  # At max
        )

        assert allowed is False
        assert "positions" in reason.lower()

    def test_validate_trade_within_limits(self, circuit_breaker):
        """Test trade validation passes within limits."""
        circuit_breaker.initialize_day(10000.0)

        valid, reason = circuit_breaker.validate_trade(
            account_balance=10000.0,
            risk_amount=150.0,  # 1.5% risk
            stop_loss_pips=20,
        )

        assert valid is True
        assert reason is None

    def test_validate_trade_exceeds_risk_limit(self, circuit_breaker):
        """Test trade validation fails when risk exceeds limit."""
        circuit_breaker.initialize_day(10000.0)

        valid, reason = circuit_breaker.validate_trade(
            account_balance=10000.0,
            risk_amount=300.0,  # 3% risk, exceeds 2% limit
            stop_loss_pips=20,
        )

        assert valid is False
        assert "risk" in reason.lower()

    def test_state_persistence(self):
        """Test state persistence to file."""
        from risk.circuit_breaker import CircuitBreaker

        with tempfile.TemporaryDirectory() as tmpdir:
            state_file = Path(tmpdir) / "cb_state.json"

            cb1 = CircuitBreaker(
                max_daily_loss_percent=5.0,
                max_trades_per_day=10,
                state_file=state_file,
            )
            cb1.initialize_day(10000.0)
            cb1.record_trade()
            cb1.record_trade()

            # Load state in new instance
            cb2 = CircuitBreaker(
                max_daily_loss_percent=5.0,
                max_trades_per_day=10,
                state_file=state_file,
            )

            assert cb2._trade_count == 2
            assert cb2._starting_balance == 10000.0


class TestPositionSizer:
    """Tests for PositionSizer class."""

    @pytest.fixture
    def sizer(self):
        """Create position sizer for testing."""
        from risk.position_sizer import PositionSizer

        return PositionSizer(
            default_risk_percent=1.0,
            min_lot_size=0.01,
            max_lot_size=10.0,
            lot_step=0.01,
            min_rr_ratio=1.5,
        )

    def test_calculate_fixed_fractional(self, sizer):
        """Test fixed fractional position sizing."""
        position = sizer.calculate_fixed_fractional(
            account_balance=10000.0,
            entry_price=1.0850,
            stop_loss=1.0820,  # 30 pips SL
            take_profit=1.0910,  # 60 pips TP
            symbol="EURUSD",
            risk_percent=1.0,
        )

        assert position.lot_size >= 0.01
        assert position.risk_percent <= 1.5  # May be slightly different due to rounding
        assert position.risk_reward_ratio >= 1.5
        assert position.stop_loss_pips == pytest.approx(30, rel=0.1)
        assert position.take_profit_pips == pytest.approx(60, rel=0.1)

    def test_calculate_fixed_lot(self, sizer):
        """Test fixed lot position sizing."""
        position = sizer.calculate_fixed_lot(
            lot_size=0.1,
            entry_price=1.0850,
            stop_loss=1.0820,
            take_profit=1.0910,
            symbol="EURUSD",
            account_balance=10000.0,
        )

        assert position.lot_size == 0.1
        assert position.risk_percent > 0

    def test_validate_position_good_rr(self, sizer):
        """Test position validation with good R:R."""
        from risk.position_sizer import PositionSize

        position = PositionSize(
            lot_size=0.1,
            risk_amount=100.0,
            risk_percent=1.0,
            stop_loss_pips=30,
            take_profit_pips=60,
            risk_reward_ratio=2.0,
            pip_value=10.0,
        )

        valid, reason = sizer.validate_position(position)

        assert valid is True
        assert reason is None

    def test_validate_position_bad_rr(self, sizer):
        """Test position validation with bad R:R."""
        from risk.position_sizer import PositionSize

        position = PositionSize(
            lot_size=0.1,
            risk_amount=100.0,
            risk_percent=1.0,
            stop_loss_pips=30,
            take_profit_pips=30,  # Only 1:1 R:R
            risk_reward_ratio=1.0,
            pip_value=10.0,
        )

        valid, reason = sizer.validate_position(position)

        assert valid is False
        assert "ratio" in reason.lower()

    def test_calculate_sl_tp_from_atr(self, sizer):
        """Test SL/TP calculation from ATR."""
        sl, tp = sizer.calculate_sl_tp_from_atr(
            entry_price=1.0850,
            atr=0.0020,  # 20 pips ATR
            order_type="BUY",
            sl_multiplier=1.5,
            tp_multiplier=2.5,
        )

        # SL should be below entry for BUY
        assert sl < 1.0850
        # TP should be above entry for BUY
        assert tp > 1.0850
        # SL distance should be 1.5 * ATR
        assert abs(1.0850 - sl) == pytest.approx(0.003, rel=0.01)
        # TP distance should be 2.5 * ATR
        assert abs(tp - 1.0850) == pytest.approx(0.005, rel=0.01)

    def test_lot_size_rounding(self, sizer):
        """Test lot size rounding to step."""
        # Test various values
        assert sizer._round_lot_size(0.0123) == 0.01
        assert sizer._round_lot_size(0.0156) == 0.02
        assert sizer._round_lot_size(0.005) == 0.01  # Min lot
        assert sizer._round_lot_size(15.0) == 10.0  # Max lot

    def test_jpy_pair_pip_size(self, sizer):
        """Test pip size for JPY pairs."""
        pip_size = sizer._get_pip_size("USDJPY")
        assert pip_size == 0.01

        pip_size = sizer._get_pip_size("EURUSD")
        assert pip_size == 0.0001
