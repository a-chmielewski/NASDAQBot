"""
Pytest configuration and fixtures for NASDAQ Breakout Bot tests.
"""

import pytest
from unittest.mock import Mock, MagicMock
from datetime import datetime, date
import pytz
from typing import Dict, Any, List

from modules.alpaca_api import AlpacaAPI
from modules.risk_manager import RiskManager
from modules.data_fetcher import DataFetcher
from modules.opening_range_breakout import OpeningRangeBreakout, StrategyConfig


@pytest.fixture
def mock_alpaca_api():
    """Mock Alpaca API for testing."""
    mock_api = Mock(spec=AlpacaAPI)
    
    # Mock account info
    mock_api.get_account_info.return_value = {
        'equity': 100000.0,
        'buying_power': 200000.0,
        'cash': 50000.0,
        'portfolio_value': 100000.0,
        'day_trade_count': 0,
        'pattern_day_trader': False
    }
    
    # Mock market data
    mock_api.get_market_data.return_value = [
        {
            'timestamp': datetime.now(pytz.timezone('US/Eastern')),
            'open': 15000.0,
            'high': 15020.0,
            'low': 14980.0,
            'close': 15010.0,
            'volume': 1000
        }
    ]
    
    # Mock latest price
    mock_api.get_latest_price.return_value = 15010.0
    
    # Mock order submission
    mock_api.submit_order.return_value = {
        'id': 'test_order_123',
        'symbol': 'MNQ',
        'qty': 10,
        'side': 'buy',
        'type': 'stop',
        'status': 'accepted',
        'filled_qty': 0,
        'filled_avg_price': 0.0
    }
    
    # Mock order status
    mock_api.get_order_status.return_value = {
        'id': 'test_order_123',
        'status': 'filled',
        'filled_qty': 10,
        'filled_avg_price': 15025.0,
        'submitted_at': datetime.now(),
        'filled_at': datetime.now()
    }
    
    # Mock cancellation
    mock_api.cancel_order.return_value = True
    mock_api.cancel_all_orders.return_value = True
    
    return mock_api


@pytest.fixture
def risk_manager():
    """Create risk manager for testing."""
    return RiskManager(
        max_daily_loss_percent=0.02,
        max_trades_per_day=2,
        default_risk_percent=0.005,
        point_value=5.0  # MNQ futures point value
    )


@pytest.fixture
def data_fetcher(mock_alpaca_api):
    """Create data fetcher with mocked API."""
    return DataFetcher(mock_alpaca_api)


@pytest.fixture
def strategy():
    """Create strategy for testing."""
    config = StrategyConfig(
        breakout_offset_points=15.0,
        stop_loss_points=25.0,
        risk_reward_ratio=2.0
    )
    return OpeningRangeBreakout(config)


@pytest.fixture
def sample_market_data():
    """Sample market data for testing."""
    return [
        {
            'timestamp': datetime(2024, 1, 15, 9, 30, tzinfo=pytz.timezone('US/Eastern')),
            'open': 15000.0,
            'high': 15020.0,
            'low': 14980.0,
            'close': 15010.0,
            'volume': 1000
        },
        {
            'timestamp': datetime(2024, 1, 15, 9, 31, tzinfo=pytz.timezone('US/Eastern')),
            'open': 15010.0,
            'high': 15030.0,
            'low': 14990.0,
            'close': 15025.0,
            'volume': 1200
        },
        {
            'timestamp': datetime(2024, 1, 15, 9, 32, tzinfo=pytz.timezone('US/Eastern')),
            'open': 15025.0,
            'high': 15035.0,
            'low': 15005.0,
            'close': 15020.0,
            'volume': 800
        }
    ]


@pytest.fixture
def trading_day():
    """Get a valid trading day."""
    # Monday, January 15, 2024
    return date(2024, 1, 15)


@pytest.fixture
def market_timezone():
    """Market timezone fixture."""
    return pytz.timezone('US/Eastern')


@pytest.fixture(autouse=True)
def reset_risk_manager_data():
    """Reset risk manager data before each test."""
    # Clean up any existing data files
    import os
    data_file = "data/risk_manager_data.json"
    if os.path.exists(data_file):
        os.remove(data_file)
