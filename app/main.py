from head import *
from module.client import Account, DataType, CurrencyType
from module.record import Record
from module.model import Model, LSTM


class MenuOption(Enum):
    """Menu options for the application"""
    DISPLAY_INFO = "0"
    START_STREAM = "1"
    STOP_STREAM = "2"
    FILE_HISTORICAL = "3"
    EXIT = "4"

@dataclass
class Parameters:
    """Simple user configuration"""
    
    # API Configuration
    api_key: str = "PKE1B8WAV2KJ324ZKQKC"
    secret_key: str = "Ro7nFRclHQekQSf5Tt3zbpJAr9AaXhQ7r67sJJDy"
    paper_trading: bool = True
    
    # Trading Symbols
    crypto_symbols: List[str] = None
    stock_symbols: List[str] = None
    
    # Data Settings
    data_type: DataType = DataType.BARS

    # Account Settings
    account_name: str = "main_account"
    
    # Record Directory
    record_folder: str = "data"
    def __post_init__(self):
        self.crypto_symbols = ["BTC/USD", "ETH/USD"]
        self.stock_symbols = ["NVDA", "AAPL"]
    
    def update(self, **kwargs) -> None:
        """Update multiple fields at once"""
        for field, value in kwargs.items():
            if hasattr(self, field):
                setattr(self, field, value)
    
    @property
    def all_symbols(self) -> List[str]:
        return self.crypto_symbols + self.stock_symbols
    
    @property
    def api_config(self) -> Dict[str, Union[str, bool]]:
        return {
            "API_KEY": self.api_key,
            "SECRET_KEY": self.secret_key,
            "paper": self.paper_trading
        }
    
    @property
    def time_config(self) -> Dict[str, Dict[str, int]]:
        return {
            "range": {"day": 7, "hour": 0, "minute": 0},
            "step": {"day": 0, "hour": 0, "minute": 5}
        }
    
    @property
    def column_config(self) -> List[str]:
        return ["timestamp", "open", "high", "low", "close"] 
    # bar: timestamp, open, high, low, close, volume, trade_count, vwap
    # quote: timestamp, ask, bid, ask_size, bid_size
    # trade: timestamp, price, size, exchange

class Application:
    def __init__(self):
        self.param = Parameters()
        self.account = Account(self.param.api_config, self.param.account_name)
        self.record = Record(self.param.record_folder)
    
    async def get_historical(self) -> None:
        fetch_tasks = [
            self.account.fetch_historical(CurrencyType.CRYPTO, self.param.data_type, self.param.time_config),
            self.account.fetch_historical(CurrencyType.STOCK, self.param.data_type, self.param.time_config),
        ]
        
        crypto_data, stock_data = await asyncio.gather(*fetch_tasks, return_exceptions=True)
        
        write_tasks = []
        if crypto_data and not isinstance(crypto_data, Exception):
            write_tasks.append(self.record.write(crypto_data))
        if stock_data and not isinstance(stock_data, Exception):
            write_tasks.append(self.record.write(stock_data))
        
        if write_tasks:
            await asyncio.gather(*write_tasks, return_exceptions=True)
 
        # Read back all symbols
        read_data = await self.record.read(self.param.all_symbols)
        print(read_data)
    
    async def run(self) -> None:
        """Run the complete application"""
        # Focus on configured symbols
        self.account.focus(self.param.all_symbols)
        
        # Fetch historical data
        self.record.set_columns(self.param.column_config)
        await self.get_historical()

async def main():
    """Application entry point"""

    app = Application()
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())