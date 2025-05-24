from head import *
# ------------- Data Retrieval -------------
from alpaca.data.live.stock import StockDataStream
from alpaca.data.live.crypto import CryptoDataStream
from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.requests import (
    StockBarsRequest, StockQuotesRequest, StockTradesRequest,
    CryptoBarsRequest, CryptoQuoteRequest, CryptoTradesRequest
)
# -------------- Trading Execution ----------
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
# -------------- Common Utilities -------------
from alpaca.common.exceptions import APIError
from alpaca.common.rest import RESTClient


class StreamType(Enum):
    """Enum for different stream types"""
    CRYPTO = "crypto"
    STOCK = "stock"


class DataType(Enum):
    """Enum for different data types"""
    BARS = "bars"
    QUOTES = "quotes" 
    TRADES = "trades"


@dataclass
class StreamConfig:
    """Configuration for streaming"""
    symbols: List[str]
    data_type: DataType
    stream_type: StreamType


class Client:
    """Base client for Alpaca API operations"""
    
    def __init__(self, config: Dict[str, Union[str, bool]]):
        self.config = config
        self.trading_client = TradingClient(
            api_key=config["API_KEY"], 
            secret_key=config["SECRET_KEY"], 
            paper=config["paper"]
        )
        self.active_streams: List[asyncio.Task] = []
        self.new_data = None

    def _create_historical_client(self, stream_type: StreamType) -> Optional[Union[CryptoHistoricalDataClient, StockHistoricalDataClient]]:
        """Factory method to create historical data clients"""
        try:
            clients = {
                StreamType.CRYPTO: CryptoHistoricalDataClient,
                StreamType.STOCK: StockHistoricalDataClient
            }
            return clients[stream_type](self.config["API_KEY"], self.config["SECRET_KEY"])
        except APIError as e:
            print(f"[!] Error creating {stream_type.value} historical client: {e}")
            return None

    def _create_stream_client(self, stream_type: StreamType) -> Optional[Union[CryptoDataStream, StockDataStream]]:
        """Factory method to create stream clients"""
        try:
            clients = {
                StreamType.CRYPTO: CryptoDataStream,
                StreamType.STOCK: StockDataStream
            }
            return clients[stream_type](self.config["API_KEY"], self.config["SECRET_KEY"])
        except APIError as e:
            print(f"[!] Error creating {stream_type.value} stream client: {e}")
            return None

    def _create_timeframe(self, interval: Dict) -> Optional[TimeFrame]:
        """Create TimeFrame from interval configuration"""
        try:
            step = interval["step"]
            if step["day"] > 0:
                return TimeFrame(step["day"], TimeFrameUnit.Day)
            elif step["hour"] > 0:
                return TimeFrame(step["hour"], TimeFrameUnit.Hour)
            else:
                return TimeFrame(step["minute"], TimeFrameUnit.Minute)
        except (KeyError, APIError) as e:
            print(f"[!] Error creating timeframe: {e}")
            return None

    def _calculate_start_time(self, interval: Dict, timezone: str) -> Optional[datetime]:
        """Calculate start time from interval configuration"""
        try:
            range_config = interval["range"]
            return datetime.now(ZoneInfo(timezone)) - timedelta(
                days=range_config["day"],
                hours=range_config["hour"], 
                minutes=range_config["minute"]
            )
        except (KeyError, APIError) as e:
            print(f"[!] Error calculating start time: {e}")
            return None

    async def on_update(self, data) -> None:
        """Handle incoming stream data"""
        self.new_data = data
        print(f"[o] {data.symbol}")
        print(f"    ├── {data.timestamp}: ${data.close}")

    def get_stream_status(self) -> str:
        """Get current stream status and clean up finished tasks"""
        self.active_streams = [task for task in self.active_streams if not task.done()]
        active_count = len(self.active_streams)

        if active_count == 0:
            return "No active streams"
        else:
            return f"{active_count} streams running"

    async def stop_streams(self) -> None:
        """Stop all active streams with complete cleanup"""
        self.get_stream_status()
        
        if not self.active_streams:
            print("[!] No active streams to stop")
            return
        # Cancel all tasks
        for task in self.active_streams:
            if not task.done():
                task.cancel()

        # Wait for cancellation
        if self.active_streams:
            try:
                await asyncio.gather(*self.active_streams, return_exceptions=True)
            except Exception:
                pass

        self.active_streams.clear()
        print("[o] Streams stopped")

    async def _cleanup_stream(self, stream) -> None:
        """Clean up stream resources"""
        try:
            if hasattr(stream, '_ws') and stream._ws:
                await stream._ws.close()
            if hasattr(stream, 'close'):
                await stream.close()
            del stream
        except Exception as e:
            print(f"[!] Cleanup warning: {e}")

    def create_order(self, symbol: str, qty: int, side: OrderSide, 
                    order_type: OrderType, time_in_force: TimeInForce) -> Optional[Order]:
        """Create and submit an order"""
        try:
            return self.trading_client.submit_order(
                symbol=symbol, qty=qty, side=side, 
                type=order_type, time_in_force=time_in_force
            )
        except APIError as e:
            print(f"[!] Order error: {e}")
            return None

    def get_positions(self) -> None:
        """Display current positions"""
        print("\n[+] Positions")
        try:
            positions = self.trading_client.get_all_positions()
            if positions:
                for pos in positions:
                    print(f"    ├── {pos.symbol}: {pos.qty} shares, Value: ${float(pos.market_value):,.2f}")
            else:
                print("    ├── No positions")
        except APIError as e:
            print(f"[!] Error getting positions: {e}")

    def get_orders(self) -> None:
        """Display current orders"""
        print("\n[+] Orders")
        try:
            orders = self.trading_client.get_orders()
            if orders:
                for order in orders:
                    print(f"    ├── {order.symbol}: {order.qty} shares")
            else:
                print("    ├── No orders")
        except APIError as e:
            print(f"[!] Error getting orders: {e}")

    def display_info(self) -> None:
        """Display client information"""
        print(f"\n[+] Client")
        print(f"    ├── API Key: {self.config['API_KEY']}")
        print(f"    ├── Paper: {self.config['paper']}")
        print(f"    └── Balance: ${self.trading_client.get_account().cash}")


class Account(Client):
    """Extended client with account-specific functionality"""
    
    def __init__(self, config: Dict[str, Union[str, bool]], name: str):
        super().__init__(config)
        self.info = {
            "name": name,
            "zone": str(get_localzone())
        }
        self.focused = {"crypto": [], "stock": []}

    def focus(self, symbols: Union[str, List[str]]) -> Optional[Dict]:
        """Focus on specific symbols for trading/streaming"""
        print("\n[o] Focus: ", end="")
        if isinstance(symbols, str):
            symbols = [symbols]
            
        for symbol in symbols:
            try:
                clean_symbol = symbol.replace('/', '')
                asset = self.trading_client.get_asset(symbol_or_asset_id=clean_symbol)
                if asset.asset_class == AssetClass.CRYPTO:
                    self.focused["crypto"].append(asset.symbol)
                else:
                    self.focused["stock"].append(asset.symbol)
            except APIError as e:
                print(f"\n[!] Error focusing on {symbol}: {e}")
                continue
                
        print(f"{self.focused}")
        return self.focused if any(self.focused.values()) else None

    def buy(self, symbol: str, qty: int, time_in_force: TimeInForce) -> Optional[Order]:
        """Place a buy order"""
        return self.create_order(symbol, qty, OrderSide.BUY, OrderType.MARKET, time_in_force)

    def sell(self, symbol: str, qty: int, time_in_force: TimeInForce) -> Optional[Order]:
        """Place a sell order"""
        return self.create_order(symbol, qty, OrderSide.SELL, OrderType.MARKET, time_in_force)

    def _get_history_data(self, stream_type: StreamType, data_type: str, interval: Dict) -> Optional[pd.DataFrame]:
        """Get historical data for specified type"""
        symbols = self.focused[stream_type.value]
        if not symbols:
            return None

        client = self._create_historical_client(stream_type)
        if not client:
            return None

        try:
            timeframe = self._create_timeframe(interval)
            start_time = self._calculate_start_time(interval, self.info["zone"])
            
            # Create appropriate request based on stream type and data type
            request_map = {
                StreamType.CRYPTO: {
                    "bars": CryptoBarsRequest,
                    "quotes": CryptoQuoteRequest,
                    "trades": CryptoTradesRequest
                },
                StreamType.STOCK: {
                    "bars": StockBarsRequest,
                    "quotes": StockQuotesRequest,
                    "trades": StockTradesRequest
                }
            }
            
            request_class = request_map[stream_type][data_type]
            request = request_class(
                symbol_or_symbols=symbols,
                timeframe=timeframe,
                start=start_time
            )
            
            # Get data using appropriate method
            method_name = f"get_{stream_type.value}_{data_type}"
            data = getattr(client, method_name)(request)
            return data.df if data and not data.df.empty else pd.DataFrame()
            
        except Exception as e:
            print(f"[!] Error getting {stream_type.value} history: {e}")
            return None

    def crypto_history(self, data_type: str, interval: Dict) -> Optional[pd.DataFrame]:
        """Get crypto historical data"""
        return self._get_history_data(StreamType.CRYPTO, data_type, interval)

    def stock_history(self, data_type: str, interval: Dict) -> Optional[pd.DataFrame]:
        """Get stock historical data"""
        return self._get_history_data(StreamType.STOCK, data_type, interval)

    async def _create_stream_task(self, stream_config: StreamConfig) -> bool:
        """Create and manage a stream task"""
        stream = self._create_stream_client(stream_config.stream_type)
        if not stream:
            return False

        async def _stream_task():
            try:
                stream._subscribe(
                    handler=self.on_update,
                    symbols=stream_config.symbols,
                    handlers=stream._handlers[stream_config.data_type.value],
                )
                await stream._run_forever()
                return True
            except ValueError as e:
                error_msg = ("[!] API connection limit reached. Wait 30+ seconds." 
                           if "connection limit exceeded" in str(e) 
                           else f"[!] {stream_config.stream_type.value.title()} stream error: {e}")
                print(error_msg)
                return False
            except Exception as e:
                print(f"[!] {stream_config.stream_type.value.title()} stream error: {e}")
                return False
            finally:
                await self._cleanup_stream(stream)

        task = asyncio.create_task(_stream_task())
        self.active_streams.append(task)
        return True

    async def crypto_stream(self, data_type: str, symbols: List[str]) -> bool:
        """Start crypto streaming"""
        if not symbols:
            return False
        
        config = StreamConfig(symbols, DataType(data_type), StreamType.CRYPTO)
        return await self._create_stream_task(config)

    async def stock_stream(self, data_type: str, symbols: List[str]) -> bool:
        """Start stock streaming"""
        if not symbols:
            return False
            
        config = StreamConfig(symbols, DataType(data_type), StreamType.STOCK)
        return await self._create_stream_task(config)

    async def stop_stream(self) -> None:
        """Stop streams and show which symbols are being stopped"""
        if not self.active_streams:
            print("[!] No active streams to stop")
            return

        symbols_to_stop = self.focused["crypto"] + self.focused["stock"]
        print(f"[+] Stopping all streams: {', '.join(symbols_to_stop)}")
        await self.stop_streams()

    def account_info(self) -> None:
        """Display account information"""
        print(f"\n[+] Profile")
        print(f"    ├── Name: {self.info['name']}")
        print(f"    └── Zone: {self.info['zone']}")
        self.display_info()
        
