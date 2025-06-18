from head import *
# ------------- Data Retrieval -------------
from alpaca.data.live.stock import StockDataStream
from alpaca.data.live.crypto import CryptoDataStream
from alpaca.data.live import OptionDataStream

from alpaca.data.historical.stock import StockHistoricalDataClient
from alpaca.data.historical.crypto import CryptoHistoricalDataClient
from alpaca.data.historical import OptionHistoricalDataClient
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.requests import (
    StockBarsRequest, StockQuotesRequest, StockTradesRequest,
    CryptoBarsRequest, CryptoQuoteRequest, CryptoTradesRequest,
    OptionChainRequest
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

class MarketType(Enum):
    OPTION = "option"
    SPOT = "spot"

class CurrencyType(Enum):
    CRYPTO = "crypto"
    STOCK = "stock"

class DataType(Enum):
    BARS = "bars"
    QUOTES = "quotes"
    TRADES = "trades"
    CHAIN = "chain"
    
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
    
    def _option_client(self, currency: CurrencyType) -> Optional[OptionHistoricalDataClient]:
        try:
            return OptionHistoricalDataClient(
                api_key=self.config["API_KEY"],
                secret_key=self.config["SECRET_KEY"]
            )
        except APIError as e:
            print(f"[!] Error creating {currency.value} option client: {e}")
            return None
        
    def _option_request(self, currency: CurrencyType, data_type: DataType) -> Optional[type]:
        try:
            request_type = {
                CurrencyType.STOCK: {
                    DataType.CHAIN: OptionChainRequest
                },
                CurrencyType.CRYPTO: {
                    DataType.CHAIN: OptionChainRequest
                }
            }
            return request_type[currency][data_type]
        except APIError as e:
            print(f"[!] Error creating {currency.value} {data_type.value} request: {e}")
            return None

    def _historical_client(self, currency: CurrencyType) -> Optional[Union[CryptoHistoricalDataClient, StockHistoricalDataClient]]:
        try: 
            clients = { 
                CurrencyType.CRYPTO: CryptoHistoricalDataClient,
                CurrencyType.STOCK: StockHistoricalDataClient,
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
        
    def _stream_client(self, currency: CurrencyType) -> Optional[Union[CryptoDataStream, StockDataStream, OptionDataStream]]:
        try:
            clients = {
                CurrencyType.CRYPTO: CryptoDataStream,
                CurrencyType.STOCK: StockDataStream,
                CurrencyType.OPTION: OptionDataStream
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

            # Create DataFrame for display
            df = pd.DataFrame([content], index=[timestamp])
            df.index.name = 'timestamp'
            
            # Format the display
            pd.set_option('display.float_format', lambda x: '%.2f' % x)
            print(f"\n[o] {symbol} Update at {timestamp}")
            print(df.to_string())
            
            # Convert to DataFrame with MultiIndex for storage
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
        
        # Clear existing focused symbols
        self.focused = {CurrencyType.CRYPTO: [], CurrencyType.STOCK: []}
        
        for symbol in symbols:
            try:
                clean_symbol = symbol.replace('/', '')
                asset = self.trading_client.get_asset(symbol_or_asset_id=clean_symbol)
                if asset.asset_class == AssetClass.CRYPTO:
                    if asset.symbol not in self.focused[CurrencyType.CRYPTO]:
                        self.focused[CurrencyType.CRYPTO].append(asset.symbol)
                else:
                    if asset.symbol not in self.focused[CurrencyType.STOCK]:
                        self.focused[CurrencyType.STOCK].append(asset.symbol)
            except APIError as e:
                print(f"[!] Error focusing on {symbol}: {e}")
                continue
        
        print(f"[+] Focused symbols: {self.focused}")
        return self.focused if any(self.focused.values()) else None
    
    async def fetch_options(self, currency: CurrencyType) -> Optional[Dict[str, pd.DataFrame]]:
        # Helper functions
        def _clean_symbol(symbol: str) -> str:
            return symbol.replace('/', '').upper()
            
        def _get_next_expiration(symbol: str) -> Optional[date]:
            current_date = datetime.now(ZoneInfo(self.info["zone"])).date()
            
            for days in range(31):  # Check current date and next 30 days
                check_date = current_date + timedelta(days=days)
                request = OptionChainRequest(
                    underlying_symbol=symbol,
                    expiration_date=check_date,
                    include_otc=False,
                    limit=1
                )
                
                try:
                    response = client_type.get_option_chain(request)
                    if (isinstance(response, dict) and response) or (hasattr(response, 'contracts') and response.contracts):
                        return check_date
                except Exception:
                    continue
            
            print(f"[!] No valid expiration dates found for {symbol}")
            return None
            
        def _option_chain_request(symbol: str, page_token: Optional[str] = None) -> Optional[OptionChainRequest]:
            clean_symbol = _clean_symbol(symbol)
            expiration_date = _get_next_expiration(clean_symbol)
            if not expiration_date:
                return None
                
            print(f"[+] Using expiration date {expiration_date} for {clean_symbol}")
            
            try:
                return OptionChainRequest(
                    underlying_symbol=clean_symbol,
                    expiration_date=expiration_date,
                    include_otc=False,
                    page_token=page_token,
                    limit=1000,
                    include_volume=True,
                    include_open_interest=True,
                    include_underlying_price=True,
                    include_implied_volatility=True
                )
            except APIError as e:
                print(f"[!] Error creating option chain request: {str(e)}")
                return None

        def _process_option_chain(data: Dict) -> Dict[str, pd.DataFrame]:
            if not data:
                return {}
            
            # Convert dictionary of option contracts to DataFrame
            contracts = []
            for symbol, contract in data.items():
                contract_dict = contract if isinstance(contract, dict) else contract.__dict__
                underlying = ''.join(c for c in symbol if not c.isdigit())[:-1]
                contract_dict['underlying_symbol'] = underlying
                
                # Split latest_trade into separate columns
                if 'latest_trade' in contract_dict and contract_dict['latest_trade']:
                    trade = contract_dict['latest_trade']
                    contract_dict['trade_time'] = getattr(trade, 'timestamp', None)
                    contract_dict['trade_price'] = getattr(trade, 'price', None)
                    contract_dict['trade_size'] = getattr(trade, 'size', None)
                else:
                    contract_dict['trade_time'] = None
                    contract_dict['trade_price'] = None
                    contract_dict['trade_size'] = None
                
                # Split latest_quote into separate columns
                if 'latest_quote' in contract_dict and contract_dict['latest_quote']:
                    quote = contract_dict['latest_quote']
                    contract_dict['quote_time'] = getattr(quote, 'timestamp', None)
                    contract_dict['bid_price'] = getattr(quote, 'bid_price', None)
                    contract_dict['bid_size'] = getattr(quote, 'bid_size', None)
                    contract_dict['ask_price'] = getattr(quote, 'ask_price', None)
                    contract_dict['ask_size'] = getattr(quote, 'ask_size', None)
                else:
                    contract_dict['quote_time'] = None
                    contract_dict['bid_price'] = None
                    contract_dict['bid_size'] = None
                    contract_dict['ask_price'] = None
                    contract_dict['ask_size'] = None
                
                # Remove the original columns
                contract_dict.pop('latest_trade', None)
                contract_dict.pop('latest_quote', None)
                
                contracts.append(contract_dict)
            
            df = pd.DataFrame(contracts)
            if df.empty:
                return {}
                
            # Extract expiration date and option details from symbol
            def parse_option_symbol(symbol: str) -> tuple:
                date_str = symbol[len(underlying):len(underlying)+6]
                year = '20' + date_str[:2]
                month = date_str[2:4]
                day = date_str[4:6]
                exp_date = f"{year}-{month}-{day}"
                opt_type = symbol[len(underlying)+6]
                strike = float(symbol[len(underlying)+7:]) / 1000
                return exp_date, opt_type, strike
            
            # Add parsed columns and create multi-index
            parsed_data = [parse_option_symbol(sym) for sym in df['symbol']]
            df['expiration_date'] = [x[0] for x in parsed_data]
            df['option_type'] = [x[1] for x in parsed_data]
            df['strike_price'] = [x[2] for x in parsed_data]
            
            df.drop('symbol', axis=1, inplace=True)
            df.set_index(['underlying_symbol', 'expiration_date', 'option_type', 'strike_price'], inplace=True)
            df.sort_index(inplace=True)
            
            # Get next closest expiration for each symbol
            grouped = df.groupby(['underlying_symbol', 'expiration_date'])
            option_chains = {}
            for (symbol, exp_date), group_df in grouped:
                if symbol not in option_chains or exp_date < option_chains[symbol]['expiration_date']:
                    option_chains[symbol] = {
                        'expiration_date': exp_date,
                        'data': group_df
                    }
            
            return {symbol: data['data'] for symbol, data in option_chains.items()}

        # Main function logic
        
        if not self.focused[currency]:
            print("[!] No focused symbols for", currency.value)
            return None
            
        if currency == CurrencyType.CRYPTO:
            print("[!] Crypto options are not supported by Alpaca")
            return None
            
        client_type = self._option_client(currency)
        if not client_type:
            print("[!] Failed to create option client")
            return None

        try:
            all_chains = {}
            for symbol in self.focused[currency]:
                print(f"\n[+] Fetching option chain for {symbol}...")
                all_contracts = {}
                page_token = None
                
                while True:
                    request = _option_chain_request(symbol, page_token)
                    if not request:
                        break
                    
                    try:
                        response = await asyncio.wait_for(
                            asyncio.to_thread(client_type.get_option_chain, request),
                            timeout=60.0
                        )
                        
                        if not response:
                            break
                        
                        if isinstance(response, dict):
                            all_contracts.update(response)
                        
                        if hasattr(response, 'next_page_token') and response.next_page_token:
                            page_token = response.next_page_token
                        else:
                            break
                            
                    except (asyncio.TimeoutError, Exception) as e:
                        print(f"[!] Error fetching option chain for {symbol}: {str(e)}")
                        break
                
                if all_contracts:
                    chains = _process_option_chain(all_contracts)
                    all_chains.update(chains)
                else:
                    print(f"[!] No option contracts found for {symbol}")
            
            return all_chains
            
        except Exception as e:
            print(f"[!] Error in fetch_options: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
        
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
        
        