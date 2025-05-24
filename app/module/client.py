from head import *
# ------------- Data Retrival-------------
# Stream Clients
from alpaca.data.live.stock import StockDataStream
from alpaca.data.live.crypto import CryptoDataStream

# Historical Clients
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.historical.crypto import CryptoHistoricalDataClient

# Data Requests and Timeframes
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.requests import (
    StockBarsRequest, StockQuotesRequest, StockTradesRequest,
    CryptoBarsRequest, CryptoQuoteRequest, CryptoTradesRequest
)
#-------------- Trading Execution ----------
# Trading Clients and Streams
from alpaca.trading.client import TradingClient
from alpaca.trading.stream import TradingStream
from alpaca.trading.models import Order
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest,
    StopLimitOrderRequest, TrailingStopOrderRequest
)
from alpaca.trading.enums import (
    OrderSide, TimeInForce, OrderStatus, OrderType,
    AssetClass, AssetStatus, AssetExchange
)
#-------------- Common Utilities -------------
from alpaca.common.exceptions import APIError
from alpaca.common.rest import RESTClient


class Client: 
    config : dict = {
        "API_KEY" : str,
        "SECRET_KEY" : str,
        "paper" : bool,
    }
    TradingClient = None
    new_data = None
    active_stream : list[asyncio.Task]  # Store actual stream objects for complete deletion

    def __init__(self, config: dict):
        self.config = config
        self.TradingClient = TradingClient(
            api_key=self.config["API_KEY"], 
            secret_key=self.config["SECRET_KEY"], 
            paper=self.config["paper"]
        )
        self.active_stream = []
    
    def order(self, symbol: str, qty: int, side: OrderSide, type: OrderType, time_in_force: TimeInForce) -> tp.Union[Order, None]:
        try:
            order = self.TradingClient.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type=type,
                time_in_force=time_in_force
            )
            return order
        except APIError as e:
            print(f"\n[!] Error → order(): {str(e)}")
            return None
    
    def history_step(self, interval: dict) -> tp.Union[CryptoHistoricalDataClient, StockHistoricalDataClient, None]:
        try:
            if interval["step"]["day"] > 0:
                timeframe = TimeFrame(interval["step"]["day"], TimeFrameUnit.Day)
            elif interval["step"]["hour"] > 0:
                timeframe = TimeFrame(interval["step"]["hour"], TimeFrameUnit.Hour)
            else:
                timeframe = TimeFrame(interval["step"]["minute"], TimeFrameUnit.Minute)
            return timeframe
        except APIError as e:
            print(f"\n[!] Error → history_step(): {str(e)}")
            return None
    
    def history_range(self, interval: dict) -> tp.Union[CryptoHistoricalDataClient, StockHistoricalDataClient, None]:
        try:
            start_time = datetime.now(ZoneInfo(self.info["zone"])) - timedelta(
                days=interval["range"]["day"],
                hours=interval["range"]["hour"],
                minutes=interval["range"]["minute"]
            )
            return start_time
        except APIError as e:
            print(f"\n[!] Error → history_range(): {str(e)}")
            return None
                
    def history(self, currency: str) -> tp.Union[CryptoHistoricalDataClient, StockHistoricalDataClient, None]:
        try:
            if currency.lower() == "crypto":
                return CryptoHistoricalDataClient(self.config["API_KEY"], self.config["SECRET_KEY"])
            elif currency.lower() == "stock":
                return StockHistoricalDataClient(self.config["API_KEY"], self.config["SECRET_KEY"])
        except APIError as e:
            print(f"\n[!] Error -> history(): {str(e)}")
            return None

    def stream(self, currency: str) -> tp.Union[CryptoDataStream, StockDataStream, None]:
        try:
            if currency.lower() == "crypto":
                return CryptoDataStream(self.config["API_KEY"], self.config["SECRET_KEY"])
            elif currency.lower() == "stock":
                return StockDataStream(self.config["API_KEY"], self.config["SECRET_KEY"])
        except APIError as e:
            print(f"\n[!] Error -> stream(): {str(e)}")
            return None
    
    async def on_update(self, data) -> None:
        self.new_data = data
        print(f"[o] {data.symbol}")
        print(f"    ├── {data.timestamp}: ${data.close}")

    def get_stream_status(self):
        """Get current stream status and clean up finished tasks"""
        # Remove completed/cancelled tasks
        self.active_stream = [task for task in self.active_stream if not task.done()]
        
        active_count = len(self.active_stream)
        if active_count == 0:
            return "No active streams"
        else:
            return f"{active_count} streams running"
    
    async def stream_stop(self):
        """Stop all active streams with complete object cleanup"""
        # Clean up finished tasks first
        self.get_stream_status()
        
        if not self.active_stream:
            print("[!] No active streams to stop")
            return
        
        # Show which symbols are being stopped
        symbols_to_stop = []
        if self.focused["crypto"]:
            symbols_to_stop.extend(self.focused["crypto"])
        if self.focused["stock"]:
            symbols_to_stop.extend(self.focused["stock"])
        
        print(f"[+] Stopping all streams: {', '.join(symbols_to_stop)}")
        
        # Cancel all active stream tasks
        cancelled_tasks = []
        for task in self.active_stream:
            if not task.done():
                task.cancel()
                cancelled_tasks.append(task)
        
        # Wait for all tasks to be cancelled properly
        if cancelled_tasks:
            try:
                await asyncio.gather(*cancelled_tasks, return_exceptions=True)
            except Exception:
                pass  # Expected for cancelled tasks
        
        # Clear the list
        self.active_stream.clear()
        
        print("[o] Streams stopped")
    async def stream_cleanup(self, stream):
        """Completely cleanup and delete stream object"""
        try:
            if hasattr(stream, '_ws') and stream._ws:
                await stream._ws.close()
            if hasattr(stream, 'close'):
                await stream.close()
            # Force garbage collection
            del stream
        except Exception as e:
            print(f"[!] Cleanup warning: {e}")
            
    def position_info(self):
        print(f"\n[+] Positions")
        try:
            if self.TradingClient.get_all_positions():
                for position in self.TradingClient.get_all_positions():     
                    print(f"    ├── {position.symbol}: {position.qty} shares, Value: ${float(position.market_value):,.2f}")
            else:
                print(f"    ├── No positions")
        except APIError as e:
            print(f"\n[!] Error → position_info(): {str(e)}")
            return None
    
    def order_info(self):
        print(f"\n[+] Orders")
        try:
            if self.TradingClient.get_orders():
                for order in self.TradingClient.get_orders():
                    print(f"    ├── {order.symbol}: {order.qty} shares, Value: ${float(order.market_value):,.2f}")
            else:
                print(f"    ├── No orders")
        except APIError as e:
            print(f"\n[!] Error → order_info(): {str(e)}")
            return None

    def Client_info(self):
        print(f"\n[+] Client")
        print(f"    ├── API Key: {self.config['API_KEY']}")
        print(f"    ├── Paper: {self.config['paper']}")
        print(f"    └── Balance: ${self.TradingClient.get_account().cash}")

class Account(Client):
    info : dict = {
        "name" : str,
        "zone" : str,
    }

    positions : pd.DataFrame
    orders : pd.DataFrame

    focused : dict = {
        "crypto" : [],
        "stock" : [],
    }

    def __init__(self, config: dict, name: str):
        super().__init__(config)
        self.info = {
            "name" : name,
            "zone" : str(get_localzone())
        }
        self.focused = {
            "crypto": [],
            "stock": []
        }

    def focus(self, symbols: tp.Union[str, tp.List[str]]) -> tp.Union[dict, None]:
        print(f"\n[o] Focus: ", end="")
        if isinstance(symbols, str):
            symbols = [symbols]
            
        for symbol in symbols:
            try:
                clean_symbol = symbol.replace('/', '')
                asset = self.TradingClient.get_asset(symbol_or_asset_id=clean_symbol)
                if asset.asset_class == AssetClass.CRYPTO:
                    self.focused["crypto"].append(asset.symbol)
                else:
                    self.focused["stock"].append(asset.symbol)
            except APIError as e:
                print(f"\n[!] Error → focus(): {str(e)}")
                continue
                
        print(f"{self.focused}")
        return self.focused if (self.focused["crypto"] or self.focused["stock"]) else None
    
    def buy(self, symbol: str, qty: int, time_in_force: TimeInForce) -> tp.Union[Order, None]:
        return self.order(symbol, qty, OrderSide.BUY, OrderType.MARKET, time_in_force)
    
    def sell(self, symbol: str, qty: int, time_in_force: TimeInForce) -> tp.Union[Order, None]:
        return self.order(symbol, qty, OrderSide.SELL, OrderType.MARKET, time_in_force)
    
    def crypto_history(self, type: str, interval: dict) -> tp.Union[pd.DataFrame, None]:
        """Get historical crypto data"""
        if not self.focused["crypto"]:
            return None
            
        history = self.history("crypto")
        if not history:
            return None
            
        try:
            timeframe = self.history_step(interval)
            start_time = self.history_range(interval)
            if type == "bars":
                request = CryptoBarsRequest(
                    symbol_or_symbols=self.focused["crypto"],
                    timeframe=timeframe,
                    start=start_time
                )
            elif type == "quotes":
                request = CryptoQuoteRequest(
                    symbol_or_symbols=self.focused["crypto"],
                    timeframe=timeframe,
                    start=start_time
                )
            elif type == "trades":
                request = CryptoTradesRequest(
                    symbol_or_symbols=self.focused["crypto"],
                    timeframe=timeframe,
                    start=start_time
                )
            data = history.get_crypto_bars(request)
            return data.df if data and not data.df.empty else pd.DataFrame()
            
        except Exception as e:
            print(f"[!] Error getting crypto history: {e}")
            return None

    def stock_history(self, type: str, interval: dict) -> tp.Union[pd.DataFrame, None]:
        """Get historical stock data"""
        if not self.focused["stock"]:
            return None
            
        history = self.history("stock")
        if not history:
            return None
            
        try:
            timeframe = self.history_step(interval)
            start_time = self.history_range(interval)
            if type == "bars":
                request = StockBarsRequest(
                    symbol_or_symbols=self.focused["stock"],
                    timeframe=timeframe,
                    start=start_time
                )
            elif type == "quotes":
                request = StockQuoteRequest(
                    symbol_or_symbols=self.focused["stock"],
                    timeframe=timeframe,
                    start=start_time
                )
            elif type == "trades":
                request = StockTradesRequest(
                    symbol_or_symbols=self.focused["stock"],
                    timeframe=timeframe,
                    start=start_time
                )
            data = history.get_stock_bars(request)
            return data.df if data and not data.df.empty else pd.DataFrame()
            
        except Exception as e:
            print(f"[!] Error getting stock history: {e}")
            return None

    
    async def crypto_stream(self, type: str, crypto_symbols: list) -> bool:
        """Simple crypto streaming with complete object cleanup"""
        if not crypto_symbols:
            return False
            
        # Create a fresh stream object each time
        stream = self.stream("crypto")
        if not stream:
            return False
        
        # Store the stream object for complete deletion later
        stream._client_ref = self  # Add reference for cleanup
        
        async def _stream_task():
            try:
                stream._subscribe(
                    handler=self.on_update,
                    symbols=crypto_symbols,
                    handlers=stream._handlers[type],
                )
                await stream._run_forever()
                return True
            except ValueError as e:
                if "connection limit exceeded" in str(e):
                    print("[!] API connection limit reached. Wait 30+ seconds before trying again.")
                    return False
                else:
                    print(f"[!] Stream error: {e}")
                    return False
            except Exception as e:
                print(f"[!] Stream error: {e}")
                return False
            finally:
                # Always cleanup the stream object
                await self.stream_cleanup(stream)
        
        # Create and append task to active_stream list
        task = asyncio.create_task(_stream_task())
        self.active_stream.append(task)
        
        return True

    async def stock_stream(self, type: str, stock_symbols: list) -> bool:
        """Simple stock streaming with complete object cleanup"""
        if not stock_symbols:
            return False
            
        # Create a fresh stream object each time
        stream = self.stream("stock")
        if not stream:
            return False
        
        # Store the stream object for complete deletion later
        stream._client_ref = self  # Add reference for cleanup
        
        async def _stream_task():
            try:
                stream._subscribe(
                    handler=self.on_update,
                    symbols=stock_symbols,
                    handlers=stream._handlers[type],
                )
                await stream._run_forever()
                return True
            except ValueError as e:
                if "connection limit exceeded" in str(e):
                    print("[!] Stock API connection limit reached. Wait 30+ seconds before trying again.")
                    return False
                else:
                    print(f"[!] Stock stream error: {e}")
                    return False
            except Exception as e:
                print(f"[!] Stock stream error: {e}")
                return False
            finally:
                # Always cleanup the stream object
                await self.stream_cleanup(stream)
        
        # Create and append task to active_stream list
        task = asyncio.create_task(_stream_task())
        self.active_stream.append(task)
        
        return True

    def account_info(self):
        print (f"\n[+] Profile")
        print(f"    ├── Name: {self.info['name']}")
        print(f"    └── Zone: {self.info['zone']}")
        self.Client_info()
        
