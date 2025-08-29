"""
Tests for Data Fetcher module.
"""

import pytest
from datetime import datetime, date, time
from unittest.mock import Mock, patch
import pytz

from modules.data_fetcher import DataFetcher, DataFetcherError


class TestDataFetcher:
    """Test cases for DataFetcher."""
    
    def test_get_opening_range_basic(self, data_fetcher, sample_market_data):
        """Test basic opening range calculation."""
        # Mock the API to return sample data
        data_fetcher.api.get_market_data.return_value = sample_market_data
        
        opening_high, opening_low = data_fetcher.get_opening_range("MNQ")
        
        # Expected high: max of all highs = 15035.0
        # Expected low: min of all lows = 14980.0
        assert opening_high == 15035.0
        assert opening_low == 14980.0
    
    def test_get_opening_range_single_bar(self, data_fetcher):
        """Test opening range with single bar."""
        single_bar = [{
            'timestamp': datetime.now(pytz.timezone('US/Eastern')),
            'open': 15000.0,
            'high': 15020.0,
            'low': 14990.0,
            'close': 15010.0,
            'volume': 1000
        }]
        
        data_fetcher.api.get_market_data.return_value = single_bar
        
        opening_high, opening_low = data_fetcher.get_opening_range("MNQ")
        
        assert opening_high == 15020.0
        assert opening_low == 14990.0
    
    def test_get_opening_range_no_data(self, data_fetcher):
        """Test opening range with no market data."""
        data_fetcher.api.get_market_data.return_value = []
        
        with pytest.raises(DataFetcherError, match="No market data available"):
            data_fetcher.get_opening_range("MNQ")
    
    def test_get_opening_range_specific_date(self, data_fetcher, sample_market_data, trading_day):
        """Test opening range for specific date."""
        data_fetcher.api.get_market_data.return_value = sample_market_data
        
        opening_high, opening_low = data_fetcher.get_opening_range("MNQ", trading_day)
        
        assert opening_high == 15035.0
        assert opening_low == 14980.0
        
        # Verify API was called with correct date
        data_fetcher.api.get_market_data.assert_called_once()
        call_args = data_fetcher.api.get_market_data.call_args
        assert call_args[1]['symbol'] == 'MNQ'
        assert call_args[1]['timeframe'] == '1Min'
    
    def test_get_opening_range_weekend(self, data_fetcher):
        """Test opening range on weekend (market closed)."""
        weekend_date = date(2024, 1, 13)  # Saturday
        
        with pytest.raises(DataFetcherError, match="Market is closed"):
            data_fetcher.get_opening_range("MNQ", weekend_date)
    
    def test_get_latest_price(self, data_fetcher):
        """Test getting latest price."""
        data_fetcher.api.get_latest_price.return_value = 15025.50
        
        price = data_fetcher.get_latest_price("MNQ")
        
        assert price == 15025.50
        data_fetcher.api.get_latest_price.assert_called_once_with("MNQ")
    
    def test_get_current_bar(self, data_fetcher):
        """Test getting current bar data."""
        current_bar = {
            'timestamp': datetime.now(pytz.timezone('US/Eastern')),
            'open': 15000.0,
            'high': 15030.0,
            'low': 14995.0,
            'close': 15020.0,
            'volume': 1500
        }
        
        data_fetcher.api.get_market_data.return_value = [current_bar]
        
        bar = data_fetcher.get_current_bar("MNQ")
        
        assert bar == current_bar
        assert bar['close'] == 15020.0
    
    def test_get_current_bar_no_data(self, data_fetcher):
        """Test getting current bar with no data."""
        data_fetcher.api.get_market_data.return_value = []
        
        with pytest.raises(DataFetcherError, match="No current bar data available"):
            data_fetcher.get_current_bar("MNQ")
    
    def test_is_market_open_weekday_hours(self, data_fetcher, market_timezone):
        """Test market open check during weekday market hours."""
        # Monday 10:00 AM ET (market is open)
        test_time = datetime(2024, 1, 15, 10, 0, tzinfo=market_timezone)
        
        assert data_fetcher.is_market_open(test_time) is True
    
    def test_is_market_open_before_hours(self, data_fetcher, market_timezone):
        """Test market open check before market hours."""
        # Monday 9:00 AM ET (before market open)
        test_time = datetime(2024, 1, 15, 9, 0, tzinfo=market_timezone)
        
        assert data_fetcher.is_market_open(test_time) is False
    
    def test_is_market_open_after_hours(self, data_fetcher, market_timezone):
        """Test market open check after market hours."""
        # Monday 5:00 PM ET (after market close)
        test_time = datetime(2024, 1, 15, 17, 0, tzinfo=market_timezone)
        
        assert data_fetcher.is_market_open(test_time) is False
    
    def test_is_market_open_weekend(self, data_fetcher, market_timezone):
        """Test market open check on weekend."""
        # Saturday 10:00 AM ET
        test_time = datetime(2024, 1, 13, 10, 0, tzinfo=market_timezone)
        
        assert data_fetcher.is_market_open(test_time) is False
    
    def test_is_market_open_current_time(self, data_fetcher):
        """Test market open check with current time."""
        # This will depend on when tests are run, so we just ensure it returns a boolean
        result = data_fetcher.is_market_open()
        assert isinstance(result, bool)
    
    def test_get_range_breakout_levels(self, data_fetcher, sample_market_data):
        """Test calculating breakout levels from opening range."""
        data_fetcher.api.get_market_data.return_value = sample_market_data
        
        range_data = data_fetcher.get_range_breakout_levels("MNQ", offset_points=15.0)
        
        expected_high = 15035.0
        expected_low = 14980.0
        expected_long_entry = expected_high + 15.0
        expected_short_entry = expected_low - 15.0
        
        assert range_data['opening_high'] == expected_high
        assert range_data['opening_low'] == expected_low
        assert range_data['long_entry'] == expected_long_entry
        assert range_data['short_entry'] == expected_short_entry
        assert range_data['range_size'] == expected_high - expected_low
        assert range_data['offset_points'] == 15.0
    
    def test_get_range_breakout_levels_custom_offset(self, data_fetcher, sample_market_data):
        """Test breakout levels with custom offset."""
        data_fetcher.api.get_market_data.return_value = sample_market_data
        
        range_data = data_fetcher.get_range_breakout_levels("MNQ", offset_points=20.0)
        
        expected_high = 15035.0
        expected_low = 14980.0
        
        assert range_data['long_entry'] == expected_high + 20.0
        assert range_data['short_entry'] == expected_low - 20.0
        assert range_data['offset_points'] == 20.0
    
    def test_wait_for_opening_range_not_ready(self, data_fetcher):
        """Test waiting for opening range when not ready."""
        # Mock the _get_market_open_datetime method directly
        with patch.object(data_fetcher, '_get_market_open_datetime') as mock_market_open:
            with patch('modules.data_fetcher.datetime') as mock_datetime:
                mock_now = datetime(2024, 1, 15, 9, 40, tzinfo=pytz.timezone('US/Eastern'))
                mock_datetime.now.return_value = mock_now
                mock_datetime.combine = datetime.combine
                
                # Mock market open time (after mock_now, so range not ready)
                market_open_time = datetime(2024, 1, 15, 9, 30, tzinfo=pytz.timezone('US/Eastern'))
                mock_market_open.return_value = market_open_time

                with pytest.raises(DataFetcherError, match="Opening range not ready"):
                    data_fetcher.wait_for_opening_range("MNQ")
    
    def test_wait_for_opening_range_ready(self, data_fetcher, sample_market_data):
        """Test waiting for opening range when ready."""
        # Mock the _get_market_open_datetime method directly
        with patch.object(data_fetcher, '_get_market_open_datetime') as mock_market_open:
            with patch('modules.data_fetcher.datetime') as mock_datetime:
                mock_now = datetime(2024, 1, 15, 9, 50, tzinfo=pytz.timezone('US/Eastern'))
                mock_datetime.now.return_value = mock_now
                mock_datetime.combine = datetime.combine
                
                # Mock market open time (before mock_now)
                market_open_time = datetime(2024, 1, 15, 9, 30, tzinfo=pytz.timezone('US/Eastern'))
                mock_market_open.return_value = market_open_time

                data_fetcher.api.get_market_data.return_value = sample_market_data

                opening_high, opening_low = data_fetcher.wait_for_opening_range("MNQ")
            
            assert opening_high == 15035.0
            assert opening_low == 14980.0
    
    def test_market_open_datetime_weekday(self, data_fetcher):
        """Test getting market open datetime for weekday."""
        weekday = date(2024, 1, 15)  # Monday
        
        market_open = data_fetcher._get_market_open_datetime(weekday)
        
        assert market_open is not None
        assert market_open.hour == 9
        assert market_open.minute == 30
        assert market_open.tzinfo.zone == 'US/Eastern'
    
    def test_market_open_datetime_weekend(self, data_fetcher):
        """Test getting market open datetime for weekend."""
        weekend = date(2024, 1, 13)  # Saturday
        
        market_open = data_fetcher._get_market_open_datetime(weekend)
        
        assert market_open is None
    
    def test_api_error_handling(self, data_fetcher):
        """Test API error handling."""
        from modules.alpaca_api import AlpacaAPIError
        
        data_fetcher.api.get_market_data.side_effect = AlpacaAPIError("API Error")
        
        with pytest.raises(DataFetcherError, match="Failed to get opening range"):
            data_fetcher.get_opening_range("MNQ")
    
    def test_unexpected_error_handling(self, data_fetcher):
        """Test unexpected error handling."""
        data_fetcher.api.get_market_data.side_effect = Exception("Unexpected error")
        
        with pytest.raises(DataFetcherError, match="Unexpected error"):
            data_fetcher.get_opening_range("MNQ")
