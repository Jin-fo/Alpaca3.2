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
        self.stream_clients: Dict[CurrencyType, Union[CryptoDataStream, StockDataStream]] = {}
        self.active_stream: Dict[CurrencyType, asyncio.Task] = {}
        self.new_data: List[pd.DataFrame] = []
    
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
        for currency, task in self.active_stream.items():
            if task and not task.done():
                return f"{currency.value} stream is running"
        return "No active streams"
        
    async def _stream_update(self, data, data_type: DataType) -> None:
        def _bars(data):
            content = {
                "open": data.open,
                "high": data.high,
                "low": data.low,
                "close": data.close,
                "volume": data.volume,
                "trade_count": data.trade_count,
                "vwap": data.vwap
            }
            return content
   
        def _quotes(data):
            content = {
                "bid_price": data.bid_price,
                "bid_size": data.bid_size,
                "ask_price": data.ask_price,
                "ask_size": data.ask_size
            }
            return content

        def _trades(data):
            content = {
                "price": data.price,
                "size": data.size
            }
            return content

        try: 
            # Handle the incoming stream data
            symbol = getattr(data, 'symbol', 'unknown')
            timestamp = getattr(data, 'timestamp', datetime.now())
            if data_type == DataType.BARS:
                content = _bars(data)
            elif data_type == DataType.QUOTES:
                content = _quotes(data)
            elif data_type == DataType.TRADES:
                content = _trades(data)

            print(f"[o] {symbol} : {timestamp}, {content}")
            
            # Convert to DataFrame
            df = pd.DataFrame([content], index=pd.MultiIndex.from_tuples(
                [(symbol, timestamp)], names=['symbol', 'timestamp']
            ))
            self.new_data.append(df)
            
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
        
        def _start_time(interval: Dict) -> Optional[datetime]:
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
        
        def _time_frame(interval: Dict) -> Optional[TimeFrame]:
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
       
        try:
            self.hist_data = {symbol: None for symbol in self.focused[currency]}
            method_name = f"get_{currency.value}_{data_type.value}"
            
            # Create request based on data type
            if data_type == DataType.BARS:
                request = request_type(
                symbol_or_symbols=self.focused[currency],
                    timeframe=_time_frame(interval), 
                    start=_start_time(interval),
                )
            else:
                request = request_type(
                symbol_or_symbols=self.focused[currency],
                    start=_start_time(interval),
                )
            # Add timeout to prevent hanging
            try:
                response = await asyncio.wait_for(
                    asyncio.to_thread(getattr(client_type, method_name), request),
                    timeout=60.0
                )
            except asyncio.TimeoutError:
                print(f"[!] API call timed out for {currency.value} {data_type.value}")
                return {}
            except Exception as api_error:
                print(f"[!] API call failed for {currency.value} {data_type.value}: {api_error}")
                return {}
            
            df = response.df
            if df is not None and not df.empty:
                # Store the complete multi-index DataFrame for each symbol
                hist_data = {
                    symbol: df.xs(symbol, level='symbol').copy()
                    for symbol in df.index.get_level_values('symbol').unique()
                }
                
                # Add symbol back as index level for each DataFrame
                for symbol, symbol_df in hist_data.items():
                    symbol_df.index = pd.MultiIndex.from_tuples(
                        [(symbol, idx) for idx in symbol_df.index],
                        names=['symbol', 'timestamp']
                    )
            else:
                hist_data = {}
            
            return hist_data
            
        except Exception as e:
            print(f"[!] Error fetching {currency.value} {data_type.value}: {e}")
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

            async def _handler(data):
                await self._stream_update(data, data_type)
            
            try:
                await asyncio.wait_for(
                    asyncio.to_thread(getattr(stream_client, method_name), _handler, *self.focused[currency]),
                    timeout=60.0
                )
            except asyncio.TimeoutError:
                print(f"[!] API call timed out")
  
            except Exception as e:
                print(f"[!] Error subscribing to {currency.value} {data_type.value}: {e}")
            
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

    async def end_stream(self) -> str:
        """Stop all active streams with complete cleanup"""
        if not self.active_stream:
            print("[!] No active streams to stop")
            return

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
        return
        
    def get_stream_status(self) -> str:
        """Public method to get stream status"""
        return self._stream_status()
        
        