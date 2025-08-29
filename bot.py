#!/usr/bin/env python3
"""
NASDAQ Breakout Bot - Main Script
Orchestrates the opening range breakout trading strategy.
"""

import logging
import json
import os
import time
import signal
import sys
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import pytz


from modules.alpaca_api import AlpacaAPI, AlpacaAPIError
from modules.data_fetcher import DataFetcher, DataFetcherError
from modules.risk_manager import RiskManager, RiskLimitExceeded
from modules.order_manager import OrderManager, OrderManagerError
from modules.opening_range_breakout import OpeningRangeBreakout, StrategyConfig
from modules.logger import (setup_logging, log_trade_entry, log_trade_exit, 
                           log_opening_range, log_breakout_levels, log_risk_check,
                           log_session_start, log_session_end)


class NASDAQBreakoutBot:
    """Main bot class orchestrating the opening range breakout strategy."""
    
    def __init__(self, config_file: str = "config.json"):
        """Initialize the bot with configuration."""
        self.config = self.load_config(config_file)
        
        # Setup enhanced logging
        self.bot_logger = setup_logging(self.config)
        self.logger = self.bot_logger.get_logger("Main")
        
        # Market timezone
        self.market_tz = pytz.timezone('US/Eastern')
        
        # Initialize components
        self.api = None
        self.data_fetcher = None
        self.risk_manager = None
        self.order_manager = None
        self.strategy = None
        
        # Bot state
        self.running = True
        self.trading_complete = False
        
        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        self.logger.info("NASDAQ Breakout Bot initialized")
    
    def load_config(self, config_file: str) -> Dict[str, Any]:
        """Load configuration from file."""
        # Default configuration
        config = {
            "alpaca": {
                "paper_trading": True
            },
            "trading": {
                "symbol": "QQQ",
                "breakout_offset_points": 15.0,
                "stop_loss_points": 25.0,
                "risk_reward_ratio": 2.0,
                "max_daily_loss_percent": 0.02,
                "max_trades_per_day": 2,
                "default_risk_percent": 0.005
            },
            "logging": {
                "level": "INFO",
                "file": "logs/nasdaq_bot.log"
            }
        }
        
        # Load from config file
        if not os.path.exists(config_file):
            raise ValueError(f"Config file {config_file} not found")
        
        try:
            with open(config_file, 'r') as f:
                file_config = json.load(f)
                # Merge configurations (file overrides defaults)
                for section, values in file_config.items():
                    if section in config:
                        config[section].update(values)
                    else:
                        config[section] = values
        except Exception as e:
            raise ValueError(f"Could not load config file {config_file}: {e}")
        
        # Set API keys based on paper trading mode
        if "alpaca_api_keys" not in config:
            raise ValueError("alpaca_api_keys section not found in config")
        
        if config["alpaca"]["paper_trading"]:
            config["alpaca"]["api_key"] = config["alpaca_api_keys"]["paper_api_key"]
            config["alpaca"]["secret_key"] = config["alpaca_api_keys"]["paper_api_secret"]
        else:
            config["alpaca"]["api_key"] = config["alpaca_api_keys"]["api_key"]
            config["alpaca"]["secret_key"] = config["alpaca_api_keys"]["api_secret"]
        
        # Validate required API keys
        if not config["alpaca"]["api_key"] or not config["alpaca"]["secret_key"]:
            raise ValueError("Alpaca API keys not found in config file")
        
        return config
    

    
    def initialize_components(self) -> None:
        """Initialize all bot components."""
        try:
            # Initialize Alpaca API
            self.api = AlpacaAPI(
                api_key=self.config["alpaca"]["api_key"],
                secret_key=self.config["alpaca"]["secret_key"],
                paper_trading=self.config["alpaca"]["paper_trading"]
            )
            
            # Initialize data fetcher
            self.data_fetcher = DataFetcher(self.api)
            
            # Initialize risk manager
            self.risk_manager = RiskManager(
                max_daily_loss_percent=self.config["trading"]["max_daily_loss_percent"],
                max_trades_per_day=self.config["trading"]["max_trades_per_day"],
                default_risk_percent=self.config["trading"]["default_risk_percent"]
            )
            
            # Initialize order manager
            self.order_manager = OrderManager(self.api, self.risk_manager)
            
            # Initialize strategy
            strategy_config = StrategyConfig(
                breakout_offset_points=self.config["trading"]["breakout_offset_points"],
                stop_loss_points=self.config["trading"]["stop_loss_points"],
                risk_reward_ratio=self.config["trading"]["risk_reward_ratio"]
            )
            self.strategy = OpeningRangeBreakout(strategy_config)
            
            self.logger.info("All components initialized successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize components: {e}")
            raise
    
    def wait_for_market_open_plus_15(self) -> datetime:
        """Wait until 15 minutes after market open."""
        now = datetime.now(self.market_tz)
        
        # Calculate market open time (9:30 AM ET)
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        
        # If it's past market open today, use tomorrow
        if now > market_open:
            market_open += timedelta(days=1)
        
        # Wait until 15 minutes after market open
        target_time = market_open + timedelta(minutes=15)
        
        if now < target_time:
            wait_seconds = (target_time - now).total_seconds()
            self.logger.info(f"Waiting {wait_seconds:.0f} seconds until opening range completes at {target_time}")
            
            while now < target_time and self.running:
                time.sleep(min(60, wait_seconds))  # Check every minute
                now = datetime.now(self.market_tz)
                wait_seconds = (target_time - now).total_seconds()
        
        return target_time
    
    def execute_trading_strategy(self) -> bool:
        """Execute the main trading strategy. Returns True if trading completed successfully."""
        try:
            symbol = self.config["trading"]["symbol"]
            
            # Check if market is open
            if not self.data_fetcher.is_market_open():
                self.logger.warning("Market is not open. Skipping trading.")
                return False
            
            # Get account information
            account_info = self.api.get_account_info()
            account_equity = account_info["equity"]
            
            # Log session start
            log_session_start(self.logger, symbol, account_equity)
            
            # Check if we can trade today
            can_trade = self.risk_manager.can_trade(account_equity)
            log_risk_check(self.logger, can_trade, 
                          "Daily limits reached" if not can_trade else None)
            
            if not can_trade:
                return True
            
            # Get opening range
            self.logger.info(f"🔍 Fetching opening range for {symbol}")
            opening_high, opening_low = self.data_fetcher.get_opening_range(symbol)
            
            # Log opening range
            log_opening_range(self.logger, symbol, opening_high, opening_low)
            
            # Calculate breakout levels using strategy
            breakout_levels = self.strategy.calculate_breakout_levels(opening_high, opening_low)
            
            # Log breakout levels
            log_breakout_levels(self.logger, symbol, breakout_levels.long_entry, 
                              breakout_levels.short_entry)
            
            # Validate trade conditions
            if not self.strategy.should_take_trade(breakout_levels):
                self.logger.warning("⚠️ Strategy conditions not met. Skipping trade.")
                return False
            
            # Calculate stop loss and take profit distances
            stop_loss_points = self.strategy.get_stop_loss_points(breakout_levels.range_size)
            take_profit_points = self.strategy.get_take_profit_points(stop_loss_points)
            
            # Place breakout orders
            breakout_orders = self.order_manager.place_breakout_orders(
                symbol=symbol,
                long_entry=breakout_levels.long_entry,
                short_entry=breakout_levels.short_entry,
                stop_loss_points=stop_loss_points,
                take_profit_points=take_profit_points,
                account_equity=account_equity
            )
            
            self.logger.info(f"Breakout orders placed successfully for {symbol}")
            
            # Monitor orders until filled or end of day
            self.monitor_trading_session(symbol)
            
            return True
            
        except (DataFetcherError, OrderManagerError, AlpacaAPIError) as e:
            self.logger.error(f"Trading strategy error: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error in trading strategy: {e}")
            return False
    
    def monitor_trading_session(self, symbol: str) -> None:
        """Monitor the trading session until completion."""
        session_end = datetime.now(self.market_tz).replace(hour=15, minute=30, second=0, microsecond=0)
        
        self.logger.info("Monitoring trading session...")
        
        while self.running and datetime.now(self.market_tz) < session_end:
            try:
                # Check if we have any active orders
                if not self.order_manager.has_active_orders(symbol):
                    self.logger.info("No active orders remaining. Trading session complete.")
                    break
                
                # Check if daily limits reached
                account_info = self.api.get_account_info()
                if not self.risk_manager.can_trade(account_info["equity"]):
                    self.logger.info("Daily limits reached. Cancelling remaining orders.")
                    self.order_manager.cancel_all_pending(symbol)
                    break
                
                # Sleep before next check
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Error monitoring trading session: {e}")
                time.sleep(60)  # Wait longer on error
        
        # End of session cleanup
        if self.order_manager.has_active_orders(symbol):
            self.logger.info("End of trading session. Cancelling remaining orders.")
            self.order_manager.cancel_all_pending(symbol)
    
    def run(self) -> None:
        """Main bot execution loop."""
        try:
            self.logger.info("Starting NASDAQ Breakout Bot")
            
            # Initialize all components
            self.initialize_components()
            
            # Prepare strategy for the day
            strategy_prep = self.strategy.prepare_day()
            if not strategy_prep.get("ready", False):
                self.logger.error("Strategy preparation failed")
                return
            
            # Log daily statistics
            daily_stats = self.risk_manager.get_daily_stats()
            self.logger.info(f"Daily stats: {daily_stats}")
            
            # Wait for opening range completion
            if self.running:
                self.wait_for_market_open_plus_15()
            
            # Execute trading strategy
            if self.running:
                success = self.execute_trading_strategy()
                if success:
                    self.logger.info("Trading strategy completed successfully")
                else:
                    self.logger.warning("Trading strategy completed with errors")
            
            # Final statistics
            final_stats = self.risk_manager.get_daily_stats()
            executed_trades = self.order_manager.get_executed_trades()
            
            # Create session summary
            session_summary = {
                "Daily P/L": f"${final_stats.get('daily_pnl', 0):.2f}",
                "Trades Executed": f"{len(executed_trades)}/{final_stats.get('max_trades_per_day', 2)}",
                "Account Equity": f"${final_stats.get('daily_pnl', 0) + (executed_trades[0].entry_price * executed_trades[0].quantity if executed_trades else 0):.2f}" if executed_trades else "N/A",
                "Strategy": "Opening Range Breakout",
                "Symbol": self.config["trading"]["symbol"]
            }
            
            # Log session end
            log_session_end(self.logger, session_summary)
            
            # Log individual trades
            for trade in executed_trades:
                self.logger.info(f"📋 Trade Summary: {trade.side.upper()} {trade.symbol} "
                               f"{trade.quantity}@${trade.entry_price:.2f}")
            
            # Log performance metrics
            if executed_trades:
                self.bot_logger.log_performance_metrics(final_stats)
            
        except KeyboardInterrupt:
            self.logger.info("Bot interrupted by user")
        except Exception as e:
            self.logger.error(f"Fatal error in bot execution: {e}")
        finally:
            self.cleanup()
            # Cleanup old logs
            self.bot_logger.cleanup_old_logs(days_to_keep=30)
    
    def cleanup(self) -> None:
        """Cleanup resources and shutdown gracefully."""
        try:
            self.logger.info("Shutting down bot...")
            
            if self.order_manager:
                self.order_manager.cleanup()
            
            self.logger.info("Bot shutdown complete")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    def signal_handler(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        self.logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
        self.running = False
    
    def get_status(self) -> Dict[str, Any]:
        """Get current bot status."""
        status = {
            "running": self.running,
            "trading_complete": self.trading_complete,
            "timestamp": datetime.now().isoformat()
        }
        
        if self.risk_manager:
            status["daily_stats"] = self.risk_manager.get_daily_stats()
        
        if self.order_manager:
            status["active_orders"] = len(self.order_manager.get_active_orders())
            status["executed_trades"] = len(self.order_manager.get_executed_trades())
        
        return status


def main():
    """Main entry point."""
    try:
        # Create and run bot
        bot = NASDAQBreakoutBot()
        bot.run()
        
    except Exception as e:
        print(f"Failed to start bot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
