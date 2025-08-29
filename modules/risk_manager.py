"""
Risk Manager for NASDAQ Breakout Bot.
Handles position sizing and risk limit enforcement.
"""

import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, date
import json
import os


@dataclass
class TradeResult:
    """Trade result data."""
    timestamp: datetime
    pnl: float
    symbol: str
    quantity: int
    entry_price: float
    exit_price: float


class RiskLimitExceeded(Exception):
    """Exception raised when risk limits are exceeded."""
    pass


class RiskManager:
    """Manages position sizing and risk limits for trading."""
    
    def __init__(self, max_daily_loss_percent: float = 0.02, 
                 max_trades_per_day: int = 2,
                 default_risk_percent: float = 0.005,
                 point_value: float = 1.0):
        """
        Initialize risk manager.
        
        Args:
            max_daily_loss_percent: Maximum daily loss as percentage of equity (default 1%)
            max_trades_per_day: Maximum trades allowed per day
            default_risk_percent: Default risk per trade as percentage of equity (default 0.5%)
            point_value: Monetary value per point movement (default $1 for stocks/ETFs)
        """
        self.max_daily_loss_percent = max_daily_loss_percent
        self.max_trades_per_day = max_trades_per_day
        self.default_risk_percent = default_risk_percent
        self.point_value = point_value
        
        self.logger = logging.getLogger(__name__)
        
        # Daily tracking
        self.current_date = None
        self.daily_pnl = 0.0
        self.trades_today = 0
        self.trade_history = []
        
        # Load existing data if available
        self._load_daily_data()
        
        self.logger.info(f"Risk manager initialized - Max daily loss: {max_daily_loss_percent*100:.1f}%, "
                        f"Max trades: {max_trades_per_day}, Risk per trade: {default_risk_percent*100:.1f}%")
    
    def calculate_position_size(self, account_equity: float, entry_price: float, 
                              stop_price: float, risk_percent: Optional[float] = None) -> int:
        """
        Calculate position size based on risk parameters.
        
        Args:
            account_equity: Current account equity
            risk_percent: Risk percentage (defaults to default_risk_percent)
            entry_price: Entry price for the trade
            stop_price: Stop loss price
            
        Returns:
            Position size (number of shares/contracts)
        """
        try:
            if risk_percent is None:
                risk_percent = self.default_risk_percent
            
            # Calculate risk budget
            risk_budget = account_equity * risk_percent
            
            # Calculate risk per share/contract
            price_risk = abs(entry_price - stop_price)
            monetary_risk_per_unit = price_risk * self.point_value
            
            if monetary_risk_per_unit <= 0:
                raise ValueError("Invalid price risk - entry and stop prices are the same")
            
            # Calculate position size
            raw_position_size = risk_budget / monetary_risk_per_unit
            position_size = int(raw_position_size)  # Round down to not exceed risk
            
            # Ensure minimum position size of 1
            if position_size < 1:
                position_size = 1
                actual_risk = monetary_risk_per_unit
                actual_risk_percent = actual_risk / account_equity
                self.logger.warning(f"Minimum position size (1) results in {actual_risk_percent*100:.2f}% risk")
            
            actual_risk = position_size * monetary_risk_per_unit
            actual_risk_percent = actual_risk / account_equity
            
            self.logger.info(f"Position sizing: Equity=${account_equity:.2f}, "
                           f"Risk budget=${risk_budget:.2f} ({risk_percent*100:.1f}%), "
                           f"Price risk={price_risk:.2f} points, "
                           f"Position size={position_size}, "
                           f"Actual risk=${actual_risk:.2f} ({actual_risk_percent*100:.2f}%)")
            
            return position_size
            
        except Exception as e:
            self.logger.error(f"Error calculating position size: {e}")
            raise RiskLimitExceeded(f"Position size calculation failed: {e}")
    
    def check_daily_loss(self, account_equity: float, potential_loss: Optional[float] = None) -> bool:
        """
        Check if daily loss limits would be exceeded.
        
        Args:
            account_equity: Current account equity
            potential_loss: Additional potential loss to check (optional)
            
        Returns:
            True if within limits, False if limits would be exceeded
        """
        try:
            self._ensure_current_date()
            
            max_daily_loss = account_equity * self.max_daily_loss_percent
            current_loss = abs(min(0, self.daily_pnl))  # Only count losses
            
            total_potential_loss = current_loss
            if potential_loss is not None:
                total_potential_loss += abs(potential_loss)
            
            within_limits = total_potential_loss <= max_daily_loss
            
            self.logger.info(f"Daily loss check: Current loss=${current_loss:.2f}, "
                           f"Potential additional=${abs(potential_loss or 0):.2f}, "
                           f"Max allowed=${max_daily_loss:.2f}, "
                           f"Within limits: {within_limits}")
            
            if not within_limits:
                self.logger.warning(f"Daily loss limit would be exceeded: "
                                  f"${total_potential_loss:.2f} > ${max_daily_loss:.2f}")
            
            return within_limits
            
        except Exception as e:
            self.logger.error(f"Error checking daily loss: {e}")
            return False
    
    def check_trade_count(self) -> bool:
        """
        Check if daily trade count limit would be exceeded.
        
        Returns:
            True if within limits, False if limits would be exceeded
        """
        try:
            self._ensure_current_date()
            
            within_limits = self.trades_today < self.max_trades_per_day
            
            self.logger.info(f"Trade count check: {self.trades_today}/{self.max_trades_per_day}, "
                           f"Within limits: {within_limits}")
            
            if not within_limits:
                self.logger.warning(f"Daily trade limit reached: {self.trades_today}/{self.max_trades_per_day}")
            
            return within_limits
            
        except Exception as e:
            self.logger.error(f"Error checking trade count: {e}")
            return False
    
    def can_trade(self, account_equity: float, potential_loss: Optional[float] = None) -> bool:
        """
        Check if a new trade can be taken based on all risk limits.
        
        Args:
            account_equity: Current account equity
            potential_loss: Potential loss of the new trade
            
        Returns:
            True if trade is allowed, False otherwise
        """
        try:
            # Check trade count limit
            if not self.check_trade_count():
                return False
            
            # Check daily loss limit
            if not self.check_daily_loss(account_equity, potential_loss):
                return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error checking if can trade: {e}")
            return False
    
    def record_trade_result(self, pnl: float, symbol: str, quantity: int,
                          entry_price: float, exit_price: float) -> None:
        """
        Record the result of a completed trade.
        
        Args:
            pnl: Profit/loss of the trade
            symbol: Trading symbol
            quantity: Position size
            entry_price: Entry price
            exit_price: Exit price
        """
        try:
            self._ensure_current_date()
            
            # Create trade result
            trade_result = TradeResult(
                timestamp=datetime.now(),
                pnl=pnl,
                symbol=symbol,
                quantity=quantity,
                entry_price=entry_price,
                exit_price=exit_price
            )
            
            # Update daily tracking
            self.daily_pnl += pnl
            self.trades_today += 1
            self.trade_history.append(trade_result)
            
            # Save data
            self._save_daily_data()
            
            self.logger.info(f"Trade recorded: {symbol} {quantity}@${entry_price:.2f}->${exit_price:.2f}, "
                           f"P/L=${pnl:.2f}, Daily P/L=${self.daily_pnl:.2f}, "
                           f"Trades today: {self.trades_today}")
            
        except Exception as e:
            self.logger.error(f"Error recording trade result: {e}")
    
    def get_daily_stats(self) -> Dict[str, Any]:
        """
        Get current daily statistics.
        
        Returns:
            Dictionary with daily stats
        """
        self._ensure_current_date()
        
        return {
            'date': self.current_date.isoformat() if self.current_date else None,
            'daily_pnl': self.daily_pnl,
            'trades_today': self.trades_today,
            'max_trades_per_day': self.max_trades_per_day,
            'max_daily_loss_percent': self.max_daily_loss_percent,
            'can_trade_more': self.trades_today < self.max_trades_per_day
        }
    
    def reset_daily_limits(self) -> None:
        """Reset daily limits (called at start of new trading day)."""
        try:
            old_date = self.current_date
            self.current_date = date.today()
            self.daily_pnl = 0.0
            self.trades_today = 0
            
            # Keep only last 30 days of history
            from datetime import timedelta
            cutoff_date = datetime.now() - timedelta(days=30)
            self.trade_history = [
                trade for trade in self.trade_history 
                if trade.timestamp > cutoff_date
            ]
            
            self._save_daily_data()
            
            self.logger.info(f"Daily limits reset: {old_date} -> {self.current_date}")
            
        except Exception as e:
            self.logger.error(f"Error resetting daily limits: {e}")
    
    def _ensure_current_date(self) -> None:
        """Ensure we're tracking the current date."""
        today = date.today()
        if self.current_date != today:
            if self.current_date is not None:
                self.logger.info(f"New trading day detected: {self.current_date} -> {today}")
            self.reset_daily_limits()
    
    def _get_data_file_path(self) -> str:
        """Get path for daily data file."""
        data_dir = "data"
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        return os.path.join(data_dir, "risk_manager_data.json")
    
    def _save_daily_data(self) -> None:
        """Save daily data to file."""
        try:
            data = {
                'current_date': self.current_date.isoformat() if self.current_date else None,
                'daily_pnl': self.daily_pnl,
                'trades_today': self.trades_today,
                'trade_history': [
                    {
                        'timestamp': trade.timestamp.isoformat(),
                        'pnl': trade.pnl,
                        'symbol': trade.symbol,
                        'quantity': trade.quantity,
                        'entry_price': trade.entry_price,
                        'exit_price': trade.exit_price
                    }
                    for trade in self.trade_history
                ]
            }
            
            with open(self._get_data_file_path(), 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            self.logger.error(f"Error saving daily data: {e}")
    
    def _load_daily_data(self) -> None:
        """Load daily data from file."""
        try:
            file_path = self._get_data_file_path()
            if not os.path.exists(file_path):
                return
            
            with open(file_path, 'r') as f:
                data = json.load(f)
            
            if data.get('current_date'):
                saved_date = date.fromisoformat(data['current_date'])
                if saved_date == date.today():
                    self.current_date = saved_date
                    self.daily_pnl = data.get('daily_pnl', 0.0)
                    self.trades_today = data.get('trades_today', 0)
                    
                    # Load trade history
                    self.trade_history = []
                    for trade_data in data.get('trade_history', []):
                        trade = TradeResult(
                            timestamp=datetime.fromisoformat(trade_data['timestamp']),
                            pnl=trade_data['pnl'],
                            symbol=trade_data['symbol'],
                            quantity=trade_data['quantity'],
                            entry_price=trade_data['entry_price'],
                            exit_price=trade_data['exit_price']
                        )
                        self.trade_history.append(trade)
                    
                    self.logger.info(f"Loaded daily data: P/L=${self.daily_pnl:.2f}, "
                                   f"Trades={self.trades_today}")
                
        except Exception as e:
            self.logger.error(f"Error loading daily data: {e}")
