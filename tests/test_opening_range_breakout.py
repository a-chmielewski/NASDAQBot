"""
Tests for Opening Range Breakout strategy module.
"""

import pytest
from datetime import datetime
from modules.opening_range_breakout import OpeningRangeBreakout, StrategyConfig, BreakoutLevels


class TestOpeningRangeBreakout:
    """Test cases for OpeningRangeBreakout strategy."""
    
    def test_strategy_initialization(self):
        """Test strategy initialization with default config."""
        strategy = OpeningRangeBreakout()
        
        assert strategy.config.breakout_offset_points == 15.0
        assert strategy.config.stop_loss_points == 25.0
        assert strategy.config.risk_reward_ratio == 2.0
    
    def test_strategy_initialization_custom_config(self):
        """Test strategy initialization with custom config."""
        config = StrategyConfig(
            breakout_offset_points=20.0,
            stop_loss_points=30.0,
            risk_reward_ratio=1.5
        )
        strategy = OpeningRangeBreakout(config)
        
        assert strategy.config.breakout_offset_points == 20.0
        assert strategy.config.stop_loss_points == 30.0
        assert strategy.config.risk_reward_ratio == 1.5
    
    def test_calculate_breakout_levels_basic(self, strategy):
        """Test basic breakout level calculation."""
        opening_high = 15020.0
        opening_low = 14980.0
        
        levels = strategy.calculate_breakout_levels(opening_high, opening_low)
        
        assert levels.opening_high == 15020.0
        assert levels.opening_low == 14980.0
        assert levels.range_size == 40.0
        assert levels.long_entry == 15035.0  # 15020 + 15
        assert levels.short_entry == 14965.0  # 14980 - 15
        assert levels.long_stop_loss == 15010.0  # 15035 - 25
        assert levels.short_stop_loss == 14990.0  # 14965 + 25
        assert levels.long_take_profit == 15085.0  # 15035 + 50 (2 * 25)
        assert levels.short_take_profit == 14915.0  # 14965 - 50 (2 * 25)
    
    def test_calculate_breakout_levels_dynamic_stops(self):
        """Test breakout levels with dynamic stops enabled."""
        config = StrategyConfig(
            breakout_offset_points=15.0,
            use_dynamic_stops=True,
            dynamic_stop_multiplier=1.5
        )
        strategy = OpeningRangeBreakout(config)
        
        opening_high = 15030.0
        opening_low = 14970.0  # 60 point range
        
        levels = strategy.calculate_breakout_levels(opening_high, opening_low)
        
        # Dynamic stop = 60 * 1.5 = 90, but capped between 15-50, so should be 50
        expected_stop_distance = 50.0
        
        assert levels.long_entry == 15045.0  # 15030 + 15
        assert levels.short_entry == 14955.0  # 14970 - 15
        assert levels.long_stop_loss == 14995.0  # 15045 - 50
        assert levels.short_stop_loss == 15005.0  # 14955 + 50
    
    def test_should_take_trade_valid_range(self, strategy):
        """Test trade validation with valid range."""
        levels = BreakoutLevels(
            opening_high=15020.0,
            opening_low=14980.0,
            range_size=40.0,
            long_entry=15035.0,
            short_entry=14965.0,
            long_stop_loss=15010.0,
            short_stop_loss=14990.0,
            long_take_profit=15085.0,
            short_take_profit=14915.0
        )
        
        assert strategy.should_take_trade(levels) is True
    
    def test_should_take_trade_invalid_range_too_small(self, strategy):
        """Test trade validation with range too small."""
        levels = BreakoutLevels(
            opening_high=15005.0,
            opening_low=15000.0,
            range_size=5.0,  # Below minimum
            long_entry=15020.0,
            short_entry=14985.0,
            long_stop_loss=14995.0,
            short_stop_loss=15010.0,
            long_take_profit=15070.0,
            short_take_profit=14935.0
        )
        
        assert strategy.should_take_trade(levels) is False
    
    def test_should_take_trade_invalid_range_too_large(self, strategy):
        """Test trade validation with range too large."""
        levels = BreakoutLevels(
            opening_high=15100.0,
            opening_low=14900.0,
            range_size=200.0,  # Above maximum
            long_entry=15115.0,
            short_entry=14885.0,
            long_stop_loss=15090.0,
            short_stop_loss=14910.0,
            long_take_profit=15165.0,
            short_take_profit=14835.0
        )
        
        assert strategy.should_take_trade(levels) is False
    
    def test_should_take_trade_invalid_time(self, strategy):
        """Test trade validation with invalid time."""
        levels = BreakoutLevels(
            opening_high=15020.0,
            opening_low=14980.0,
            range_size=40.0,
            long_entry=15035.0,
            short_entry=14965.0,
            long_stop_loss=15010.0,
            short_stop_loss=14990.0,
            long_take_profit=15085.0,
            short_take_profit=14915.0
        )
        
        # Test with time outside trading hours (5 PM ET)
        invalid_time = datetime(2024, 1, 15, 17, 0)
        
        assert strategy.should_take_trade(levels, invalid_time) is False
    
    def test_get_stop_loss_points_fixed(self, strategy):
        """Test getting stop loss points with fixed stops."""
        stop_points = strategy.get_stop_loss_points()
        assert stop_points == 25.0
    
    def test_get_stop_loss_points_dynamic(self):
        """Test getting stop loss points with dynamic stops."""
        config = StrategyConfig(
            use_dynamic_stops=True,
            dynamic_stop_multiplier=1.5
        )
        strategy = OpeningRangeBreakout(config)
        
        # Test with 40 point range
        stop_points = strategy.get_stop_loss_points(40.0)
        expected = min(max(40.0 * 1.5, 15.0), 50.0)  # Should be 50.0 (capped)
        assert stop_points == expected
    
    def test_get_take_profit_points(self, strategy):
        """Test getting take profit points."""
        stop_loss_points = 25.0
        tp_points = strategy.get_take_profit_points(stop_loss_points)
        
        expected = 25.0 * 2.0  # 2:1 risk reward
        assert tp_points == expected
    
    def test_update_config(self, strategy):
        """Test updating strategy configuration."""
        strategy.update_config(
            breakout_offset_points=20.0,
            stop_loss_points=30.0
        )
        
        assert strategy.config.breakout_offset_points == 20.0
        assert strategy.config.stop_loss_points == 30.0
        assert strategy.config.risk_reward_ratio == 2.0  # Unchanged
    
    def test_update_config_invalid_parameter(self, strategy):
        """Test updating config with invalid parameter."""
        original_offset = strategy.config.breakout_offset_points
        
        strategy.update_config(invalid_param=100.0)
        
        # Should remain unchanged
        assert strategy.config.breakout_offset_points == original_offset
    
    def test_prepare_day(self, strategy):
        """Test day preparation."""
        prep_info = strategy.prepare_day()
        
        assert prep_info['ready'] is True
        assert prep_info['strategy'] == 'opening_range_breakout'
        assert 'config' in prep_info
        assert 'timestamp' in prep_info
    
    def test_get_strategy_stats(self, strategy):
        """Test getting strategy statistics."""
        stats = strategy.get_strategy_stats()
        
        assert stats['strategy_name'] == 'Opening Range Breakout'
        assert 'config' in stats
        assert 'description' in stats
        assert stats['config']['breakout_offset_points'] == 15.0
    
    def test_valid_range_edge_cases(self, strategy):
        """Test range validation edge cases."""
        # Exactly at minimum
        assert strategy._is_valid_range(5.0) is False
        
        # Exactly at maximum
        assert strategy._is_valid_range(100.0) is True
        
        # Just below minimum
        assert strategy._is_valid_range(4.99) is False
        
        # Just above maximum
        assert strategy._is_valid_range(100.01) is False
    
    def test_valid_trade_time_edge_cases(self, strategy):
        """Test trade time validation edge cases."""
        # Exactly at market open
        market_open = datetime(2024, 1, 15, 9, 30)
        assert strategy._is_valid_trade_time(market_open) is True
        
        # Exactly at cutoff time (3:30 PM)
        cutoff_time = datetime(2024, 1, 15, 15, 30)
        assert strategy._is_valid_trade_time(cutoff_time) is True
        
        # Just before market open
        before_open = datetime(2024, 1, 15, 9, 29)
        assert strategy._is_valid_trade_time(before_open) is False
        
        # Just after cutoff
        after_cutoff = datetime(2024, 1, 15, 15, 31)
        assert strategy._is_valid_trade_time(after_cutoff) is False
    
    def test_calculate_stop_distance_bounds(self):
        """Test stop distance calculation bounds."""
        config = StrategyConfig(
            use_dynamic_stops=True,
            dynamic_stop_multiplier=2.0
        )
        strategy = OpeningRangeBreakout(config)
        
        # Test minimum bound
        small_range = 5.0
        stop_distance = strategy._calculate_stop_distance(small_range)
        assert stop_distance == 15.0  # Should be clamped to minimum
        
        # Test maximum bound
        large_range = 50.0
        stop_distance = strategy._calculate_stop_distance(large_range)
        assert stop_distance == 50.0  # Should be clamped to maximum
    
    def test_invalid_range_calculation(self, strategy):
        """Test breakout calculation with invalid range."""
        with pytest.raises(ValueError, match="Invalid range size"):
            strategy.calculate_breakout_levels(15000.0, 15200.0)  # Range too large
