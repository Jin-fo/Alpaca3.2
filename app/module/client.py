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

class CurrencyType(Enum):
    CRYPTO = "crypto"
    STOCK = "stock"

class DataType(Enum):
    BARS = "bars"
    QUOTES = "quotes"
    TRADES = "trades"
    
class Client:
    def __init__(self, config: Dict[str, Union[str, bool]]):
        self.config = config
        self.trading_client = TradingClient(
            api_key=config["API_KEY"],
            secret_key=config["SECRET_KEY"],
            paper=config["paper"]
        )
        self.active_stream: Dict[CurrencyType, asyncio.Task] = {}
        self.stream_clients: Dict[CurrencyType, Union[CryptoDataStream, StockDataStream]] = {}
        self.hist_data: Dict[CurrencyType, pd.DataFrame] = {}
        self.new_data: Dict[CurrencyType, pd.DataFrame] = {}
    
    def _historical_client(self, currency: CurrencyType) -> Optional[Union[CryptoHistoricalDataClient, StockHistoricalDataClient]]:
        try: 
            clients = {
                CurrencyType.CRYPTO: CryptoHistoricalDataClient,
                CurrencyType.STOCK: StockHistoricalDataClient
            }
            # Create client with timezone setting
            client = clients[currency](
                api_key=self.config["API_KEY"], 
                secret_key=self.config["SECRET_KEY"]
            )
            return client
        except APIError as e:
            print(f"[!] Error creating {currency.value} historical client: {e}")
            return None
    
    def _historical_request(self, currency: CurrencyType, data_type: DataType) -> Optional[type]:
        try:
            request_type = {
                CurrencyType.CRYPTO: {
                    DataType.BARS: CryptoBarsRequest,
                    DataType.QUOTES: CryptoQuoteRequest,
                    DataType.TRADES: CryptoTradesRequest
                },
                CurrencyType.STOCK: {
                    DataType.BARS: StockBarsRequest,
                    DataType.QUOTES: StockQuotesRequest,
                    DataType.TRADES: StockTradesRequest
                }
            }
            return request_type[currency][data_type]
        except APIError as e:
            print(f"[!] Error creating {currency.value} {data_type.value} request: {e}")
            return None
        
    def _stream_client(self, currency: CurrencyType) -> Optional[Union[CryptoDataStream, StockDataStream]]:
        try:
            clients = {
                CurrencyType.CRYPTO: CryptoDataStream,
                CurrencyType.STOCK: StockDataStream
            }
            return clients[currency](self.config["API_KEY"], self.config["SECRET_KEY"])
        except APIError as e:
            print(f"[!] Error creating {currency.value} stream client: {e}")
            return None
        
    def _stream_status(self) -> str:
        """Get current stream status with associated symbols (read-only)"""
        if not self.active_stream:
            return "No active streams"
        
        status_parts = []
        active_count = 0
        
        for currency, task in self.active_stream.items():
            if task and not task.done():
                symbols = self.focused.get(currency, [])
                symbol_list = ", ".join(symbols) if symbols else "none"
                status_parts.append(f"{currency.value}: {symbol_list}")
                active_count += 1
        
        if active_count == 0:
            return "No active streams"
        
        status_summary = f"{active_count} active stream(s)"
        if status_parts:
            status_detail = " | ".join(status_parts)
            return f"{status_summary} - {status_detail}"
        else:
            return status_summary
        
    async def _stream_update(self, data) -> None:
        try: 
            # Handle the incoming stream data
            symbol = getattr(data, 'symbol', 'unknown')
            timestamp = getattr(data, 'timestamp', datetime.now())
            
            # Store the new data
            self.new_data[symbol] = data
            print(f"[o] {symbol}: {data}")
        except Exception as e:
            print(f"[!] Error updating stream data: {e}")

    async def _stream_cleanup(self, stream) -> None:
        """Clean up stream resources"""
        if not stream:
            return
            
        try:
            # Close WebSocket and session
            if hasattr(stream, '_ws') and stream._ws and not stream._ws.closed:
                await stream._ws.close()
            if hasattr(stream, '_session') and stream._session and not stream._session.closed:
                await stream._session.close()
            
            # Close stream and clear handlers
            if hasattr(stream, 'close'):
                await stream.close()
            if hasattr(stream, '_handlers'):
                stream._handlers.clear()
                
        except Exception as e:
            print(f"[!] Cleanup warning: {e}")
        finally:
            import gc
            gc.collect()

class Account(Client):
    def __init__(self, config: Dict[str, Union[str, bool]], name: str):
        super().__init__(config)
        self.name = name
        self.info = {
            "name": name,
            "zone": str(get_localzone())
        }
        self.focused = {CurrencyType.CRYPTO: [], CurrencyType.STOCK: []}
    
    def focus(self, symbols: Union[str, List[str]]) -> Optional[Dict]:
        if isinstance(symbols, str): symbols = [symbols]
        for symbol in symbols:
            try:
                clean_symbol = symbol.replace('/', '')
                asset = self.trading_client.get_asset(symbol_or_asset_id=clean_symbol)
                if asset.asset_class == AssetClass.CRYPTO:
                    self.focused[CurrencyType.CRYPTO].append(asset.symbol)
                else:
                    self.focused[CurrencyType.STOCK].append(asset.symbol)
            except APIError as e:
                print(f"[!] Error focusing on {symbol}: {e}")
                continue
        
        print(f"[+] Focused symbols: {self.focused}")
        return self.focused if any(self.focused.values()) else None
    
    async def fetch_historical(self, currency: CurrencyType, data_type: DataType, interval: Dict) -> Optional[Dict[str, pd.DataFrame]]:
        if not self.focused[currency]:
            return None
        client_type = self._historical_client(currency)
        request_type = self._historical_request(currency, data_type)
        if not client_type or not request_type:
            return None
        
        try:
            self.hist_data = {symbol: None for symbol in self.focused[currency]}
            method_name = f"get_{currency.value}_{data_type.value}"
            
            for symbol in self.focused[currency]:
                # Create request based on data type
                if data_type == DataType.BARS:
                    request = request_type(
                        symbol_or_symbols=symbol,
                        timeframe=self._time_frame(interval), 
                        start=self._start_time(interval),
                    )
                else:
                    request = request_type(
                        symbol_or_symbols=symbol,
                        start=self._start_time(interval),
                    )
                # Add timeout to prevent hanging
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(getattr(client_type, method_name), request),
                        timeout=60.0
                    )
                except asyncio.TimeoutError:
                    print(f"[!] API call timed out for {symbol}")
                    self.hist_data[symbol] = None
                    continue
                except Exception as api_error:
                    print(f"[!] API call failed for {symbol}: {api_error}")
                    self.hist_data[symbol] = None
                    continue
                
                # Convert response to DataFrame
                data = response.df if hasattr(response, 'df') and response.df is not None else pd.DataFrame()
                self.hist_data[symbol] = data
            
            return self.hist_data
            
        except Exception as e:
            print(f"[!] Error fetching {currency.value} {data_type.value}: {e}")
            return None
        
    def _start_time(self, interval: Dict) -> Optional[datetime]:
        try:
            range_config = interval["range"]
            return datetime.now(ZoneInfo(self.info["zone"])) - timedelta(
                days=range_config["day"],
                hours=range_config["hour"],
                minutes=range_config["minute"]
            )
        except APIError as e:
            print(f"[!] Error calculating start time: {e}")
            return None
        
    def _time_frame(self, interval: Dict) -> Optional[TimeFrame]:
        try:
            step = interval["step"]
            if step["day"] > 0:
                return TimeFrame(step["day"], TimeFrameUnit.Day)
            elif step["hour"] > 0:
                return TimeFrame(step["hour"], TimeFrameUnit.Hour)
            else:
                return TimeFrame(step["minute"], TimeFrameUnit.Minute)
        except APIError as e:
            print(f"[!] Error creating timeframe: {e}")
            return None
        
    async def start_stream(self, currency: CurrencyType, data_type: DataType) -> str:
        if not self.focused[currency]:
            return f"No {currency.value} symbols focused"
        
        # Check if stream is already running for this currency
        if currency in self.active_stream and not self.active_stream[currency].done():
            return f"{currency.value.title()} stream already running"
        
        # Create stream client using existing method
        stream_client = self._stream_client(currency)
        if not stream_client:
            return f"Failed to create {currency.value} stream client"
        
        try:
            # Subscribe to data using dynamic method lookup
            method_name = f"subscribe_{data_type.value}"
            symbols = self.focused[currency]
            
            subscribe_method = getattr(stream_client, method_name)
            subscribe_method(self._stream_update, *symbols)
            
            # Store the stream client for cleanup
            self.stream_clients[currency] = stream_client
            
            # Create async task to run the stream
            async def _run_stream():
                try:
                    await stream_client._run_forever()
                    print(f"[o] {currency.value.title()} stream ended normally")
                except Exception as e:
                    print(f"[!] {currency.value.title()} stream error: {e}")
                finally:
                    await self._stream_cleanup(stream_client)
                    # Remove from clients dict when done
                    if currency in self.stream_clients:
                        del self.stream_clients[currency]
            
            # Start the stream task
            task = asyncio.create_task(_run_stream())
            print(f"[o] {currency.value.title()} stream task created")
            self.active_stream[currency] = task
            
            return f"{currency.value.title()} stream started successfully"
            
        except Exception as e:
            return f"Failed to start {currency.value} stream: {str(e)}"

    async def stop_stream(self) -> str:
        """Stop all active streams with complete cleanup"""
        if not self.active_stream:
            return "No active streams to stop"

        stopped_count = 0
        for currency, task in list(self.active_stream.items()):
            if task and not task.done():
                print(f"[o] Stopping {currency.value} stream")
                
                # Clean up stream client
                if currency in self.stream_clients:
                    await self._stream_cleanup(self.stream_clients[currency])
                
                # Cancel and wait for task
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                
                stopped_count += 1

        # Clear all and force garbage collection
        self.active_stream.clear()
        self.stream_clients.clear()
        
        import gc
        gc.collect()
        
        return f"Stopped {stopped_count} stream(s) successfully"
        
        