from head import *
# ------------- Data Retrieval -------------
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.data.live import NewsDataStream, StockDataStream, CryptoDataStream, OptionDataStream
from alpaca.data.historical import NewsClient, StockHistoricalDataClient, CryptoHistoricalDataClient, OptionHistoricalDataClient
from alpaca.data.requests import (
    StockBarsRequest, StockQuotesRequest, StockTradesRequest, StockLatestBarRequest, StockSnapshotRequest,
    CryptoBarsRequest, CryptoQuoteRequest, CryptoTradesRequest, CryptoLatestBarRequest, CryptoSnapshotRequest,
    OptionChainRequest, OptionBarsRequest, OptionTradesRequest, OptionSnapshotRequest, 
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
    STOCK = "stock"
    CRYPTO = "crypto"
    OPTION = "option"

class DataType(Enum):
    BARS = "bars"
    QUOTES = "quotes"
    TRADES = "trades"
    CHAIN = "chain"
    
    @classmethod
    def from_string(cls, value: str) -> 'DataType':
        """Create DataType from string (case-insensitive)"""
        try:
            return cls[value.upper()]
        except KeyError:
            valid_types = [dt.name for dt in cls]
            raise ValueError(f"'{value}' is not a valid DataType. Valid types: {', '.join(valid_types)}")

class Client:

    def __init__(self) -> None:
        self.api_key : str = None
        self.secret_key : str = None
        self.paper : bool = True

        self.location : str = None

        self.historical_client : Dict[MarketType, type] = {
            MarketType.STOCK: StockHistoricalDataClient,
            MarketType.CRYPTO: CryptoHistoricalDataClient,
            MarketType.OPTION: OptionHistoricalDataClient
        }

        self.stream_client : Dict[MarketType, type] = {
            MarketType.STOCK: StockDataStream,
            MarketType.CRYPTO: CryptoDataStream,
            MarketType.OPTION: OptionDataStream
        }

        self.trading_client : TradingClient = None

    def load(self, config: Dict[str, Any], location: str) -> None:
        self.location = location

        if self.api_key != config['key'] or self.secret_key != config['secret'] or self.paper != config['paper']:
            self.api_key = config['key']
            self.secret_key = config['secret']
            self.paper = config['paper']
            self.update()
        
    def update(self) -> None:
        self.trading_client = TradingClient(api_key=self.api_key, secret_key=self.secret_key)
        for market in MarketType:

            self.historical_client[market] = self.historical_client[market](api_key=self.api_key, secret_key=self.secret_key)
            self.stream_client[market] = self.stream_client[market](api_key=self.api_key, secret_key=self.secret_key)

class Historical(Client):

    def __init__(self) -> None:
        super().__init__()
        self.folder : str = None
        
        self.latest_tasks: Dict[str, asyncio.Task] = {}
        self.latest_data: Dict[str, pd.DataFrame] = {}

    def _request(self, market: MarketType, data_type: DataType) -> Optional[type]:
        try:
            request_type = {
                MarketType.STOCK: {
                    DataType.BARS: StockBarsRequest,
                    DataType.QUOTES: StockQuotesRequest,
                    DataType.TRADES: StockTradesRequest
                },
                MarketType.CRYPTO: {
                    DataType.BARS: CryptoBarsRequest,
                    DataType.QUOTES: CryptoQuoteRequest,
                    DataType.TRADES: CryptoTradesRequest
                },
                MarketType.OPTION: {
                    DataType.CHAIN: OptionChainRequest,
                    DataType.BARS: OptionBarsRequest,
                    DataType.TRADES: OptionTradesRequest
                }
            }
            return request_type[market][data_type]
        
        except APIError as e:
            print(f"[!] Error creating {market.value} {data_type.value} request: {e}")
            return None

    def _request_latest(self, market: MarketType, data_type: DataType) -> Optional[type]:
        try:
            request_type = {
                MarketType.STOCK: StockLatestBarRequest,
                MarketType.CRYPTO: CryptoLatestBarRequest,
            }
            return request_type[market][data_type]
        except APIError as e:
            print(f"[!] Error creating {market.value} {data_type.value} request: {e}")


    def _start_date(self, time_value: Dict) -> datetime:
        range_config = time_value["range"]
        if range_config["day"] > 0: 
            return datetime.now(ZoneInfo(self.location)) - timedelta(days=range_config["day"])
        elif range_config["hour"] > 0:
            return datetime.now(ZoneInfo(self.location)) - timedelta(hours=range_config["hour"])
        elif range_config["minute"] > 0:
            return datetime.now(ZoneInfo(self.location)) - timedelta(minutes=range_config["minute"])
        else:
            raise Exception(f"Invalid range time: {range_config}")

    def _delta_time(self, time_value: Dict) -> TimeFrame:
        step_config = time_value["step"]
        if step_config["day"] > 0:
            return TimeFrame(step_config["day"], TimeFrameUnit.Day)
        elif step_config["hour"] > 0:
            return TimeFrame(step_config["hour"], TimeFrameUnit.Hour)
        elif step_config["minute"] > 0:
            return TimeFrame(step_config["minute"], TimeFrameUnit.Minute)
        else:
            raise Exception(f"Invalid step time: {step_config}")

    async def stock_request(self, stock: List[str], data_type: DataType, time_value: Dict) -> Dict[str, pd.DataFrame]:
        client_type = self.historical_client[MarketType.STOCK]
        request_type = self._request(MarketType.STOCK, data_type)

        if not client_type or not request_type:
            print(f"[!] Failed to create {MarketType.STOCK.value} historical client or request")
            return None
        
        print(f"[>] Fetching {MarketType.STOCK.value} {data_type.value}: {stock}")
        
        try:
            request = None
            historical_method = getattr(client_type, f"get_stock_{data_type.value.lower()}")
            response_dict = {}

            for symbol in stock:
                if data_type == DataType.BARS:
                    request = request_type(
                        symbol_or_symbols=symbol,
                        timeframe=self._delta_time(time_value),
                        start=self._start_date(time_value)
                    )

                elif data_type == DataType.QUOTES:
                    request = request_type(
                        symbol_or_symbols=symbol,
                        start=self._start_date(time_value)
                    )

                elif data_type == DataType.TRADES:
                    request = request_type(
                        symbol_or_symbols=symbol,
                        start=self._start_date(time_value)
                    )

                if historical_method and request:
                    response = await asyncio.to_thread(historical_method, request)
                    if response:
                        response_dict[symbol] = response.df
                    else:
                        raise Exception(f"response: {response}")
                else:
                    raise Exception(f"historical_method: {historical_method} | request: {request}")
            
            return response_dict

        except Exception as e:
            print(f"[!] Error: {e}")
            return None

    async def crypto_request(self, crypto: List[str], data_type: DataType, time_value: Dict) -> Dict[str, pd.DataFrame]:
        client_type = self.historical_client[MarketType.CRYPTO]
        request_type = self._request(MarketType.CRYPTO, data_type)

        if not client_type or not request_type:
            print(f"[!] Invalid {MarketType.CRYPTO.value} historical client or request")
            return None
        
        print(f"[>] Fetching {MarketType.CRYPTO.value} {data_type.value}: {crypto}")
        
        try:
            request = None
            historical_method = getattr(client_type, f"get_crypto_{data_type.value.lower()}")
            response_dict = {}

            for symbol in crypto:
                if data_type == DataType.BARS:
                    request = request_type(
                        symbol_or_symbols=symbol,
                        timeframe=self._delta_time(time_value),
                        start=self._start_date(time_value)
                    )

                elif data_type == DataType.QUOTES:
                    request = request_type(
                        symbol_or_symbols=symbol,
                        start=self._start_date(time_value)
                    )

                elif data_type == DataType.TRADES:
                    request = request_type(
                        symbol_or_symbols=symbol,
                        start=self._start_date(time_value)
                    )

                if historical_method and request:
                    try:
                        response = await asyncio.wait_for(
                                asyncio.to_thread(historical_method, request),
                            timeout=60.0
                        )
                        if response:
                            response_dict[symbol] = response.df
                        else:
                            raise Exception(f"response: {response}")
                    except (asyncio.TimeoutError, Exception) as e:
                        print(f"[!] Error: {e}")
                        return None 

            return response_dict

        except Exception as e:
            print(f"[!] Error: {e}")
            return None

    async def option_request(self, option: List[str], data_type: DataType, time_value: Dict) -> Union[pd.DataFrame, Dict[str, pd.DataFrame], None]:
        client_type = self.historical_client[MarketType.OPTION]
        request_type = self._request(MarketType.OPTION, data_type)

        if not client_type or not request_type:
            print(f"[!] Invalid {MarketType.OPTION.value} historical client or request")
            return None
        
        def _next_expiration_date(symbol: str, time_value: Dict) -> Optional[datetime]:
            """Find the next valid expiration date for a symbol"""
            current_date = datetime.now(ZoneInfo(self.location)).date() + timedelta(days=time_value["expire"]["day"])
            
            for days in range(31):  # Check next 30 days
                check_date = current_date + timedelta(days=days)
                request = OptionChainRequest(
                    underlying_symbol=symbol,
                    expiration_date=check_date,
                    include_otc=False,
                    limit=1
                )
                response = client_type.get_option_chain(request)
                
                if response and (isinstance(response, dict) and response) or (hasattr(response, 'contracts') and response.contracts):
                    print(f"[o] Next expiration date: {check_date} for {symbol}")
                    return check_date
                else:
                    continue
            raise Exception(f"No valid expiration dates found for {symbol}")

        async def _retrive_chain(symbol: str, expiration_date: datetime) -> Optional[Dict]:
            """Fetch all pages of option chain data for a symbol"""
            all_contracts = {}
            page_token = None
            
            while True:
                request = request_type(
                    underlying_symbol=symbol,
                    expiration_date=expiration_date,
                    page_token=page_token,
                    include_otc=False,
                    limit=1000,
                    include_volume=True,
                    include_open_interest=True,
                    include_underlying_price=True,
                    include_implied_volatility=True
                )
                historical_method = getattr(client_type, f"get_option_chain")

                if historical_method and request:
                    try:
                        response = await asyncio.wait_for(
                        asyncio.to_thread(historical_method, request),
                        timeout=60.0
                    )
                    except (asyncio.TimeoutError, Exception) as e:
                        print(f"[!] Error: {e}")
                        return None
                else:
                    raise Exception(f"historical_method: {historical_method} | request: {request}")
                
                if isinstance(response, dict):
                    all_contracts.update(response)
                elif hasattr(response, 'contracts'):
                    all_contracts.update(response.contracts)
                else:
                    raise Exception(f"response: {response}")
                
                if hasattr(response, 'next_page_token') and response.next_page_token:
                    page_token = response.next_page_token
                else:
                    break
            
            return all_contracts

        def _clean_chain(chain: Dict) -> pd.DataFrame:
            """Convert option chain data to DataFrame for single symbol"""            
            contracts = []
            for symbol, contract in chain.items():
                contract_dict = contract if isinstance(contract, dict) else contract.__dict__
                
                # Extract underlying symbol from option symbol
                underlying = ''.join(c for c in symbol if not c.isdigit())[:-1]
                contract_dict['underlying_symbol'] = underlying
                
                # Parse option symbol to get expiration, type, and strike
                date_str = symbol[len(underlying):len(underlying)+6]
                year = '20' + date_str[:2]
                month = date_str[2:4]
                day = date_str[4:6]
                contract_dict['expiration_date'] = f"{year}-{month}-{day}"
                contract_dict['option_type'] = symbol[len(underlying)+6]
                contract_dict['strike_price'] = float(symbol[len(underlying)+7:]) / 1000
                
                # Extract trade data
                if 'latest_trade' in contract_dict and contract_dict['latest_trade']:
                    trade = contract_dict['latest_trade']
                    contract_dict['trade_time'] = getattr(trade, 'timestamp', None)
                    contract_dict['trade_price'] = getattr(trade, 'price', None)
                    contract_dict['trade_size'] = getattr(trade, 'size', None)
                
                # Extract quote data
                if 'latest_quote' in contract_dict and contract_dict['latest_quote']:
                    quote = contract_dict['latest_quote']
                    contract_dict['quote_time'] = getattr(quote, 'timestamp', None)
                    contract_dict['bid_price'] = getattr(quote, 'bid_price', None)
                    contract_dict['bid_size'] = getattr(quote, 'bid_size', None)
                    contract_dict['ask_price'] = getattr(quote, 'ask_price', None)
                    contract_dict['ask_size'] = getattr(quote, 'ask_size', None)
                
                # Remove original nested objects
                contract_dict.pop('latest_trade', None)
                contract_dict.pop('latest_quote', None)
                contract_dict.pop('symbol', None)
                
                contracts.append(contract_dict)
            
            df = pd.DataFrame(contracts)
            if df.empty:
                return df
            
            # Set multi-index and sort
            df.set_index(['underlying_symbol', 'expiration_date', 'option_type', 'strike_price'], inplace=True)
            df.sort_index(inplace=True)
            
            return df

        print(f"[>] Fetching {MarketType.OPTION.value} {data_type.value}: {option}")
        try:
            if data_type == DataType.CHAIN:
                all_chains = {}
                
                for symbol in option:
                    expiration_date = _next_expiration_date(symbol, time_value)
                    contracts = await _retrive_chain(symbol, expiration_date)
                    if contracts:
                        all_chains[symbol] = _clean_chain(contracts)
                return all_chains
            elif data_type == DataType.BARS:
                # For options, bars data is not directly supported in the same way
                print(f"[!] {DataType.BARS.value} data type not supported for options")
                return None
            elif data_type == DataType.TRADES:
                # For options, trades data is not directly supported in the same way
                print(f"[!] {DataType.TRADES.value} data type not supported for options")
                return None
            else:
                raise Exception(f"Unsupported data type for options: {data_type.value}")

        except Exception as e:
            print(f"[!] Error: {e}")
            return None

    async def stock_latest(self, stock: List[str], data_type: DataType, periodic: bool = False, time_value: Dict = None) -> Dict[str, pd.DataFrame]:
        if periodic and time_value:
            await self._latest_periodic(stock, MarketType.STOCK, data_type, time_value)
            return self.latest_data
        
        client_type = self.historical_client[MarketType.STOCK]
        request_type = self._request_latest(MarketType.STOCK, data_type)

        if not client_type or not request_type:
            print(f"[!] Invalid {MarketType.STOCK.value} historical client or request")
            return None
        
        try:
            response_dict = {}
            historical_method = getattr(client_type, f"get_stock_{data_type.value.lower()}")

            for symbol in stock:
                request = request_type(symbol_or_symbols=symbol)
                response = await asyncio.to_thread(historical_method, request)
                if response:
                    response_dict[symbol] = response.df

            return response_dict

        except Exception as e:
            print(f"[!] Error: {e}")
            return None
        
    async def crypto_latest(self, crypto: List[str], data_type: DataType, periodic: bool = False, time_value: Dict = None) -> Dict[str, pd.DataFrame]:
        if periodic and time_value:
            await self._latest_periodic(crypto, MarketType.CRYPTO, data_type, time_value)
            return self.latest_data
        
        client_type = self.historical_client[MarketType.CRYPTO]
        request_type = self._request_latest(MarketType.CRYPTO, data_type)

        if not client_type or not request_type:
            print(f"[!] Invalid {MarketType.CRYPTO.value} historical client or request")
            return None

        try:
            response_dict = {}
            historical_method = getattr(client_type, f"get_crypto_{data_type.value.lower()}")
            
            for symbol in crypto:
                request = request_type(symbol_or_symbols=symbol)
                response = await asyncio.to_thread(historical_method, request)
                if response:
                    response_dict[symbol] = response.df
            
            return response_dict
        
        except Exception as e:
            print(f"[!] Error: {e}")
            return None

    async def _latest_periodic(self, symbols: List[str], market: MarketType, data_type: DataType, time_value: Dict) -> None:
        step = time_value["step"]
        interval = step["day"]*86400 + step["hour"]*3600 + step["minute"]*60 or 300
        
        async def _fetch():
            while True:
                try:
                    if market == MarketType.STOCK:
                        data = await self.stock_latest(symbols, data_type)
                    elif market == MarketType.CRYPTO:
                        data = await self.crypto_latest(symbols, data_type)
                    
                    if data:
                        self.latest_data.update(data)
                        print(f"[o] Updated latest {market.value} at {datetime.now().strftime('%H:%M:%S')}")
                    
                    await asyncio.sleep(interval)
                except Exception as e:
                    print(f"[!] Latest fetch error: {e}")
                    await asyncio.sleep(interval)
        
        task_key = f"{market.value}_latest"
        if task_key in self.latest_tasks:
            self.latest_tasks[task_key].cancel()
        
        self.latest_tasks[task_key] = asyncio.create_task(_fetch())
        print(f"[>] Started latest {market.value} every {interval}s")

class Stream(Client):
    def __init__(self) -> None:
        super().__init__()
        self.folder : str = None

        self.running_stream: bool = False
        self.active_stream : Dict[str, Dict[str, Any]] = {} #store active stream for each symbol: {"task": task, "client": client}

        self.crypto_data : Dict[str, Any] = {}
        self.stock_data : Dict[str, Any] = {}
        self.option_data : Dict[str, Any] = {}

    def _status(self) -> str:
        """Get current stream status"""
        if not self.active_stream and self.running_stream == False:
            return "No active streams"
        
        active_streams = []
        for symbol, stream_info in self.active_stream.items():
            task = stream_info.get("task")
            if task and not task.done():
                active_streams.append(f"{symbol} stream")
            elif task and task.done():
                active_streams.append(f"{symbol} stream (completed)")
        
        if active_streams:
            return ", ".join(active_streams)
        else:
            return "No active streams"
        
    async def pop_new_data(self, market) -> Dict[str, pd.DataFrame]:
        """Get new data and convert to standardized DataFrame format"""
        def _convert_to_dataframe(data, symbol: str) -> pd.DataFrame:
            """Convert any data type to DataFrame with consistent format"""
            if data is None:
                return pd.DataFrame()
            
            # If already a DataFrame, return as is
            if isinstance(data, pd.DataFrame):
                return data
            
            # If it's a dict, convert to DataFrame
            if isinstance(data, dict):
                return pd.DataFrame([data])
            
            # If it's a list, convert to DataFrame
            if isinstance(data, list):
                return pd.DataFrame(data)
            
            # If it's a single object (like bar, trade, quote), convert to dict then DataFrame
            if hasattr(data, '__dict__'):
                return pd.DataFrame([data.__dict__])
            
            # If it's a named tuple or similar, convert to dict
            if hasattr(data, '_asdict'):
                return pd.DataFrame([data._asdict()])
            
            # Fallback: try to convert to DataFrame directly
            try:
                return pd.DataFrame(data)
            except:
                # Last resort: create empty DataFrame
                return pd.DataFrame()
        
        if market == MarketType.CRYPTO:
            if not self.crypto_data:
                return {}
            
            converted_data = {}
            for symbol, data in self.crypto_data.items():
                if data is not None:
                    df = _convert_to_dataframe(data, symbol)
                    if not df.empty:
                        # Add symbol column if not present
                        if 'symbol' not in df.columns:
                            df['symbol'] = symbol
                        converted_data[symbol] = df

            self.crypto_data.clear()
            
        elif market == MarketType.STOCK:
            if not self.stock_data:
                return {}
            
            converted_data = {}
            for symbol, data in self.stock_data.items():
                if data is not None:
                    df = _convert_to_dataframe(data, symbol)
                    if not df.empty:
                        # Add symbol column if not present
                        if 'symbol' not in df.columns:
                            df['symbol'] = symbol
                        converted_data[symbol] = df

            self.stock_data.clear()
            
        elif market == MarketType.OPTION:
            if not self.option_data:
                return {}
            
            converted_data = {}
            for symbol, data in self.option_data.items():
                if data is not None:
                    df = _convert_to_dataframe(data, symbol)
                    if not df.empty:
                        # Add symbol column if not present
                        if 'symbol' not in df.columns:
                            df['symbol'] = symbol
                        converted_data[symbol] = df 

            self.option_data.clear()

        return converted_data

    async def stock_run(self, stock: List[str], data_type: DataType, time_value: Dict = None) -> None:
        # Check if there's already an active stock stream and stop it
        for symbol in stock:
            if symbol in self.active_stream and self.active_stream[symbol].get("task") and not self.active_stream[symbol]["task"].done():
                print(f"[o] Stopping existing {symbol} stream before starting new one")
                await self._stop_stream(symbol)
                #working for more efficient stream stop

        self.running_stream = True;

        if not self.stream_client[MarketType.STOCK]:
            print(f"[!] Failed to create {MarketType.STOCK.value} stream client")
            return
        
        stream_client = self.stream_client[MarketType.STOCK]

        print(f"[>] Fetching {MarketType.STOCK.value} {data_type.value}: {stock}")
        try:    
            stream_method = getattr(stream_client, f"subscribe_{data_type.value}")

            # Initialize data structures for all symbols
            for symbol in stock:
                if symbol not in self.stock_data:
                    self.stock_data[symbol] = None

            # Subscribe all symbols to the same stream client
            for symbol in stock:
                async def _update_handler(data, symbol=symbol):  # Capture symbol in parameter
                    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} @ {symbol}: \n{data}")
                    self.stock_data[symbol] = data

                await asyncio.wait_for(
                    asyncio.to_thread(stream_method, _update_handler, symbol),
                    timeout=60.0
                )
            
            # Create single stream task for all symbols
            async def _run_stream_with_error_handling():
                try:
                    await stream_client._run_forever()
                except Exception as e:
                    print(f"[!] {MarketType.STOCK.value} stream error: {e}")
                finally:
                    print(f"[o] {MarketType.STOCK.value} stream ended")
            
            task = asyncio.create_task(_run_stream_with_error_handling())
            print(f"[o] {MarketType.STOCK.value} stream task created")
            
            # Store the same task and client for all symbols
            for symbol in stock:
                self.active_stream[symbol] = {"task": task, "client": stream_client}

        except (asyncio.TimeoutError, Exception) as e:
            print(f"[!] Failed to create {MarketType.STOCK.value} {data_type.value} method: {e}")
            return

    async def crypto_run(self, crypto: List[str], data_type: DataType, time_value: Dict = None) -> None:
        # Check if there's already an active crypto stream and stop it
        for symbol in crypto:
            if symbol in self.active_stream and self.active_stream[symbol].get("task") and not self.active_stream[symbol]["task"].done():
                print(f"[o] Stopping existing {symbol} stream before starting new one")
                await self._stop_stream(symbol)

        self.running_stream = True;
        
        if not self.stream_client[MarketType.CRYPTO]:
            print(f"[!] Failed to create {MarketType.CRYPTO.value} stream client")
            return
        
        stream_client = self.stream_client[MarketType.CRYPTO]

        print(f"[>] Fetching {MarketType.CRYPTO.value} {data_type.value}: {crypto}")
        try:    
            stream_method = getattr(stream_client, f"subscribe_{data_type.value}")

            # Initialize data structures for all symbols
            for symbol in crypto:
                if symbol not in self.crypto_data:
                    self.crypto_data[symbol] = None

            # Subscribe all symbols to the same stream client
            for symbol in crypto:
                async def _update_handler(data, symbol=symbol):  # Capture symbol in parameter
                    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} : Data retrived for {symbol}")
                    self.crypto_data[symbol] = data

                await asyncio.wait_for(
                    asyncio.to_thread(stream_method, _update_handler, symbol),
                    timeout=60.0
                )
            
            # Create single stream task for all symbols
            async def _run_stream_with_error_handling():
                try:
                    await stream_client._run_forever()
                except Exception as e:
                    print(f"[!] {MarketType.CRYPTO.value} stream error: {e}")
                finally:
                    print(f"[o] {MarketType.CRYPTO.value} stream ended")
            
            task = asyncio.create_task(_run_stream_with_error_handling())
            print(f"[o] {MarketType.CRYPTO.value} stream task created")
            
            # Store the same task and client for all symbols
            for symbol in crypto:
                self.active_stream[symbol] = {"task": task, "client": stream_client}

        except (asyncio.TimeoutError, Exception) as e:
            print(f"[!] Failed to create {MarketType.CRYPTO.value} {data_type.value} method: {e}")
            return

    async def option_run(self, option: List[str], data_type: DataType, time_value: Dict = None) -> None:
        print(f"[!] {MarketType.OPTION.value} streaming not supported for options")
        return

    async def _stop_stream(self, symbol: str) -> None:
        """Stop a specific symbol stream"""
        async def _cleanup(stream) -> None:
            if not stream:
                return
            try:
                if hasattr(stream, 'stop_ws'):
                    await stream.stop_ws()
                if hasattr(stream, 'close'):
                    await stream.close()
            except Exception as e:
                print(f"[!] Cleanup warning: {e}")
            finally:
                gc.collect()
        
        if symbol in self.crypto_data:
            self.crypto_data[symbol].clear()
        elif symbol in self.stock_data:
            self.stock_data[symbol].clear()
        elif symbol in self.option_data:
            self.option_data[symbol].clear()

        if symbol in self.active_stream and self.active_stream[symbol]:
            stream_info = self.active_stream[symbol]
            task = stream_info.get("task")
            client = stream_info.get("client")
            
            if task and not task.done():
                print(f"[o] Stopping {symbol} stream")
                
                # Clean up stream client
                if client:
                    await _cleanup(client)
                
                # Cancel the task
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            # Remove from active streams
            del self.active_stream[symbol]

    async def stop_all(self) -> None:
        """Stop all active streams"""
        for symbol in list(self.active_stream.keys()):
            await self._stop_stream(symbol)
        self.running_stream = False
        print("[o] All streams stopped")

class Trade(Client):
    def __init__(self) -> None:
        super().__init__()
        self.folder : str = None

    def _client(self) -> TradingClient:
        if not self.api_key or not self.secret_key:
            raise ValueError("API credentials not loaded. Call load() method first.")
        return TradingClient(api_key=self.api_key, secret_key=self.secret_key, paper=self.paper)
    
    def buy(self, symbol: str, quantity: int, price: float) -> None:
        pass
    
    def sell(self, symbol: str, quantity: int, price: float) -> None:
        pass
    
    def cancel(self, symbol: str, quantity: int, price: float) -> None:
        pass

class Account():
    def __init__(self) -> None:
        self.name : str = None
        self.location : str = None
        self.investment : Dict[str, List[str]] = {}
        
        #action
        self.client = Client()
        self.historical = Historical()
        self.stream = Stream()
        self.trade = Trade()

    def load(self, config: Dict[str, Any]) -> None:
        self.config = config
        self.name = config['name']
        self.location = config['location']

        self.trade.load(config['api'], self.location)  # Trade class needs API credentials too
        self.stream.load(config['api'], self.location)  # Stream class needs API credentials 
        self.historical.load(config['api'], self.location)  # Historical class needs API credentials

        self.investment["crypto"] = self.focus(config["crypto"]["symbol"])
        self.investment["stock"] = self.focus(config["stock"]["symbol"])
        self.investment["option"] = self.focus(config["option"]["symbol"])
        print(f"[>] Investment: {self.investment}")

    def focus(self, symbols: Union[str, List[str]]) -> Union[List[str], None]:
        if not symbols:
            return None
        if isinstance(symbols, str):
            symbols = [symbols]
        symbols_list = []
        for symbol in symbols:
            try:
                asset = self.trade._client().get_asset(symbol_or_asset_id=symbol)
                if asset and asset.symbol not in symbols_list:
                    symbols_list.append(asset.symbol)
                else:
                    print(f"[!] {asset.symbol if asset else symbol} already in list or not found")
                    continue
            except (APIError, Exception) as e:
                print(f"[!] Error focusing on {symbol}: {e}")
                continue

        if not symbols_list:
            return None
        return symbols_list

    async def fetch_historical(self, market: MarketType) -> Optional[Union[pd.DataFrame, Dict[str, pd.DataFrame]]]:
        
        historical_data = None
        if market == MarketType.CRYPTO and self.investment["crypto"]:
            try:
                data_type = DataType.from_string(self.config["crypto"]["historical"])
                historical_data =  await self.historical.crypto_request(self.investment["crypto"], data_type, self.config["crypto"]["time_value"])
            except (KeyError, ValueError) as e:
                print(f"[!] Invalid crypto data type '{self.config['crypto']}': {e}")
                return None

        elif market == MarketType.STOCK and self.investment["stock"]:
            try:
                data_type = DataType.from_string(self.config["stock"]["historical"])
                historical_data = await self.historical.stock_request(self.investment["stock"], data_type, self.config["stock"]["time_value"])
            except (KeyError, ValueError) as e:
                print(f"[!] Invalid stock data type '{self.config['stock']}': {e}")
                return None

        elif market == MarketType.OPTION and self.investment["option"]:
            try:
                data_type = DataType.from_string(self.config["option"]["historical"])
                historical_data =  await self.historical.option_request(self.investment["option"], data_type, self.config["option"]["time_value"])
            except (KeyError, ValueError) as e:
                print(f"[!] Invalid option data type '{self.config['option']}': {e}")
                return None
        
        return historical_data

    async def start_stream(self, market: MarketType) -> None:
        
        if market == MarketType.CRYPTO and self.investment["crypto"]:
            try:
                data_type = DataType.from_string(self.config["crypto"]["stream"])
                await self.stream.crypto_run(self.investment["crypto"], data_type)
            except Exception as e:
                print(f"[!] Error starting {MarketType.CRYPTO.value} stream: {e}")
                return None
            
        elif market == MarketType.STOCK and self.investment["stock"]:
            try:
                data_type = DataType.from_string(self.config["stock"]["stream"])
                await self.stream.stock_run(self.investment["stock"], data_type)
            except Exception as e:
                print(f"[!] Error starting {MarketType.STOCK.value} stream: {e}")
                return None
            
        elif market == MarketType.OPTION and self.investment["option"]:
            try:
                data_type = DataType.from_string(self.config["option"]["stream"])
                await self.stream.option_run(self.investment["option"], data_type)
            except Exception as e:
                print(f"[!] Error starting {MarketType.OPTION.value} stream: {e}")
                return None
        elif market == MarketType.OPTION:
            print(f"[!] No {MarketType.OPTION.value} symbols configured for streaming")
            return None
    
    async def start_retrieve(self, market: MarketType) -> None:
        if market == MarketType.CRYPTO and self.investment["crypto"]:
            data_type = DataType.from_string(self.config["crypto"]["historical"])
            await self.historical.crypto_latest(self.investment["crypto"], data_type, True, self.config["crypto"]["time_value"])
        elif market == MarketType.STOCK and self.investment["stock"]:
            data_type = DataType.from_string(self.config["stock"]["historical"])
            await self.historical.stock_latest(self.investment["stock"], data_type, True, self.config["stock"]["time_value"])
        
    async def stop_retrieve(self) -> None:
        for task in self.historical.latest_tasks.values():
            task.cancel()
        self.historical.latest_tasks.clear()

    async def stop_stream(self) -> None:
        await self.stream.stop_all()

    def get_latest(self, symbol: str = None):
        return self.historical.latest_data.get(symbol) if symbol else self.historical.latest_data

    async def make_order(self, market: MarketType, order_type) -> None:
        pass

    async def display_status(self) -> None:
        """Display comprehensive application status"""
        print("\n" + "="*40)
        print("APPLICATION STATUS")
        print("="*40)
        
        # Account information
        print(f"Account: {self.name}")
        print(f"Location: {self.location}")
        
        # Stream status (if implemented)
        try:
            status = self.stream._status() if hasattr(self.stream, '_status') else "Not implemented"
            print(f"Streams: {status}")
        except Exception as e:
            print(f"Streams: Error getting status - {e}")
        
        # Periodic latest status
        try:
            latest_status = "Running" if self.historical.latest_tasks else "Stopped"
            latest_count = len(self.historical.latest_tasks)
            data_count = len(self.historical.latest_data)
            print(f"Periodic Latest: {latest_status} ({latest_count} tasks, {data_count} symbols with data)")
        except Exception as e:
            print(f"Periodic Latest: Error getting status - {e}")
        
        # Focused symbols by market type
        print(f"Crypto symbols: {self.investment.get('crypto', []) if self.investment.get('crypto') else 'None'}")
        print(f"Stock symbols: {self.investment.get('stock', []) if self.investment.get('stock') else 'None'}")
        print(f"Option symbols: {self.investment.get('option', []) if self.investment.get('option') else 'None'}")
        
        # Configuration data types
        try:
            crypto_data_type = self.config.get("crypto", {}).get("historical", "Not configured")
            stock_data_type = self.config.get("stock", {}).get("historical", "Not configured")
            option_data_type = self.config.get("option", {}).get("historical", "Not configured")
            
            print(f"Crypto data type: {crypto_data_type}")
            print(f"Stock data type: {stock_data_type}")
            print(f"Option data type: {option_data_type}")
        except Exception as e:
            print(f"Data types: Error getting config - {e}")
        
        # Detailed task analysis
        all_tasks = asyncio.all_tasks()
        print(f"\nASYNCIO TASKS ({len(all_tasks)} total):")
        print("-" * 40)
        
        task_categories = {
            'stream': [],
            'main': [],
            'input': [],
            'system': [],
            'unknown': []
        }
        
        for i, task in enumerate(all_tasks, 1):
            try:
                # Get task name and coroutine info
                task_name = getattr(task, '_name', f'Task-{i}')
                coro = task.get_coro()
                coro_name = getattr(coro, '__name__', str(coro))
                
                # Get more details about the coroutine
                if hasattr(coro, 'cr_code'):
                    func_name = coro.cr_code.co_name
                    filename = coro.cr_code.co_filename.split('/')[-1]
                    line_no = coro.cr_frame.f_lineno if coro.cr_frame else '?'
                    location = f"{filename}:{line_no}"
                else:
                    func_name = coro_name
                    location = "unknown"
                
                # Categorize tasks
                if 'run_stream' in func_name or 'stream' in func_name.lower():
                    task_categories['stream'].append(f"  {task_name}: {func_name} ({location})")
                elif 'main' in func_name or 'handle_action' in func_name:
                    task_categories['main'].append(f"  {task_name}: {func_name} ({location})")
                elif 'input' in func_name.lower() or 'executor' in str(task):
                    task_categories['input'].append(f"  {task_name}: {func_name} ({location})")
                elif any(x in func_name.lower() for x in ['loop', 'event', 'selector']):
                    task_categories['system'].append(f"  {task_name}: {func_name} ({location})")
                else:
                    task_categories['unknown'].append(f"  {task_name}: {func_name} ({location})")
                    
            except Exception as e:
                task_categories['unknown'].append(f"  Task-{i}: <error getting info: {e}>")
        
        # Display categorized tasks
        for category, tasks in task_categories.items():
            if tasks:
                print(f"{category.upper()} ({len(tasks)}):")
                for task_info in tasks:
                    print(task_info)
                print()
        
        print("="*40)
        

