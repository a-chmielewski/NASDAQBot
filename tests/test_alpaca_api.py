"""
Tests for Alpaca API module.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from modules.alpaca_api import AlpacaAPI, AlpacaAPIError, OrderParams


class TestAlpacaAPI:
    """Test cases for AlpacaAPI (mocked - no live API calls)."""
    
    @pytest.fixture
    def alpaca_api(self):
        """Create AlpacaAPI instance with mocked internal API."""
        with patch('modules.alpaca_api.tradeapi.REST') as mock_rest:
            api = AlpacaAPI("test_key", "test_secret", paper_trading=True)
            api.api = Mock()
            return api
    
    def test_initialization_paper_trading(self):
        """Test API initialization with paper trading."""
        with patch('modules.alpaca_api.tradeapi.REST') as mock_rest:
            api = AlpacaAPI("test_key", "test_secret", paper_trading=True)
            
            mock_rest.assert_called_once_with(
                "test_key",
                "test_secret", 
                'https://paper-api.alpaca.markets',
                api_version='v2'
            )
    
    def test_initialization_live_trading(self):
        """Test API initialization with live trading."""
        with patch('modules.alpaca_api.tradeapi.REST') as mock_rest:
            api = AlpacaAPI("test_key", "test_secret", paper_trading=False)
            
            mock_rest.assert_called_once_with(
                "test_key",
                "test_secret",
                'https://api.alpaca.markets',
                api_version='v2'
            )
    
    def test_get_account_info_success(self, alpaca_api):
        """Test successful account info retrieval."""
        # Mock account object
        mock_account = Mock()
        mock_account.equity = "100000.50"
        mock_account.buying_power = "200000.00"
        mock_account.cash = "50000.25"
        mock_account.portfolio_value = "100000.50"
        mock_account.daytrade_count = 2
        mock_account.pattern_day_trader = False
        
        alpaca_api.api.get_account.return_value = mock_account
        
        account_info = alpaca_api.get_account_info()
        
        assert account_info['equity'] == 100000.50
        assert account_info['buying_power'] == 200000.00
        assert account_info['cash'] == 50000.25
        assert account_info['portfolio_value'] == 100000.50
        assert account_info['day_trade_count'] == 2
        assert account_info['pattern_day_trader'] is False
    
    def test_get_market_data_success(self, alpaca_api):
        """Test successful market data retrieval."""
        # Mock bar objects
        mock_bar1 = Mock()
        mock_bar1.t = datetime(2024, 1, 15, 9, 30)
        mock_bar1.o = 15000.0
        mock_bar1.h = 15020.0
        mock_bar1.l = 14980.0
        mock_bar1.c = 15010.0
        mock_bar1.v = 1000
        
        mock_bar2 = Mock()
        mock_bar2.t = datetime(2024, 1, 15, 9, 31)
        mock_bar2.o = 15010.0
        mock_bar2.h = 15030.0
        mock_bar2.l = 14990.0
        mock_bar2.c = 15025.0
        mock_bar2.v = 1200
        
        alpaca_api.api.get_bars.return_value = [mock_bar1, mock_bar2]
        
        start_time = datetime(2024, 1, 15, 9, 30)
        end_time = datetime(2024, 1, 15, 9, 45)
        
        bar_data = alpaca_api.get_market_data("MNQ", "1Min", start_time, end_time)
        
        assert len(bar_data) == 2
        assert bar_data[0]['open'] == 15000.0
        assert bar_data[0]['high'] == 15020.0
        assert bar_data[0]['low'] == 14980.0
        assert bar_data[0]['close'] == 15010.0
        assert bar_data[0]['volume'] == 1000
        assert bar_data[1]['close'] == 15025.0
    
    def test_get_latest_price_success(self, alpaca_api):
        """Test successful latest price retrieval."""
        mock_trade = Mock()
        mock_trade.price = 15025.50
        
        alpaca_api.api.get_latest_trade.return_value = mock_trade
        
        price = alpaca_api.get_latest_price("MNQ")
        
        assert price == 15025.50
        alpaca_api.api.get_latest_trade.assert_called_once_with("MNQ")
    
    def test_submit_order_basic(self, alpaca_api):
        """Test basic order submission."""
        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.symbol = "MNQ"
        mock_order.qty = 4
        mock_order.side = "buy"
        mock_order.order_type = "stop"
        mock_order.status = "accepted"
        mock_order.filled_qty = None
        mock_order.filled_avg_price = None
        
        alpaca_api.api.submit_order.return_value = mock_order
        
        order_params = OrderParams(
            symbol="MNQ",
            qty=4,
            side="buy",
            type="stop",
            stop_price=15035.0
        )
        
        order_info = alpaca_api.submit_order(order_params)
        
        assert order_info['id'] == "order_123"
        assert order_info['symbol'] == "MNQ"
        assert order_info['qty'] == 4
        assert order_info['side'] == "buy"
        assert order_info['type'] == "stop"
        assert order_info['status'] == "accepted"
    
    def test_submit_order_bracket(self, alpaca_api):
        """Test bracket order submission."""
        mock_order = Mock()
        mock_order.id = "bracket_order_123"
        mock_order.symbol = "MNQ"
        mock_order.qty = 4
        mock_order.side = "buy"
        mock_order.order_type = "stop"
        mock_order.status = "accepted"
        mock_order.filled_qty = None
        mock_order.filled_avg_price = None
        
        alpaca_api.api.submit_order.return_value = mock_order
        
        order_params = OrderParams(
            symbol="MNQ",
            qty=4,
            side="buy",
            type="stop",
            stop_price=15035.0,
            take_profit=15085.0,
            stop_loss=15010.0
        )
        
        order_info = alpaca_api.submit_order(order_params)
        
        # Verify bracket order was submitted
        call_args = alpaca_api.api.submit_order.call_args[1]
        assert call_args['order_class'] == 'bracket'
        assert 'take_profit' in call_args
        assert 'stop_loss' in call_args
        assert call_args['take_profit']['limit_price'] == 15085.0
        assert call_args['stop_loss']['stop_price'] == 15010.0
    
    def test_cancel_order_success(self, alpaca_api):
        """Test successful order cancellation."""
        alpaca_api.api.cancel_order.return_value = None
        
        result = alpaca_api.cancel_order("order_123")
        
        assert result is True
        alpaca_api.api.cancel_order.assert_called_once_with("order_123")
    
    def test_cancel_all_orders_success(self, alpaca_api):
        """Test successful cancellation of all orders."""
        alpaca_api.api.cancel_all_orders.return_value = None
        
        result = alpaca_api.cancel_all_orders()
        
        assert result is True
        alpaca_api.api.cancel_all_orders.assert_called_once()
    
    def test_get_order_status_success(self, alpaca_api):
        """Test successful order status retrieval."""
        mock_order = Mock()
        mock_order.id = "order_123"
        mock_order.status = "filled"
        mock_order.filled_qty = 4
        mock_order.filled_avg_price = 15035.0
        mock_order.submitted_at = datetime.now()
        mock_order.filled_at = datetime.now()
        
        alpaca_api.api.get_order.return_value = mock_order
        
        order_status = alpaca_api.get_order_status("order_123")
        
        assert order_status['id'] == "order_123"
        assert order_status['status'] == "filled"
        assert order_status['filled_qty'] == 4
        assert order_status['filled_avg_price'] == 15035.0
    
    def test_retry_logic_success_after_retry(self, alpaca_api):
        """Test retry logic succeeding after initial failure."""
        from modules.alpaca_api import APIError
        
        # Mock to fail once then succeed
        alpaca_api.api.get_account.side_effect = [
            APIError({"message": "Temporary error"}),
            Mock(equity="100000.0", buying_power="200000.0", cash="50000.0",
                 portfolio_value="100000.0", day_trade_count=0, pattern_day_trader=False)
        ]
        
        with patch('time.sleep'):  # Speed up test
            account_info = alpaca_api.get_account_info()
        
        assert account_info['equity'] == 100000.0
        assert alpaca_api.api.get_account.call_count == 2
    
    def test_retry_logic_max_retries_exceeded(self, alpaca_api):
        """Test retry logic failing after max retries."""
        from modules.alpaca_api import APIError
        
        # Mock to always fail
        alpaca_api.api.get_account.side_effect = APIError({"message": "Persistent error"})
        
        with patch('time.sleep'):  # Speed up test
            with pytest.raises(AlpacaAPIError):
                alpaca_api.get_account_info()
        
        assert alpaca_api.api.get_account.call_count == 3  # Default max retries
    
    def test_is_retryable_error(self, alpaca_api):
        """Test retryable error detection."""
        from modules.alpaca_api import APIError
        
        # Create mock error objects since we can't set status_code directly
        server_error = Mock(spec=APIError)
        server_error.status_code = 500
        assert alpaca_api._is_retryable_error(server_error) is True
        
        # Rate limit should be retryable
        rate_limit_error = Mock(spec=APIError)
        rate_limit_error.status_code = 429
        assert alpaca_api._is_retryable_error(rate_limit_error) is True
        
        # Client errors should not be retryable
        client_error = Mock(spec=APIError)
        client_error.status_code = 400
        assert alpaca_api._is_retryable_error(client_error) is False
        
        # Timeout should be retryable (based on message)
        timeout_error = APIError({"message": "Connection timeout"})
        assert alpaca_api._is_retryable_error(timeout_error) is True
    
    def test_timeframe_mapping(self, alpaca_api):
        """Test timeframe string to enum mapping."""
        from modules.alpaca_api import TimeFrame
        
        mock_bars = [Mock(t=datetime.now(), o=15000, h=15020, l=14980, c=15010, v=1000)]
        alpaca_api.api.get_bars.return_value = mock_bars
        
        # Test different timeframes
        alpaca_api.get_market_data("MNQ", "1Min", datetime.now(), datetime.now())
        alpaca_api.get_market_data("MNQ", "5Min", datetime.now(), datetime.now())
        alpaca_api.get_market_data("MNQ", "15Min", datetime.now(), datetime.now())
        alpaca_api.get_market_data("MNQ", "1Hour", datetime.now(), datetime.now())
        alpaca_api.get_market_data("MNQ", "1Day", datetime.now(), datetime.now())
        
        # Verify API was called with correct timeframes
        assert alpaca_api.api.get_bars.call_count == 5
    
    def test_api_error_handling(self, alpaca_api):
        """Test API error handling and conversion."""
        from modules.alpaca_api import APIError
        
        alpaca_api.api.get_account.side_effect = APIError({"message": "API Error"})
        
        with pytest.raises(AlpacaAPIError, match="API call failed after 3 attempts"):
            with patch('time.sleep'):  # Speed up test
                alpaca_api.get_account_info()
    
    def test_unexpected_error_handling(self, alpaca_api):
        """Test unexpected error handling."""
        alpaca_api.api.get_account.side_effect = ValueError("Unexpected error")
        
        with pytest.raises(AlpacaAPIError, match="Unexpected error after 3 attempts"):
            with patch('time.sleep'):  # Speed up test
                alpaca_api.get_account_info()
