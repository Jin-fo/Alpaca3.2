from head import *
from module.client import Account, DataType, CurrencyType
from module.stats import Stats
from module.model import Model, LSTM


class MenuOption(Enum):
    """Menu options for the application"""
    DISPLAY_INFO = "0"
    START_STREAM = "1"
    STOP_STREAM = "2"
    FILE_HISTORICAL = "3"
    EXIT = "4"


@dataclass
class UserConfig:
    """Simple user configuration"""
    
    # API Configuration
    api_key: str = "PKE1B8WAV2KJ324ZKQKC"
    secret_key: str = "Ro7nFRclHQekQSf5Tt3zbpJAr9AaXhQ7r67sJJDy"
    paper_trading: bool = True
    
    # Trading Symbols
    crypto_symbols: List[str] = None
    stock_symbols: List[str] = None
    
    # Data Settings
    data_type: str = "bars"
    days_back: int = 7
    interval_minutes: int = 5
    
    # Account Settings
    account_name: str = "main_account"
    
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
    def alpaca_api(self) -> Dict[str, Union[str, bool]]:
        return {
            "API_KEY": self.api_key,
            "SECRET_KEY": self.secret_key,
            "paper": self.paper_trading
        }
    
    @property
    def time_config(self) -> Dict[str, Dict[str, int]]:
        return {
            "range": {"day": self.days_back, "hour": 0, "minute": 0},
            "step": {"day": 0, "hour": 0, "minute": self.interval_minutes}
        }

class Application:
    def __init__(self):
        self.config = UserConfig()
        self.account = Account(self.config.alpaca_api, self.config.account_name)
        self.stats = Stats()
    
    async def file_historical(self, data: Dict[str, pd.DataFrame]) -> None:
        for key, value in data.items():
            if value is not None and not value.empty:
                print(f"File: {key} {value}")
                self.stats.write(value)

    async def get_historical(self) -> None:
        fetch_tasks = [
            self.account.fetch_historical(CurrencyType.CRYPTO, DataType.BARS, self.config.time_config),
            self.account.fetch_historical(CurrencyType.STOCK, DataType.BARS, self.config.time_config),
        ]
        
        crypto_data, stock_data = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            
        file_tasks = [
            self.stats.write(crypto_data),
            self.stats.write(stock_data),
        ]
        
        await asyncio.gather(*file_tasks, return_exceptions=True)
    
    async def run(self) -> None:
        """Run the complete application"""
        # Focus on configured symbols
        self.account.focus(self.config.all_symbols)
        
        # Fetch historical data
        await self.get_historical()

async def main():
    """Application entry point"""

    app = Application()
    await app.run()


if __name__ == "__main__":
    asyncio.run(main())