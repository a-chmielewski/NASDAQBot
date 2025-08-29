"""
Enhanced Logging Module for NASDAQ Breakout Bot.
Provides colored console output, rotating file logs, and daily log files.
"""

import logging
import logging.handlers
import os
from datetime import datetime
from typing import Optional
import colorama
from colorama import Fore, Back, Style

# Initialize colorama for Windows support
colorama.init(autoreset=True)


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels."""
    
    COLORS = {
        'DEBUG': Fore.CYAN,
        'INFO': Fore.GREEN,
        'WARNING': Fore.YELLOW,
        'ERROR': Fore.RED,
        'CRITICAL': Fore.RED + Back.YELLOW + Style.BRIGHT
    }
    
    def __init__(self, fmt: str = None):
        super().__init__()
        self.fmt = fmt or '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        
    def format(self, record):
        # Create a copy of the record to avoid modifying the original
        log_record = logging.makeLogRecord(record.__dict__)
        
        # Color the level name
        level_color = self.COLORS.get(record.levelname, '')
        if level_color:
            log_record.levelname = f"{level_color}{record.levelname}{Style.RESET_ALL}"
        
        # Create formatter with the format
        formatter = logging.Formatter(self.fmt)
        return formatter.format(log_record)


class TradingLogFilter(logging.Filter):
    """Filter to add trading-specific context to log records."""
    
    def __init__(self):
        super().__init__()
        self.trading_session = None
        self.symbol = None
        
    def set_context(self, symbol: str = None, session: str = None):
        """Set trading context for logs."""
        if symbol:
            self.symbol = symbol
        if session:
            self.trading_session = session
    
    def filter(self, record):
        # Add trading context to record
        if self.symbol:
            record.symbol = self.symbol
        if self.trading_session:
            record.session = self.trading_session
        return True


class BotLogger:
    """Enhanced logger for the NASDAQ Breakout Bot."""
    
    def __init__(self, name: str = "NASDAQBot", log_dir: str = "logs", 
                 log_level: str = "INFO", max_file_size: int = 10485760,  # 10MB
                 backup_count: int = 5):
        """
        Initialize the enhanced logger.
        
        Args:
            name: Logger name
            log_dir: Directory for log files
            log_level: Logging level
            max_file_size: Maximum file size before rotation (bytes)
            backup_count: Number of backup files to keep
        """
        self.name = name
        self.log_dir = log_dir
        self.log_level = getattr(logging, log_level.upper())
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        
        # Create log directory
        os.makedirs(self.log_dir, exist_ok=True)
        
        # Create main logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.log_level)
        
        # Clear any existing handlers
        self.logger.handlers.clear()
        
        # Create trading filter
        self.trading_filter = TradingLogFilter()
        
        # Setup handlers
        self._setup_console_handler()
        self._setup_file_handlers()
        
        # Prevent duplicate logs
        self.logger.propagate = False
        
    def _setup_console_handler(self):
        """Setup colored console handler."""
        console_handler = logging.StreamHandler()
        console_handler.setLevel(self.log_level)
        
        # Use colored formatter for console
        console_formatter = ColoredFormatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        console_handler.addFilter(self.trading_filter)
        
        self.logger.addHandler(console_handler)
    
    def _setup_file_handlers(self):
        """Setup file handlers for different types of logs."""
        
        # Daily rotating log file
        daily_log_file = os.path.join(
            self.log_dir, 
            f"{datetime.now().strftime('%Y-%m-%d')}_NASDAQ.log"
        )
        
        # Main rotating file handler
        main_file_handler = logging.handlers.RotatingFileHandler(
            filename=os.path.join(self.log_dir, f"{self.name}.log"),
            maxBytes=self.max_file_size,
            backupCount=self.backup_count,
            encoding='utf-8'
        )
        main_file_handler.setLevel(self.log_level)
        
        # Daily file handler (creates new file each day)
        daily_file_handler = logging.FileHandler(
            filename=daily_log_file,
            encoding='utf-8'
        )
        daily_file_handler.setLevel(self.log_level)
        
        # Trade-specific log handler
        trade_log_file = os.path.join(
            self.log_dir,
            f"{datetime.now().strftime('%Y-%m-%d')}_NASDAQ_trades.log"
        )
        trade_file_handler = logging.FileHandler(
            filename=trade_log_file,
            encoding='utf-8'
        )
        trade_file_handler.setLevel(logging.INFO)
        
        # File formatter (no colors)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Enhanced formatter for trade logs
        trade_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(symbol)s] %(message)s'
        )
        
        # Set formatters
        main_file_handler.setFormatter(file_formatter)
        daily_file_handler.setFormatter(file_formatter)
        trade_file_handler.setFormatter(trade_formatter)
        
        # Add filters
        main_file_handler.addFilter(self.trading_filter)
        daily_file_handler.addFilter(self.trading_filter)
        trade_file_handler.addFilter(self.trading_filter)
        
        # Add handlers to logger
        self.logger.addHandler(main_file_handler)
        self.logger.addHandler(daily_file_handler)
        self.logger.addHandler(trade_file_handler)
    
    def get_logger(self, module_name: str = None) -> logging.Logger:
        """
        Get a logger for a specific module.
        
        Args:
            module_name: Name of the module
            
        Returns:
            Logger instance
        """
        if module_name:
            return logging.getLogger(f"{self.name}.{module_name}")
        return self.logger
    
    def set_trading_context(self, symbol: str = None, session: str = None):
        """Set trading context for enhanced logging."""
        self.trading_filter.set_context(symbol=symbol, session=session)
    
    def log_trade_event(self, message: str, level: str = "INFO", **kwargs):
        """
        Log a trade-specific event.
        
        Args:
            message: Log message
            level: Log level
            **kwargs: Additional context
        """
        log_level = getattr(logging, level.upper())
        
        # Add extra context to message
        if kwargs:
            context_str = " | ".join([f"{k}={v}" for k, v in kwargs.items()])
            message = f"{message} | {context_str}"
        
        self.logger.log(log_level, message)
    
    def log_performance_metrics(self, metrics: dict):
        """Log performance metrics."""
        self.logger.info("=== PERFORMANCE METRICS ===")
        for key, value in metrics.items():
            if isinstance(value, float):
                self.logger.info(f"{key}: {value:.4f}")
            else:
                self.logger.info(f"{key}: {value}")
        self.logger.info("=" * 30)
    
    def log_session_summary(self, summary: dict):
        """Log trading session summary."""
        self.logger.info("=== TRADING SESSION SUMMARY ===")
        for key, value in summary.items():
            if isinstance(value, float) and key.lower().find('price') != -1:
                self.logger.info(f"{key}: ${value:.2f}")
            elif isinstance(value, float) and key.lower().find('pnl') != -1:
                self.logger.info(f"{key}: ${value:.2f}")
            elif isinstance(value, float):
                self.logger.info(f"{key}: {value:.4f}")
            else:
                self.logger.info(f"{key}: {value}")
        self.logger.info("=" * 35)
    
    def cleanup_old_logs(self, days_to_keep: int = 30):
        """
        Clean up old log files.
        
        Args:
            days_to_keep: Number of days of logs to keep
        """
        try:
            from datetime import timedelta
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            
            for filename in os.listdir(self.log_dir):
                if filename.endswith('.log'):
                    file_path = os.path.join(self.log_dir, filename)
                    file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                    
                    if file_time < cutoff_date:
                        os.remove(file_path)
                        self.logger.info(f"Removed old log file: {filename}")
                        
        except Exception as e:
            self.logger.error(f"Error cleaning up old logs: {e}")


def setup_logging(config: dict) -> BotLogger:
    """
    Setup enhanced logging based on configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        BotLogger instance
    """
    log_config = config.get("logging", {})
    
    bot_logger = BotLogger(
        name="NASDAQBot",
        log_dir=log_config.get("log_dir", "logs"),
        log_level=log_config.get("level", "INFO"),
        max_file_size=log_config.get("max_file_size", 10485760),
        backup_count=log_config.get("backup_count", 5)
    )
    
    # Set initial context
    bot_logger.set_trading_context(
        symbol=config.get("trading", {}).get("symbol", "MNQ"),
        session=datetime.now().strftime("%Y%m%d")
    )
    
    return bot_logger


def get_module_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.
    
    Args:
        name: Module name
        
    Returns:
        Logger instance
    """
    return logging.getLogger(f"NASDAQBot.{name}")


# Convenience functions for common log patterns
def log_trade_entry(logger: logging.Logger, symbol: str, side: str, quantity: int, 
                   price: float, order_id: str = None):
    """Log trade entry."""
    order_info = f" (Order: {order_id})" if order_id else ""
    logger.info(f"🔵 ENTRY: {side.upper()} {quantity} {symbol} @ ${price:.2f}{order_info}")


def log_trade_exit(logger: logging.Logger, symbol: str, side: str, quantity: int,
                  entry_price: float, exit_price: float, pnl: float):
    """Log trade exit."""
    pnl_symbol = "🟢" if pnl >= 0 else "🔴"
    logger.info(f"{pnl_symbol} EXIT: {side.upper()} {quantity} {symbol} "
               f"${entry_price:.2f} → ${exit_price:.2f} | P/L: ${pnl:.2f}")


def log_opening_range(logger: logging.Logger, symbol: str, high: float, low: float):
    """Log opening range."""
    range_size = high - low
    logger.info(f"📊 OPENING RANGE: {symbol} ${low:.2f} - ${high:.2f} "
               f"(Range: {range_size:.2f} points)")


def log_breakout_levels(logger: logging.Logger, symbol: str, long_entry: float, 
                       short_entry: float):
    """Log breakout levels."""
    logger.info(f"🎯 BREAKOUT LEVELS: {symbol} Long @ ${long_entry:.2f} | "
               f"Short @ ${short_entry:.2f}")


def log_risk_check(logger: logging.Logger, can_trade: bool, reason: str = None):
    """Log risk check result."""
    if can_trade:
        logger.info("✅ RISK CHECK: Passed - Ready to trade")
    else:
        logger.warning(f"❌ RISK CHECK: Failed - {reason or 'Risk limits exceeded'}")


def log_session_start(logger: logging.Logger, symbol: str, account_equity: float):
    """Log session start."""
    logger.info("=" * 50)
    logger.info(f"🚀 TRADING SESSION STARTED")
    logger.info(f"📈 Symbol: {symbol}")
    logger.info(f"💰 Account Equity: ${account_equity:.2f}")
    logger.info(f"🕐 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 50)


def log_session_end(logger: logging.Logger, summary: dict):
    """Log session end."""
    logger.info("=" * 50)
    logger.info("🏁 TRADING SESSION ENDED")
    for key, value in summary.items():
        logger.info(f"📊 {key}: {value}")
    logger.info("=" * 50)
