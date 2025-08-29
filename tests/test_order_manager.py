"""
Tests for Order Manager module.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime
from modules.order_manager import OrderManager, OrderManagerError, BreakoutOrders, TradeExecution


class TestOrderManager:
    """Test cases for OrderManager."""
    
    @pytest.fixture
    def order_manager(self, mock_alpaca_api, risk_manager):
        """Create order manager for testing."""
        return OrderManager(mock_alpaca_api, risk_manager)
    
    def test_initialization(self, order_manager):
        """Test order manager initialization."""
        assert order_manager.api is not None
        assert order_manager.risk_manager is not None
        assert len(order_manager.active_breakout_orders) == 0
        assert len(order_manager.executed_trades) == 0
        assert order_manager.monitoring_active is False
    
    def test_place_breakout_orders_success(self, order_manager):
        """Test successful breakout order placement."""
        symbol = "MNQ"
        long_entry = 15035.0
        short_entry = 14965.0
        stop_loss_points = 25.0
        take_profit_points = 50.0
        account_equity = 100000.0

        # Mock successful order submissions
        order_manager.api.submit_order.side_effect = [
            {'id': 'long_order_123', 'symbol': 'MNQ', 'side': 'buy'},
            {'id': 'short_order_456', 'symbol': 'MNQ', 'side': 'sell'}
        ]

        # Mock risk manager methods to ensure they work
        with patch.object(order_manager.risk_manager, 'can_trade', return_value=True):
            with patch.object(order_manager.risk_manager, 'calculate_position_size', return_value=4):
                with patch.object(order_manager, 'start_monitoring') as mock_start:
                    breakout_orders = order_manager.place_breakout_orders(
                        symbol, long_entry, short_entry, stop_loss_points,
                        take_profit_points, account_equity
                    )

                    assert breakout_orders.long_order_id == 'long_order_123'
                    assert breakout_orders.short_order_id == 'short_order_456'
                    assert breakout_orders.symbol == symbol
                    assert breakout_orders.long_entry == long_entry
                    assert breakout_orders.short_entry == short_entry
                    # Verify breakout orders were tracked
                    assert len(order_manager.active_breakout_orders) == 1
                    assert symbol in order_manager.active_breakout_orders
                    mock_start.assert_called_once()
    
    def test_place_breakout_orders_risk_limits_exceeded(self, order_manager):
        """Test order placement when risk limits are exceeded."""
        # Mock can_trade to return False
        with patch.object(order_manager.risk_manager, 'can_trade', return_value=False):
            with pytest.raises(OrderManagerError, match="Risk limits prevent new trades"):
                order_manager.place_breakout_orders(
                    "MNQ", 15035.0, 14965.0, 25.0, 50.0, 100000.0
                )
    
    def test_place_breakout_orders_invalid_position_size(self, order_manager):
        """Test order placement with invalid position size."""
        # Mock calculate_position_size to return 0
        with patch.object(order_manager.risk_manager, 'calculate_position_size', return_value=0):
            with pytest.raises(OrderManagerError, match="Invalid position size calculated"):
                order_manager.place_breakout_orders(
                    "MNQ", 15035.0, 14965.0, 25.0, 50.0, 100000.0
                )
    
    def test_cancel_order_success(self, order_manager):
        """Test successful order cancellation."""
        order_manager.api.cancel_order.return_value = True
        
        result = order_manager.cancel_order("test_order_123")
        
        assert result is True
        order_manager.api.cancel_order.assert_called_once_with("test_order_123")
    
    def test_cancel_order_failure(self, order_manager):
        """Test order cancellation failure."""
        from modules.alpaca_api import AlpacaAPIError
        order_manager.api.cancel_order.side_effect = AlpacaAPIError("Order not found")
        
        result = order_manager.cancel_order("invalid_order")
        
        assert result is False
    
    def test_cancel_all_pending_specific_symbol(self, order_manager):
        """Test cancelling all pending orders for specific symbol."""
        # Set up active orders
        breakout_orders = BreakoutOrders(
            long_order_id="long_123",
            short_order_id="short_456",
            symbol="MNQ"
        )
        order_manager.active_breakout_orders["MNQ"] = breakout_orders
        order_manager.api.cancel_order.return_value = True
        
        result = order_manager.cancel_all_pending("MNQ")
        
        assert result is True
        assert "MNQ" not in order_manager.active_breakout_orders
        assert order_manager.api.cancel_order.call_count == 2
    
    def test_cancel_all_pending_all_symbols(self, order_manager):
        """Test cancelling all pending orders for all symbols."""
        order_manager.api.cancel_all_orders.return_value = True
        
        result = order_manager.cancel_all_pending()
        
        assert result is True
        assert len(order_manager.active_breakout_orders) == 0
        order_manager.api.cancel_all_orders.assert_called_once()
    
    def test_has_active_orders_specific_symbol(self, order_manager):
        """Test checking for active orders for specific symbol."""
        breakout_orders = BreakoutOrders(symbol="MNQ")
        order_manager.active_breakout_orders["MNQ"] = breakout_orders
        
        assert order_manager.has_active_orders("MNQ") is True
        assert order_manager.has_active_orders("ES") is False
    
    def test_has_active_orders_any_symbol(self, order_manager):
        """Test checking for any active orders."""
        assert order_manager.has_active_orders() is False
        
        breakout_orders = BreakoutOrders(symbol="MNQ")
        order_manager.active_breakout_orders["MNQ"] = breakout_orders
        
        assert order_manager.has_active_orders() is True
    
    def test_get_active_orders(self, order_manager):
        """Test getting active orders."""
        breakout_orders = BreakoutOrders(symbol="MNQ")
        order_manager.active_breakout_orders["MNQ"] = breakout_orders
        
        active_orders = order_manager.get_active_orders()
        
        assert "MNQ" in active_orders
        assert active_orders["MNQ"].symbol == "MNQ"
    
    def test_get_executed_trades(self, order_manager):
        """Test getting executed trades."""
        trade = TradeExecution(
            order_id="test_123",
            symbol="MNQ",
            side="long",
            quantity=4,
            entry_price=15035.0,
            timestamp=datetime.now(),
            stop_loss=15010.0,
            take_profit=15085.0
        )
        order_manager.executed_trades.append(trade)
        
        executed_trades = order_manager.get_executed_trades()
        
        assert len(executed_trades) == 1
        assert executed_trades[0].symbol == "MNQ"
    
    def test_handle_order_fill_long(self, order_manager):
        """Test handling long order fill."""
        breakout_orders = BreakoutOrders(
            long_order_id="long_123",
            short_order_id="short_456",
            symbol="MNQ",
            stop_loss_points=25.0,
            take_profit_points=50.0,
            position_size=4
        )
        
        # Mock order status response
        order_manager.api.get_order_status.return_value = {
            'filled_avg_price': 15035.0
        }
        order_manager.api.cancel_order.return_value = True
        
        order_manager._handle_order_fill(breakout_orders, 'long')
        
        # Check that opposite order was cancelled
        order_manager.api.cancel_order.assert_called_once_with("short_456")
        
        # Check that trade was recorded
        assert len(order_manager.executed_trades) == 1
        trade = order_manager.executed_trades[0]
        assert trade.side == 'long'
        assert trade.entry_price == 15035.0
        assert trade.stop_loss == 15010.0  # 15035 - 25
        assert trade.take_profit == 15085.0  # 15035 + 50
    
    def test_handle_order_fill_short(self, order_manager):
        """Test handling short order fill."""
        breakout_orders = BreakoutOrders(
            long_order_id="long_123",
            short_order_id="short_456",
            symbol="MNQ",
            stop_loss_points=25.0,
            take_profit_points=50.0,
            position_size=4
        )
        
        # Mock order status response
        order_manager.api.get_order_status.return_value = {
            'filled_avg_price': 14965.0
        }
        order_manager.api.cancel_order.return_value = True
        
        order_manager._handle_order_fill(breakout_orders, 'short')
        
        # Check that opposite order was cancelled
        order_manager.api.cancel_order.assert_called_once_with("long_123")
        
        # Check that trade was recorded
        assert len(order_manager.executed_trades) == 1
        trade = order_manager.executed_trades[0]
        assert trade.side == 'short'
        assert trade.entry_price == 14965.0
        assert trade.stop_loss == 14990.0  # 14965 + 25
        assert trade.take_profit == 14915.0  # 14965 - 50
    
    def test_check_order_status(self, order_manager):
        """Test checking order status."""
        order_manager.api.get_order_status.return_value = {'status': 'filled'}
        
        status = order_manager._check_order_status("test_order_123")
        
        assert status == 'filled'
        order_manager.api.get_order_status.assert_called_once_with("test_order_123")
    
    def test_check_order_status_error(self, order_manager):
        """Test checking order status with error."""
        order_manager.api.get_order_status.side_effect = Exception("API Error")
        
        status = order_manager._check_order_status("test_order_123")
        
        assert status == 'unknown'
    
    def test_on_trade_exit(self, order_manager):
        """Test handling trade exit."""
        # Set up executed trade
        trade = TradeExecution(
            order_id="test_123",
            symbol="MNQ",
            side="long",
            quantity=4,
            entry_price=15035.0,
            timestamp=datetime.now(),
            stop_loss=15010.0,
            take_profit=15085.0
        )
        order_manager.executed_trades.append(trade)
        
        # Mock the record_trade_result method
        with patch.object(order_manager.risk_manager, 'record_trade_result') as mock_record:
            order_manager.on_trade_exit("MNQ", 15085.0, 200.0)
            
            # Check that risk manager recorded the trade
            mock_record.assert_called_once_with(
                pnl=200.0,
                symbol="MNQ",
                quantity=4,
                entry_price=15035.0,
                exit_price=15085.0
            )
    
    def test_get_daily_trade_count(self, order_manager):
        """Test getting daily trade count."""
        order_manager.risk_manager.trades_today = 1
        
        count = order_manager.get_daily_trade_count()
        
        assert count == 1
    
    def test_cleanup(self, order_manager):
        """Test cleanup functionality."""
        order_manager.monitoring_active = True
        order_manager.api.cancel_all_orders.return_value = True
        
        order_manager.cleanup()
        
        assert order_manager.monitoring_active is False
        order_manager.api.cancel_all_orders.assert_called_once()
    
    def test_start_stop_monitoring(self, order_manager):
        """Test starting and stopping monitoring."""
        # Mock the monitoring thread to prevent actual execution
        with patch('threading.Thread') as mock_thread:
            mock_thread_instance = Mock()
            mock_thread.return_value = mock_thread_instance
            
            # Start monitoring
            order_manager.start_monitoring()
            assert order_manager.monitoring_active is True
            assert order_manager.monitor_thread is not None
            mock_thread_instance.start.assert_called_once()
            
            # Stop monitoring
            order_manager.stop_monitoring()
            assert order_manager.monitoring_active is False
