"""
Data Fetcher for NASDAQ Breakout Bot.
Handles market data retrieval for opening range breakout strategy.
"""

import logging
from typing import Tuple, Optional, Dict, Any
from datetime import datetime, timedelta, time
import pytz

from .alpaca_api import AlpacaAPI, AlpacaAPIError


class DataFetcherError(Exception):
    """Custom exception for data fetcher errors."""
    pass


class DataFetcher:
    """Handles market data retrieval for trading strategy."""
    
    def __init__(self, alpaca_api: AlpacaAPI):
        """
        Initialize data fetcher with Alpaca API connector.
        
        Args:
            alpaca_api: Initialized Alpaca API instance
        """
        self.api = alpaca_api
        self.logger = logging.getLogger(__name__)
        
        # US Eastern timezone for market hours
        self.market_tz = pytz.timezone('US/Eastern')
        
        # Standard market open time (9:30 AM ET)
        self.market_open_time = time(9, 30)
        
        self.logger.info("Data fetcher initialized")
    
    def get_opening_range(self, symbol: str, date: Optional[datetime] = None) -> Tuple[float, float]:
        """
        Get the 15-minute opening range (high and low) for a given trading day.
        
        Args:
            symbol: Trading symbol (e.g., 'QQQ')
            date: Trading date (defaults to today)
            
        Returns:
            Tuple of (opening_high, opening_low)
        """
        try:
            if date is None:
                date = datetime.now(self.market_tz).date()
            
            # Get market calendar to ensure it's a trading day
            market_open_dt = self._get_market_open_datetime(date)
            if market_open_dt is None:
                raise DataFetcherError(f"Market is closed on {date}")
            
            # Calculate 15-minute window
            range_start = market_open_dt
            range_end = market_open_dt + timedelta(minutes=15)
            
            self.logger.info(f"Fetching opening range for {symbol} from {range_start} to {range_end}")
            
            # Get 1-minute bars to calculate exact high/low
            bars = self.api.get_market_data(
                symbol=symbol,
                timeframe='1Min',
                start_time=range_start,
                end_time=range_end
            )
            
            if not bars:
                raise DataFetcherError(f"No market data available for {symbol} on {date}")
            
            # Calculate high and low from all bars in the 15-minute window
            opening_high = max(bar['high'] for bar in bars)
            opening_low = min(bar['low'] for bar in bars)
            
            self.logger.info(f"Opening range for {symbol}: High=${opening_high:.2f}, Low=${opening_low:.2f}")
            
            return opening_high, opening_low
            
        except AlpacaAPIError as e:
            self.logger.error(f"API error getting opening range: {e}")
            raise DataFetcherError(f"Failed to get opening range: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error getting opening range: {e}")
            raise DataFetcherError(f"Unexpected error: {e}")
    
    def get_latest_price(self, symbol: str) -> float:
        """
        Get the latest traded price for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Latest price
        """
        try:
            price = self.api.get_latest_price(symbol)
            self.logger.debug(f"Latest price for {symbol}: ${price:.2f}")
            return price
            
        except AlpacaAPIError as e:
            self.logger.error(f"API error getting latest price: {e}")
            raise DataFetcherError(f"Failed to get latest price: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error getting latest price: {e}")
            raise DataFetcherError(f"Unexpected error: {e}")
    
    def get_current_bar(self, symbol: str, timeframe: str = '1Min') -> Dict[str, Any]:
        """
        Get the current/latest bar data for a symbol.
        
        Args:
            symbol: Trading symbol
            timeframe: Timeframe for the bar data
            
        Returns:
            Dictionary containing OHLCV data
        """
        try:
            now = datetime.now(self.market_tz)
            start_time = now - timedelta(minutes=5)  # Get last 5 minutes to ensure we have data
            
            bars = self.api.get_market_data(
                symbol=symbol,
                timeframe=timeframe,
                start_time=start_time,
                end_time=now
            )
            
            if not bars:
                raise DataFetcherError(f"No current bar data available for {symbol}")
            
            # Return the most recent bar
            latest_bar = bars[-1]
            self.logger.debug(f"Current bar for {symbol}: Close=${latest_bar['close']:.2f}")
            
            return latest_bar
            
        except AlpacaAPIError as e:
            self.logger.error(f"API error getting current bar: {e}")
            raise DataFetcherError(f"Failed to get current bar: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error getting current bar: {e}")
            raise DataFetcherError(f"Unexpected error: {e}")
    
    def is_market_open(self, dt: Optional[datetime] = None) -> bool:
        """
        Check if the market is currently open.
        
        Args:
            dt: Datetime to check (defaults to now)
            
        Returns:
            True if market is open
        """
        try:
            if dt is None:
                dt = datetime.now(self.market_tz)
            
            # Convert to market timezone if needed
            if dt.tzinfo is None:
                dt = self.market_tz.localize(dt)
            elif dt.tzinfo != self.market_tz:
                dt = dt.astimezone(self.market_tz)
            
            # Check if it's a weekday
            if dt.weekday() >= 5:  # Saturday = 5, Sunday = 6
                return False
            
            # Check if it's within market hours (9:30 AM - 4:00 PM ET)
            market_time = dt.time()
            market_open = time(9, 30)
            market_close = time(16, 0)
            
            is_open = market_open <= market_time <= market_close
            self.logger.debug(f"Market open check for {dt}: {is_open}")
            
            return is_open
            
        except Exception as e:
            self.logger.error(f"Error checking market status: {e}")
            return False
    
    def wait_for_opening_range(self, symbol: str) -> Tuple[float, float]:
        """
        Wait until 15 minutes after market open and then fetch the opening range.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Tuple of (opening_high, opening_low)
        """
        try:
            now = datetime.now(self.market_tz)
            today = now.date()
            
            market_open_dt = self._get_market_open_datetime(today)
            if market_open_dt is None:
                raise DataFetcherError("Market is closed today")
            
            # Time when opening range is complete (15 minutes after open)
            range_complete_time = market_open_dt + timedelta(minutes=15)
            
            if now < range_complete_time:
                wait_seconds = (range_complete_time - now).total_seconds()
                self.logger.info(f"Waiting {wait_seconds:.0f} seconds for opening range to complete")
                
                # Don't actually wait here - let the calling code handle timing
                raise DataFetcherError(f"Opening range not ready. Wait until {range_complete_time}")
            
            # Opening range is complete, fetch it
            return self.get_opening_range(symbol, today)
            
        except Exception as e:
            self.logger.error(f"Error waiting for opening range: {e}")
            raise DataFetcherError(f"Failed to wait for opening range: {e}")
    
    def _get_market_open_datetime(self, date) -> Optional[datetime]:
        """
        Get the market open datetime for a given date.
        
        Args:
            date: Date to check
            
        Returns:
            Market open datetime or None if market is closed
        """
        try:
            # Convert date to datetime in market timezone
            if isinstance(date, datetime):
                dt = date
            else:
                dt = datetime.combine(date, self.market_open_time)
            
            # Ensure it's in market timezone
            if dt.tzinfo is None:
                dt = self.market_tz.localize(dt)
            elif dt.tzinfo != self.market_tz:
                dt = dt.astimezone(self.market_tz)
            
            # Check if it's a trading day (basic check - excludes holidays)
            if dt.weekday() >= 5:  # Weekend
                return None
            
            return dt
            
        except Exception as e:
            self.logger.error(f"Error getting market open datetime: {e}")
            return None
    
    def get_range_breakout_levels(self, symbol: str, offset_points: float = 15.0) -> Dict[str, float]:
        """
        Get opening range and calculate breakout levels with offset.
        
        Args:
            symbol: Trading symbol
            offset_points: Points to add/subtract from range for breakout triggers
            
        Returns:
            Dictionary with range and breakout levels
        """
        try:
            opening_high, opening_low = self.get_opening_range(symbol)
            
            # Calculate breakout levels
            long_entry = opening_high + offset_points
            short_entry = opening_low - offset_points
            
            range_data = {
                'opening_high': opening_high,
                'opening_low': opening_low,
                'range_size': opening_high - opening_low,
                'long_entry': long_entry,
                'short_entry': short_entry,
                'offset_points': offset_points
            }
            
            self.logger.info(f"Breakout levels for {symbol}: Long=${long_entry:.2f}, Short=${short_entry:.2f}")
            
            return range_data
            
        except Exception as e:
            self.logger.error(f"Error calculating breakout levels: {e}")
            raise DataFetcherError(f"Failed to calculate breakout levels: {e}")
