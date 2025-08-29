"""
Tests for Risk Manager module.
"""

import pytest
from datetime import datetime, date
from modules.risk_manager import RiskManager, RiskLimitExceeded


class TestRiskManager:
    """Test cases for RiskManager."""
    
    def test_position_size_calculation_basic(self, risk_manager):
        """Test basic position size calculation."""
        account_equity = 100000.0
        entry_price = 15000.0
        stop_price = 14975.0  # 25 points risk
        
        position_size = risk_manager.calculate_position_size(
            account_equity, entry_price, stop_price
        )
        
        # Expected: $500 risk / (25 points * $5/point) = 4 contracts
        assert position_size == 4
    
    def test_position_size_calculation_small_equity(self):
        """Test position sizing with small equity."""
        risk_manager = RiskManager(default_risk_percent=0.005, point_value=5.0)
        
        account_equity = 5000.0  # Small account
        entry_price = 15000.0
        stop_price = 14970.0  # 30 points risk
        
        position_size = risk_manager.calculate_position_size(
            account_equity, entry_price, stop_price
        )
        
        # Expected: $25 risk / (30 points * $5/point) = 0.16 -> 1 contract minimum
        assert position_size == 1
    
    def test_position_size_calculation_large_equity(self):
        """Test position sizing with large equity."""
        risk_manager = RiskManager(default_risk_percent=0.005, point_value=5.0)
        
        account_equity = 1000000.0  # Large account
        entry_price = 15000.0
        stop_price = 14980.0  # 20 points risk
        
        position_size = risk_manager.calculate_position_size(
            account_equity, entry_price, stop_price
        )
        
        # Expected: $5000 risk / (20 points * $5/point) = 50 contracts
        assert position_size == 50
    
    def test_position_size_different_stop_distances(self, risk_manager):
        """Test position sizing with different stop distances."""
        account_equity = 100000.0
        entry_price = 15000.0
        
        # 20 point stop
        stop_price_20 = 14980.0
        size_20 = risk_manager.calculate_position_size(
            account_equity, entry_price, stop_price_20
        )
        
        # 30 point stop
        stop_price_30 = 14970.0
        size_30 = risk_manager.calculate_position_size(
            account_equity, entry_price, stop_price_30
        )
        
        # Smaller stop should allow larger position
        assert size_20 > size_30
        assert size_20 == 5  # $500 / (20 * $5) = 5
        assert size_30 == 3  # $500 / (30 * $5) = 3.33 -> 3
    
    def test_daily_loss_limit_enforcement(self, risk_manager):
        """Test daily loss limit enforcement."""
        account_equity = 100000.0
        max_daily_loss = account_equity * 0.02  # 2% = $2000
        
        # Test within limits
        assert risk_manager.check_daily_loss(account_equity, 1000.0) is True
        
        # Test at limit
        assert risk_manager.check_daily_loss(account_equity, max_daily_loss) is True
        
        # Test exceeding limit
        assert risk_manager.check_daily_loss(account_equity, max_daily_loss + 1) is False
    
    def test_daily_loss_with_existing_losses(self, risk_manager):
        """Test daily loss check with existing losses."""
        account_equity = 100000.0
        
        # Record a losing trade
        risk_manager.record_trade_result(-800.0, "MNQ", 4, 15000.0, 14800.0)
        
        # Check if we can take another trade with potential $1500 loss
        # Total would be $2300, exceeding $2000 limit
        assert risk_manager.check_daily_loss(account_equity, 1500.0) is False
        
        # Check with smaller potential loss
        assert risk_manager.check_daily_loss(account_equity, 1000.0) is True
    
    def test_trade_count_limit(self, risk_manager):
        """Test daily trade count limit."""
        # Initially should allow trades
        assert risk_manager.check_trade_count() is True
        
        # After first trade
        risk_manager.record_trade_result(500.0, "MNQ", 4, 15000.0, 15125.0)
        assert risk_manager.check_trade_count() is True
        assert risk_manager.trades_today == 1
        
        # After second trade
        risk_manager.record_trade_result(-300.0, "MNQ", 3, 15000.0, 14900.0)
        assert risk_manager.check_trade_count() is False
        assert risk_manager.trades_today == 2
    
    def test_can_trade_combined_limits(self, risk_manager):
        """Test can_trade with combined limits."""
        account_equity = 100000.0
        
        # Initially should allow trading
        assert risk_manager.can_trade(account_equity) is True
        
        # After one profitable trade
        risk_manager.record_trade_result(800.0, "MNQ", 4, 15000.0, 15200.0)
        assert risk_manager.can_trade(account_equity) is True
        
        # After second trade (hitting trade limit)
        risk_manager.record_trade_result(-500.0, "MNQ", 3, 15000.0, 14833.0)
        assert risk_manager.can_trade(account_equity) is False
    
    def test_can_trade_loss_limit_hit(self, risk_manager):
        """Test can_trade when loss limit is hit."""
        account_equity = 100000.0
        
        # Record large loss exceeding daily limit
        risk_manager.record_trade_result(-2100.0, "MNQ", 10, 15000.0, 14790.0)
        
        # Should not allow more trades
        assert risk_manager.can_trade(account_equity) is False
    
    def test_daily_reset(self, risk_manager):
        """Test daily reset functionality."""
        # Record trades
        risk_manager.record_trade_result(-1000.0, "MNQ", 4, 15000.0, 14750.0)
        risk_manager.record_trade_result(500.0, "MNQ", 3, 15000.0, 15167.0)
        
        assert risk_manager.trades_today == 2
        assert risk_manager.daily_pnl == -500.0
        
        # Reset daily limits
        risk_manager.reset_daily_limits()
        
        assert risk_manager.trades_today == 0
        assert risk_manager.daily_pnl == 0.0
        assert risk_manager.current_date == date.today()
    
    def test_invalid_position_size_calculation(self, risk_manager):
        """Test position size calculation with invalid inputs."""
        account_equity = 100000.0
        entry_price = 15000.0
        stop_price = 15000.0  # Same as entry price
        
        with pytest.raises(RiskLimitExceeded):
            risk_manager.calculate_position_size(account_equity, entry_price, stop_price)
    
    def test_get_daily_stats(self, risk_manager):
        """Test getting daily statistics."""
        # Record a trade
        risk_manager.record_trade_result(300.0, "MNQ", 2, 15000.0, 15150.0)
        
        stats = risk_manager.get_daily_stats()
        
        assert stats['daily_pnl'] == 300.0
        assert stats['trades_today'] == 1
        assert stats['max_trades_per_day'] == 2
        assert stats['max_daily_loss_percent'] == 0.02
        assert stats['can_trade_more'] is True
    
    def test_edge_case_zero_equity(self, risk_manager):
        """Test edge case with zero equity."""
        with pytest.raises(RiskLimitExceeded):
            risk_manager.calculate_position_size(0.0, 15000.0, 14975.0)
    
    def test_edge_case_negative_risk(self, risk_manager):
        """Test edge case with negative risk (stop above entry for long)."""
        account_equity = 100000.0
        entry_price = 15000.0
        stop_price = 15025.0  # Stop above entry for long position
        
        # Should still calculate position size using absolute difference
        position_size = risk_manager.calculate_position_size(
            account_equity, entry_price, stop_price
        )
        
        # Risk is 25 points, same calculation
        assert position_size == 4
