"""
Order Manager for NASDAQ Breakout Bot.
Handles order placement and monitoring for breakout strategy.
"""

import logging
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import threading

from .alpaca_api import AlpacaAPI, OrderParams, AlpacaAPIError
from .risk_manager import RiskManager, RiskLimitExceeded


@dataclass
class BreakoutOrders:
    """Container for breakout order information."""
    long_order_id: Optional[str] = None
    short_order_id: Optional[str] = None
    symbol: str = ""
    long_entry: float = 0.0
    short_entry: float = 0.0
    stop_loss_points: float = 0.0
    take_profit_points: float = 0.0
    position_size: int = 0


@dataclass
class TradeExecution:
    """Trade execution information."""
    order_id: str
    symbol: str
    side: str
    quantity: int
    entry_price: float
    timestamp: datetime
    stop_loss: float
    take_profit: float


class OrderManagerError(Exception):
    """Custom exception for order manager errors."""
    pass


class OrderManager:
    """Manages order placement and monitoring for breakout strategy."""
    
    def __init__(self, alpaca_api: AlpacaAPI, risk_manager: RiskManager):
        """
        Initialize order manager.
        
        Args:
            alpaca_api: Alpaca API connector
            risk_manager: Risk manager instance
        """
        self.api = alpaca_api
        self.risk_manager = risk_manager
        self.logger = logging.getLogger(__name__)
        
        # Active orders tracking
        self.active_breakout_orders: Dict[str, BreakoutOrders] = {}
        self.executed_trades: List[TradeExecution] = []
        self.monitoring_active = False
        self.monitor_thread = None
        
        self.logger.info("Order manager initialized")
    
    def place_breakout_orders(self, symbol: str, long_entry: float, short_entry: float,
                            stop_loss_points: float, take_profit_points: float,
                            account_equity: float) -> BreakoutOrders:
        """
        Place breakout orders (long and short) with bracket orders.
        
        Args:
            symbol: Trading symbol
            long_entry: Long breakout entry price
            short_entry: Short breakout entry price
            stop_loss_points: Stop loss distance in points
            take_profit_points: Take profit distance in points
            account_equity: Current account equity
            
        Returns:
            BreakoutOrders containing order IDs and details
        """
        try:
            # Check if we can trade
            if not self.risk_manager.can_trade(account_equity):
                raise OrderManagerError("Risk limits prevent new trades")
            
            # Calculate position size for long trade
            long_stop_price = long_entry - stop_loss_points
            position_size = self.risk_manager.calculate_position_size(
                account_equity, long_entry, long_stop_price
            )
            
            # Verify position size is reasonable
            if position_size <= 0:
                raise OrderManagerError("Invalid position size calculated")
            
            # Calculate stop loss and take profit prices
            long_stop_loss = long_entry - stop_loss_points
            long_take_profit = long_entry + take_profit_points
            short_stop_loss = short_entry + stop_loss_points
            short_take_profit = short_entry - take_profit_points
            
            self.logger.info(f"Placing breakout orders for {symbol}: "
                           f"Long@${long_entry:.2f} SL@${long_stop_loss:.2f} TP@${long_take_profit:.2f}, "
                           f"Short@${short_entry:.2f} SL@${short_stop_loss:.2f} TP@${short_take_profit:.2f}, "
                           f"Size={position_size}")
            
            # Place long breakout order (buy stop with bracket)
            long_order_params = OrderParams(
                symbol=symbol,
                qty=position_size,
                side='buy',
                type='stop',
                stop_price=long_entry,
                take_profit=long_take_profit,
                stop_loss=long_stop_loss,
                time_in_force='day'
            )
            
            # Place short breakout order (sell stop with bracket)  
            short_order_params = OrderParams(
                symbol=symbol,
                qty=position_size,
                side='sell',
                type='stop',
                stop_price=short_entry,
                take_profit=short_take_profit,
                stop_loss=short_stop_loss,
                time_in_force='day'
            )
            
            # Submit orders
            long_order = self.api.submit_order(long_order_params)
            short_order = self.api.submit_order(short_order_params)
            
            # Create breakout orders container
            breakout_orders = BreakoutOrders(
                long_order_id=long_order['id'],
                short_order_id=short_order['id'],
                symbol=symbol,
                long_entry=long_entry,
                short_entry=short_entry,
                stop_loss_points=stop_loss_points,
                take_profit_points=take_profit_points,
                position_size=position_size
            )
            
            # Track active orders
            self.active_breakout_orders[symbol] = breakout_orders
            
            # Start monitoring if not already active
            if not self.monitoring_active:
                self.start_monitoring()
            
            self.logger.info(f"Breakout orders placed successfully for {symbol}: "
                           f"Long ID={long_order['id']}, Short ID={short_order['id']}")
            
            return breakout_orders
            
        except (AlpacaAPIError, RiskLimitExceeded) as e:
            self.logger.error(f"Error placing breakout orders: {e}")
            raise OrderManagerError(f"Failed to place breakout orders: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error placing breakout orders: {e}")
            raise OrderManagerError(f"Unexpected error: {e}")
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel a specific order.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if successful
        """
        try:
            success = self.api.cancel_order(order_id)
            if success:
                self.logger.info(f"Order cancelled: {order_id}")
            return success
            
        except AlpacaAPIError as e:
            self.logger.warning(f"Error cancelling order {order_id}: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error cancelling order {order_id}: {e}")
            return False
    
    def cancel_all_pending(self, symbol: Optional[str] = None) -> bool:
        """
        Cancel all pending orders for a symbol or all symbols.
        
        Args:
            symbol: Symbol to cancel orders for (None for all)
            
        Returns:
            True if successful
        """
        try:
            if symbol:
                # Cancel specific symbol's orders
                if symbol in self.active_breakout_orders:
                    orders = self.active_breakout_orders[symbol]
                    if orders.long_order_id:
                        self.cancel_order(orders.long_order_id)
                    if orders.short_order_id:
                        self.cancel_order(orders.short_order_id)
                    del self.active_breakout_orders[symbol]
            else:
                # Cancel all orders
                success = self.api.cancel_all_orders()
                self.active_breakout_orders.clear()
                self.logger.info("All pending orders cancelled")
                return success
            
            return True
            
        except AlpacaAPIError as e:
            self.logger.error(f"Error cancelling pending orders: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error cancelling pending orders: {e}")
            return False
    
    def start_monitoring(self) -> None:
        """Start monitoring orders for fills."""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self._monitor_orders, daemon=True)
        self.monitor_thread.start()
        self.logger.info("Order monitoring started")
    
    def stop_monitoring(self) -> None:
        """Stop monitoring orders."""
        self.monitoring_active = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=5)
        self.logger.info("Order monitoring stopped")
    
    def _monitor_orders(self) -> None:
        """Monitor orders for fills (runs in separate thread)."""
        while self.monitoring_active:
            try:
                symbols_to_remove = []
                
                for symbol, orders in self.active_breakout_orders.items():
                    # Check long order status
                    if orders.long_order_id:
                        long_status = self._check_order_status(orders.long_order_id)
                        if long_status == 'filled':
                            self._handle_order_fill(orders, 'long')
                            symbols_to_remove.append(symbol)
                            continue
                    
                    # Check short order status
                    if orders.short_order_id:
                        short_status = self._check_order_status(orders.short_order_id)
                        if short_status == 'filled':
                            self._handle_order_fill(orders, 'short')
                            symbols_to_remove.append(symbol)
                            continue
                
                # Remove filled orders from tracking
                for symbol in symbols_to_remove:
                    if symbol in self.active_breakout_orders:
                        del self.active_breakout_orders[symbol]
                
                # Stop monitoring if no active orders
                if not self.active_breakout_orders:
                    self.monitoring_active = False
                    break
                
                # Wait before next check
                time.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                self.logger.error(f"Error in order monitoring: {e}")
                time.sleep(30)  # Wait longer on error
    
    def _check_order_status(self, order_id: str) -> str:
        """Check the status of an order."""
        try:
            order_status = self.api.get_order_status(order_id)
            return order_status['status']
        except Exception as e:
            self.logger.warning(f"Error checking order status {order_id}: {e}")
            return 'unknown'
    
    def _handle_order_fill(self, orders: BreakoutOrders, side: str) -> None:
        """Handle when a breakout order is filled."""
        try:
            filled_order_id = orders.long_order_id if side == 'long' else orders.short_order_id
            opposite_order_id = orders.short_order_id if side == 'long' else orders.long_order_id
            
            # Get filled order details
            order_status = self.api.get_order_status(filled_order_id)
            entry_price = order_status['filled_avg_price']
            
            # Cancel opposite order
            if opposite_order_id:
                self.cancel_order(opposite_order_id)
                self.logger.info(f"Cancelled opposite {orders.symbol} order: {opposite_order_id}")
            
            # Calculate stop loss and take profit
            if side == 'long':
                stop_loss = entry_price - orders.stop_loss_points
                take_profit = entry_price + orders.take_profit_points
            else:
                stop_loss = entry_price + orders.stop_loss_points
                take_profit = entry_price - orders.take_profit_points
            
            # Create trade execution record
            trade_execution = TradeExecution(
                order_id=filled_order_id,
                symbol=orders.symbol,
                side=side,
                quantity=orders.position_size,
                entry_price=entry_price,
                timestamp=datetime.now(),
                stop_loss=stop_loss,
                take_profit=take_profit
            )
            
            self.executed_trades.append(trade_execution)
            
            self.logger.info(f"Breakout order filled: {side.upper()} {orders.symbol} "
                           f"{orders.position_size}@${entry_price:.2f}, "
                           f"SL@${stop_loss:.2f}, TP@${take_profit:.2f}")
            
        except Exception as e:
            self.logger.error(f"Error handling order fill: {e}")
    
    def get_active_orders(self) -> Dict[str, BreakoutOrders]:
        """Get currently active breakout orders."""
        return self.active_breakout_orders.copy()
    
    def get_executed_trades(self) -> List[TradeExecution]:
        """Get list of executed trades."""
        return self.executed_trades.copy()
    
    def has_active_orders(self, symbol: Optional[str] = None) -> bool:
        """
        Check if there are active orders.
        
        Args:
            symbol: Check for specific symbol (None for any)
            
        Returns:
            True if there are active orders
        """
        if symbol:
            return symbol in self.active_breakout_orders
        return len(self.active_breakout_orders) > 0
    
    def cleanup(self) -> None:
        """Cleanup resources and cancel all orders."""
        try:
            self.stop_monitoring()
            self.cancel_all_pending()
            self.logger.info("Order manager cleanup completed")
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    def on_trade_exit(self, symbol: str, exit_price: float, pnl: float) -> None:
        """
        Handle trade exit (called when position closes).
        
        Args:
            symbol: Trading symbol
            exit_price: Exit price
            pnl: Profit/loss of the trade
        """
        try:
            # Find the corresponding executed trade
            for trade in self.executed_trades:
                if trade.symbol == symbol:
                    # Record trade result with risk manager
                    self.risk_manager.record_trade_result(
                        pnl=pnl,
                        symbol=symbol,
                        quantity=trade.quantity,
                        entry_price=trade.entry_price,
                        exit_price=exit_price
                    )
                    
                    self.logger.info(f"Trade exit recorded: {symbol} P/L=${pnl:.2f}")
                    break
            
        except Exception as e:
            self.logger.error(f"Error handling trade exit: {e}")
    
    def get_daily_trade_count(self) -> int:
        """Get number of trades executed today."""
        return self.risk_manager.trades_today
