"""
Alpaca API Connector for NASDAQ Breakout Bot.
Provides interface to Alpaca's trading API.
"""

import logging
import time
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime, timedelta

import alpaca_trade_api as tradeapi
from alpaca_trade_api.rest import APIError, TimeFrame


@dataclass
class OrderParams:
    """Order parameters for placing trades."""
    symbol: str
    qty: int
    side: str  # 'buy' or 'sell'
    type: str  # 'market', 'limit', 'stop', 'stop_limit'
    time_in_force: str = 'day'
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    take_profit: Optional[float] = None
    stop_loss: Optional[float] = None


class AlpacaAPIError(Exception):
    """Custom exception for Alpaca API errors."""
    pass


class AlpacaAPI:
    """Alpaca API connector for trading operations."""
    
    def __init__(self, api_key: str, secret_key: str, paper_trading: bool = True):
        """
        Initialize Alpaca API connection.
        
        Args:
            api_key: Alpaca API key
            secret_key: Alpaca secret key
            paper_trading: Use paper trading endpoint if True
        """
        self.logger = logging.getLogger(__name__)
        
        base_url = 'https://paper-api.alpaca.markets' if paper_trading else 'https://api.alpaca.markets'
        
        try:
            self.api = tradeapi.REST(
                api_key,
                secret_key,
                base_url,
                api_version='v2'
            )
            self.logger.info(f"Initialized Alpaca API connection (paper: {paper_trading})")
        except Exception as e:
            self.logger.error(f"Failed to initialize Alpaca API: {e}")
            raise AlpacaAPIError(f"API initialization failed: {e}")
    
    def get_account_info(self) -> Dict[str, Any]:
        """
        Fetch account information including equity and buying power.
        
        Returns:
            Dict containing account details
        """
        return self._retry_api_call(self._get_account_info_impl)
    
    def get_market_data(self, symbol: str, timeframe: str, start_time: datetime, 
                       end_time: datetime) -> List[Dict[str, Any]]:
        """
        Retrieve historical price data.
        
        Args:
            symbol: Trading symbol (e.g., 'QQQ')
            timeframe: Timeframe ('15Min', '1Hour', etc.)
            start_time: Start datetime
            end_time: End datetime
            
        Returns:
            List of bar data dictionaries
        """
        return self._retry_api_call(self._get_market_data_impl, symbol, timeframe, start_time, end_time)
    
    def get_latest_price(self, symbol: str) -> float:
        """
        Fetch the latest traded price for a symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Latest price as float
        """
        return self._retry_api_call(self._get_latest_price_impl, symbol)
    
    def submit_order(self, order_params: OrderParams) -> Dict[str, Any]:
        """
        Submit an order to Alpaca.
        
        Args:
            order_params: Order parameters
            
        Returns:
            Order response dictionary
        """
        return self._retry_api_call(self._submit_order_impl, order_params, max_retries=2)
    
    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order by ID.
        
        Args:
            order_id: Order ID to cancel
            
        Returns:
            True if successful
        """
        return self._retry_api_call(self._cancel_order_impl, order_id, max_retries=2)
    
    def cancel_all_orders(self) -> bool:
        """
        Cancel all open orders.
        
        Returns:
            True if successful
        """
        return self._retry_api_call(self._cancel_all_orders_impl, max_retries=2)
    
    def get_order_status(self, order_id: str) -> Dict[str, Any]:
        """
        Get order status by ID.
        
        Args:
            order_id: Order ID to check
            
        Returns:
            Order status dictionary
        """
        return self._retry_api_call(self._get_order_status_impl, order_id)
    
    def _retry_api_call(self, func, *args, max_retries: int = 3, **kwargs):
        """
        Retry API calls with exponential backoff.
        
        Args:
            func: Function to retry
            max_retries: Maximum number of retries
            *args, **kwargs: Function arguments
            
        Returns:
            Function result
        """
        last_exception = None
        
        for attempt in range(max_retries):
            try:
                self.logger.debug(f"API call attempt {attempt + 1}/{max_retries}: {func.__name__}")
                result = func(*args, **kwargs)
                if attempt > 0:
                    self.logger.info(f"API call succeeded on attempt {attempt + 1}: {func.__name__}")
                return result
                
            except APIError as e:
                last_exception = e
                # Check if error is retryable
                if self._is_retryable_error(e) and attempt < max_retries - 1:
                    wait_time = min(2 ** attempt, 30)  # Cap at 30 seconds
                    self.logger.warning(f"Retryable API error (attempt {attempt + 1}/{max_retries}), "
                                      f"retrying in {wait_time}s: {e}")
                    time.sleep(wait_time)
                else:
                    self.logger.error(f"API error (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt == max_retries - 1:
                        raise AlpacaAPIError(f"API call failed after {max_retries} attempts: {e}")
                    
            except Exception as e:
                last_exception = e
                self.logger.error(f"Unexpected error in API call (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    raise AlpacaAPIError(f"Unexpected error after {max_retries} attempts: {e}")
                time.sleep(2 ** attempt)
        
        # This should not be reached, but just in case
        raise AlpacaAPIError(f"API call failed after {max_retries} attempts: {last_exception}")
    
    def _is_retryable_error(self, error: APIError) -> bool:
        """
        Determine if an API error is retryable.
        
        Args:
            error: API error to check
            
        Returns:
            True if error is retryable
        """
        # Check status code if available
        if hasattr(error, 'status_code') and error.status_code is not None:
            # Retry on server errors (5xx) and rate limits (429)
            if error.status_code >= 500 or error.status_code == 429:
                return True
            # Don't retry on client errors (4xx) except rate limits
            if 400 <= error.status_code < 500:
                return False
        
        # Check error message for common retryable patterns
        error_msg = str(error).lower()
        retryable_patterns = [
            'timeout', 'connection', 'network', 'rate limit', 
            'too many requests', 'service unavailable', 'internal server error'
        ]
        
        return any(pattern in error_msg for pattern in retryable_patterns)
    
    def _get_account_info_impl(self) -> Dict[str, Any]:
        """Implementation of get_account_info with detailed logging."""
        self.logger.debug("Fetching account information")
        
        try:
            account = self.api.get_account()
            account_info = {
                'equity': float(account.equity),
                'buying_power': float(account.buying_power),
                'cash': float(account.cash),
                'portfolio_value': float(account.portfolio_value),
                'day_trade_count': int(getattr(account, 'daytrade_count', 0)),
                'pattern_day_trader': getattr(account, 'pattern_day_trader', False)
            }
            
            self.logger.info(f"Account info retrieved - Equity: ${account_info['equity']:.2f}, "
                           f"Buying Power: ${account_info['buying_power']:.2f}")
            self.logger.debug(f"Full account info: {account_info}")
            
            return account_info
            
        except Exception as e:
            self.logger.error(f"Failed to get account info: {e}")
            raise
    
    def _get_market_data_impl(self, symbol: str, timeframe: str, start_time: datetime, 
                             end_time: datetime) -> List[Dict[str, Any]]:
        """Implementation of get_market_data with detailed logging."""
        self.logger.debug(f"Fetching market data for {symbol} ({timeframe}) from {start_time} to {end_time}")
        
        try:
            # Map timeframe string to TimeFrame enum
            from alpaca_trade_api.rest import TimeFrameUnit
            
            timeframe_map = {
                '1Min': TimeFrame.Minute,
                '5Min': TimeFrame(5, TimeFrameUnit.Minute),
                '15Min': TimeFrame(15, TimeFrameUnit.Minute),
                '1Hour': TimeFrame.Hour,
                '1Day': TimeFrame.Day
            }
            
            tf = timeframe_map.get(timeframe, TimeFrame(15, TimeFrameUnit.Minute))
            
            bars = self.api.get_bars(
                symbol,
                tf,
                start=start_time.isoformat(),
                end=end_time.isoformat(),
                adjustment='raw'
            )
            
            bar_data = []
            for bar in bars:
                bar_data.append({
                    'timestamp': bar.t,
                    'open': float(bar.o),
                    'high': float(bar.h),
                    'low': float(bar.l),
                    'close': float(bar.c),
                    'volume': int(bar.v)
                })
            
            self.logger.info(f"Retrieved {len(bar_data)} bars for {symbol} ({timeframe})")
            if bar_data:
                first_bar = bar_data[0]
                last_bar = bar_data[-1]
                self.logger.debug(f"First bar: {first_bar['timestamp']} OHLC: {first_bar['open']:.2f}/ "
                                f"{first_bar['high']:.2f}/{first_bar['low']:.2f}/{first_bar['close']:.2f}")
                self.logger.debug(f"Last bar: {last_bar['timestamp']} OHLC: {last_bar['open']:.2f}/ "
                                f"{last_bar['high']:.2f}/{last_bar['low']:.2f}/{last_bar['close']:.2f}")
            
            return bar_data
            
        except Exception as e:
            self.logger.error(f"Failed to get market data for {symbol}: {e}")
            raise
    
    def _get_latest_price_impl(self, symbol: str) -> float:
        """Implementation of get_latest_price with detailed logging."""
        self.logger.debug(f"Fetching latest price for {symbol}")
        
        try:
            latest_trade = self.api.get_latest_trade(symbol)
            price = float(latest_trade.price)
            
            self.logger.info(f"Latest price for {symbol}: ${price:.2f}")
            self.logger.debug(f"Latest trade details - Price: ${price:.2f}, Time: {latest_trade.timestamp}")
            
            return price
            
        except Exception as e:
            self.logger.error(f"Failed to get latest price for {symbol}: {e}")
            raise
    
    def _submit_order_impl(self, order_params: OrderParams) -> Dict[str, Any]:
        """Implementation of submit_order with detailed logging."""
        self.logger.info(f"Submitting order: {order_params.side.upper()} {order_params.qty} {order_params.symbol} "
                        f"@ {order_params.type.upper()}")
        self.logger.debug(f"Order parameters: {order_params}")
        
        try:
            # Build order request
            order_request = {
                'symbol': order_params.symbol,
                'qty': order_params.qty,
                'side': order_params.side,
                'type': order_params.type,
                'time_in_force': order_params.time_in_force
            }
            
            # Add price parameters if provided
            if order_params.limit_price:
                order_request['limit_price'] = order_params.limit_price
                self.logger.debug(f"Limit price: ${order_params.limit_price:.2f}")
            if order_params.stop_price:
                order_request['stop_price'] = order_params.stop_price
                self.logger.debug(f"Stop price: ${order_params.stop_price:.2f}")
            
            # Add bracket order parameters
            order_data = {}
            if order_params.take_profit:
                order_data['take_profit'] = {'limit_price': order_params.take_profit}
                self.logger.debug(f"Take profit: ${order_params.take_profit:.2f}")
            if order_params.stop_loss:
                order_data['stop_loss'] = {'stop_price': order_params.stop_loss}
                self.logger.debug(f"Stop loss: ${order_params.stop_loss:.2f}")
            
            if order_data:
                order_request['order_class'] = 'bracket'
                order_request.update(order_data)
                self.logger.debug("Using bracket order class")
            
            # Submit order
            order = self.api.submit_order(**order_request)
            
            order_info = {
                'id': order.id,
                'symbol': order.symbol,
                'qty': int(order.qty),
                'side': order.side,
                'type': order.order_type,
                'status': order.status,
                'filled_qty': int(order.filled_qty or 0),
                'filled_avg_price': float(order.filled_avg_price or 0)
            }
            
            self.logger.info(f"Order submitted successfully - ID: {order.id}, Status: {order.status}")
            self.logger.debug(f"Order response: {order_info}")
            
            return order_info
            
        except Exception as e:
            self.logger.error(f"Failed to submit order: {e}")
            self.logger.debug(f"Failed order request: {order_request if 'order_request' in locals() else 'N/A'}")
            raise
    
    def _cancel_order_impl(self, order_id: str) -> bool:
        """Implementation of cancel_order with detailed logging."""
        self.logger.info(f"Cancelling order: {order_id}")
        
        try:
            self.api.cancel_order(order_id)
            self.logger.info(f"Order cancelled successfully: {order_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {e}")
            raise
    
    def _cancel_all_orders_impl(self) -> bool:
        """Implementation of cancel_all_orders with detailed logging."""
        self.logger.info("Cancelling all open orders")
        
        try:
            self.api.cancel_all_orders()
            self.logger.info("All orders cancelled successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to cancel all orders: {e}")
            raise
    
    def _get_order_status_impl(self, order_id: str) -> Dict[str, Any]:
        """Implementation of get_order_status with detailed logging."""
        self.logger.debug(f"Getting order status: {order_id}")
        
        try:
            order = self.api.get_order(order_id)
            
            order_status = {
                'id': order.id,
                'status': order.status,
                'filled_qty': int(order.filled_qty or 0),
                'filled_avg_price': float(order.filled_avg_price or 0),
                'submitted_at': order.submitted_at,
                'filled_at': order.filled_at
            }
            
            self.logger.debug(f"Order status retrieved - ID: {order.id}, Status: {order.status}, "
                            f"Filled: {order_status['filled_qty']}/{order.qty}")
            
            return order_status
            
        except Exception as e:
            self.logger.error(f"Failed to get order status for {order_id}: {e}")
            raise
