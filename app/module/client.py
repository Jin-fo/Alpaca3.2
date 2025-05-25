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
        self.new_data: Dict[CurrencyType, pd.DataFrame] = {}
    
    def _historical_client(self, currency: CurrencyType) -> Optional[Union[CryptoHistoricalDataClient, StockHistoricalDataClient]]:
        try: 
            clients = {
                CurrencyType.CRYPTO: CryptoHistoricalDataClient,
                CurrencyType.STOCK: StockHistoricalDataClient
            }
            return clients[currency](self.config["API_KEY"], self.config["SECRET_KEY"])
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
    
    def _stream_request(self, currency: CurrencyType, data_type: DataType) -> Optional[type]:
        pass
    def _stream_update(self, data) -> None:
        pass
    def _stream_status(self) -> str:
        pass
    

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
                print(f"\n[!] Error focusing on {symbol}: {e}")
                continue
        return self.focused if any(self.focused.values()) else None
    
    async def fetch_historical(self, currency: CurrencyType, data_type: DataType, interval: Dict) -> Optional[Dict[str, pd.DataFrame]]:
        client_type = self._historical_client(currency)
        request_type = self._historical_request(currency, data_type)
        if not client_type or not request_type:
            return None
        
        try:
            result = {symbol: None for symbol in self.focused[currency]}
            method_name = f"get_{currency.value}_{data_type.value}"
            
            for symbol in self.focused[currency]:
                request = request_type(
                    symbol_or_symbols=symbol,
                    timeframe=self._time_frame(interval), 
                    start=self._start_time(interval),
                    asof=None,
                    feed=None,
                    asof_timezone=self.info["zone"]
                )
                
                response = getattr(client_type, method_name)(request)
                data = response.df
                
                # Data comes with timezone already handled by Alpaca API
                result[symbol] = data

            return result
            
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
        
    async def start_stream(self, currency: CurrencyType, data_type: DataType, interval: Dict) -> Optional[Dict[str, pd.DataFrame]]:
        pass
        
    async def stop_stream(self, currency: CurrencyType) -> None:
        pass
        