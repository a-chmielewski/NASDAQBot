"""
Opening Range Breakout Strategy for NASDAQ Breakout Bot.
Contains strategy-specific parameters and logic.
"""

import logging
from typing import Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class StrategyConfig:
    """Configuration parameters for the opening range breakout strategy."""
    breakout_offset_points: float = 15.0  # Points beyond range for entry trigger
    stop_loss_points: float = 25.0        # Stop loss distance from entry
    risk_reward_ratio: float = 2.0        # Take profit multiplier (2R = 2x stop distance)
    min_range_size: float = 5.0           # Minimum opening range size in points
    max_range_size: float = 100.0         # Maximum opening range size in points
    use_dynamic_stops: bool = False       # Use range-based stop sizing
    dynamic_stop_multiplier: float = 1.5  # Multiplier for range-based stops


@dataclass
class BreakoutLevels:
    """Breakout entry and exit levels."""
    opening_high: float
    opening_low: float
    range_size: float
    long_entry: float
    short_entry: float
    long_stop_loss: float
    short_stop_loss: float
    long_take_profit: float
    short_take_profit: float
    position_size: int = 0


class OpeningRangeBreakout:
    """Opening range breakout strategy implementation."""
    
    def __init__(self, config: Optional[StrategyConfig] = None):
        """
        Initialize strategy with configuration.
        
        Args:
            config: Strategy configuration (uses defaults if None)
        """
        self.config = config or StrategyConfig()
        self.logger = logging.getLogger(__name__)
        
        self.logger.info(f"Opening range breakout strategy initialized: "
                        f"Offset={self.config.breakout_offset_points}pts, "
                        f"Stop={self.config.stop_loss_points}pts, "
                        f"R:R={self.config.risk_reward_ratio}:1")
    
    def calculate_breakout_levels(self, opening_high: float, opening_low: float) -> BreakoutLevels:
        """
        Calculate breakout entry and exit levels from opening range.
        
        Args:
            opening_high: High of the opening range
            opening_low: Low of the opening range
            
        Returns:
            BreakoutLevels with all calculated prices
        """
        try:
            range_size = opening_high - opening_low
            
            # Validate range size
            if not self._is_valid_range(range_size):
                raise ValueError(f"Invalid range size: {range_size:.2f} points")
            
            # Calculate entry levels
            long_entry = opening_high + self.config.breakout_offset_points
            short_entry = opening_low - self.config.breakout_offset_points
            
            # Calculate stop loss distance
            stop_distance = self._calculate_stop_distance(range_size)
            
            # Calculate stop loss levels
            long_stop_loss = long_entry - stop_distance
            short_stop_loss = short_entry + stop_distance
            
            # Calculate take profit levels
            take_profit_distance = stop_distance * self.config.risk_reward_ratio
            long_take_profit = long_entry + take_profit_distance
            short_take_profit = short_entry - take_profit_distance
            
            breakout_levels = BreakoutLevels(
                opening_high=opening_high,
                opening_low=opening_low,
                range_size=range_size,
                long_entry=long_entry,
                short_entry=short_entry,
                long_stop_loss=long_stop_loss,
                short_stop_loss=short_stop_loss,
                long_take_profit=long_take_profit,
                short_take_profit=short_take_profit
            )
            
            self.logger.info(f"Breakout levels calculated: Range={range_size:.2f}pts, "
                           f"Long={long_entry:.2f}(SL:{long_stop_loss:.2f}/TP:{long_take_profit:.2f}), "
                           f"Short={short_entry:.2f}(SL:{short_stop_loss:.2f}/TP:{short_take_profit:.2f})")
            
            return breakout_levels
            
        except Exception as e:
            self.logger.error(f"Error calculating breakout levels: {e}")
            raise
    
    def should_take_trade(self, breakout_levels: BreakoutLevels, current_time: datetime = None) -> bool:
        """
        Determine if a breakout trade should be taken based on strategy rules.
        
        Args:
            breakout_levels: Calculated breakout levels
            current_time: Current time (for time-based filters)
            
        Returns:
            True if trade should be taken
        """
        try:
            # Check range size validity
            if not self._is_valid_range(breakout_levels.range_size):
                self.logger.warning(f"Range size invalid: {breakout_levels.range_size:.2f} points")
                return False
            
            # Time-based filter (optional - trade only within certain hours)
            if current_time and not self._is_valid_trade_time(current_time):
                self.logger.info("Outside valid trading hours")
                return False
            
            # Additional filters can be added here
            # - Volatility filters
            # - Market condition filters
            # - Gap filters
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking trade validity: {e}")
            return False
    
    def prepare_day(self) -> Dict[str, Any]:
        """
        Prepare strategy for the trading day.
        
        Returns:
            Dictionary with day preparation results
        """
        try:
            preparation_info = {
                'strategy': 'opening_range_breakout',
                'config': {
                    'breakout_offset': self.config.breakout_offset_points,
                    'stop_loss_points': self.config.stop_loss_points,
                    'risk_reward_ratio': self.config.risk_reward_ratio,
                    'use_dynamic_stops': self.config.use_dynamic_stops
                },
                'timestamp': datetime.now().isoformat(),
                'ready': True
            }
            
            self.logger.info("Strategy prepared for trading day")
            return preparation_info
            
        except Exception as e:
            self.logger.error(f"Error preparing strategy for day: {e}")
            return {'ready': False, 'error': str(e)}
    
    def get_stop_loss_points(self, range_size: Optional[float] = None) -> float:
        """
        Get stop loss distance in points.
        
        Args:
            range_size: Opening range size for dynamic calculation
            
        Returns:
            Stop loss distance in points
        """
        return self._calculate_stop_distance(range_size)
    
    def get_take_profit_points(self, stop_loss_points: float) -> float:
        """
        Get take profit distance in points.
        
        Args:
            stop_loss_points: Stop loss distance
            
        Returns:
            Take profit distance in points
        """
        return stop_loss_points * self.config.risk_reward_ratio
    
    def update_config(self, **kwargs) -> None:
        """
        Update strategy configuration parameters.
        
        Args:
            **kwargs: Configuration parameters to update
        """
        try:
            for key, value in kwargs.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)
                    self.logger.info(f"Updated config: {key}={value}")
                else:
                    self.logger.warning(f"Unknown config parameter: {key}")
                    
        except Exception as e:
            self.logger.error(f"Error updating config: {e}")
    
    def _calculate_stop_distance(self, range_size: Optional[float] = None) -> float:
        """Calculate stop loss distance based on configuration."""
        if self.config.use_dynamic_stops and range_size is not None:
            # Use range-based dynamic stops
            dynamic_stop = range_size * self.config.dynamic_stop_multiplier
            # Ensure it's within reasonable bounds
            return max(min(dynamic_stop, 50.0), 15.0)
        else:
            # Use fixed stop distance
            return self.config.stop_loss_points
    
    def _is_valid_range(self, range_size: float) -> bool:
        """Check if opening range size is valid for trading."""
        return self.config.min_range_size < range_size <= self.config.max_range_size
    
    def _is_valid_trade_time(self, current_time: datetime) -> bool:
        """Check if current time is valid for trading."""
        # For now, allow trading throughout market hours
        # Could add filters like:
        # - No trades in last hour of market
        # - No trades during lunch hour
        # - etc.
        
        # Basic check: ensure it's during market hours (9:30 AM - 4:00 PM ET)
        market_time = current_time.time()
        market_start = datetime.strptime("09:30", "%H:%M").time()
        market_end = datetime.strptime("15:30", "%H:%M").time()  # Stop 30 min before close
        
        return market_start <= market_time <= market_end
    
    def get_strategy_stats(self) -> Dict[str, Any]:
        """
        Get current strategy statistics and configuration.
        
        Returns:
            Dictionary with strategy information
        """
        return {
            'strategy_name': 'Opening Range Breakout',
            'config': {
                'breakout_offset_points': self.config.breakout_offset_points,
                'stop_loss_points': self.config.stop_loss_points,
                'risk_reward_ratio': self.config.risk_reward_ratio,
                'min_range_size': self.config.min_range_size,
                'max_range_size': self.config.max_range_size,
                'use_dynamic_stops': self.config.use_dynamic_stops,
                'dynamic_stop_multiplier': self.config.dynamic_stop_multiplier
            },
            'description': f"15-minute opening range breakout with {self.config.breakout_offset_points}pt offset, "
                          f"{self.config.stop_loss_points}pt stops, {self.config.risk_reward_ratio}:1 R/R"
        }
