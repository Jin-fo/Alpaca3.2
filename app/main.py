from head import *
from module.client import Account
from module.stats import Stats
from module.model import Model, LSTM


class MenuOption(Enum):
    """Menu options for the application"""
    START_STREAM = "1"
    STOP_STREAM = "2"
    FILE_HISTORICAL = "3"
    EXIT = "4"


@dataclass
class AppConfig:
    """Application configuration"""
    api_key: str = "PKE1B8WAV2KJ324ZKQKC"
    secret_key: str = "Ro7nFRclHQekQSf5Tt3zbpJAr9AaXhQ7r67sJJDy"
    paper: bool = True
    symbols: List[str] = None
    data_type: str = "bars"
    
    def __post_init__(self):
        if self.symbols is None:
            self.symbols = ["BTC/USD", "NVDA", "AAPL"]
    
    @property
    def client_config(self) -> Dict[str, str]:
        return {
            "API_KEY": self.api_key,
            "SECRET_KEY": self.secret_key,
            "paper": self.paper
        }
    
    @property
    def time_interval(self) -> Dict:
        return {
            "range": {"day": 1, "hour": 0, "minute": 0},
            "step": {"day": 0, "hour": 0, "minute": 1}
        }


class Application:
    """Market data streaming and analysis application"""
    
    def __init__(self, config: Optional[AppConfig] = None):
        self.config = config or AppConfig()
        self.account = Account(self.config.client_config, "Paper Account")
        self._setup_menu_actions()

    def _setup_menu_actions(self) -> None:
        """Setup menu action mappings"""
        self.menu_actions: Dict[str, Tuple[str, Callable]] = {
            MenuOption.START_STREAM.value: ("Start Stream", self.start_streams),
            MenuOption.STOP_STREAM.value: ("Stop Stream", self.stop_streams),
            MenuOption.FILE_HISTORICAL.value: ("File Historical", self.fetch_historical_data),
            MenuOption.EXIT.value: ("Exit", self._exit_application)
        }

    def display_account_info(self) -> None:
        """Display account information"""
        print("-" * 30)
        self.account.account_info()
        print("-" * 30)

    def _clean_data(self, data, timezone: str, columns: List[str]) -> pd.DataFrame:
        """Convert data to DataFrame with timezone handling"""
        try:
            # Try DataFrame from data object first
            df = data.df.reset_index() if hasattr(data, 'df') else self._create_fallback_dataframe(data, columns)
            
            # Filter to specified columns
            result = pd.DataFrame({col: df[col] for col in columns if col in df.columns})
            
            # Handle timezone conversion
            return self._process_timestamps(result, timezone)
            
        except Exception as e:
            print(f"[!] Data cleaning error: {e}")
            return pd.DataFrame()

    def _create_fallback_dataframe(self, data, columns: List[str]) -> pd.DataFrame:
        """Create DataFrame from individual data attributes"""
        result = pd.DataFrame()
        result['timestamp'] = [data.timestamp]
        for col in columns:
            if col != 'timestamp':
                result[col] = [getattr(data, col, 0)]
        return result

    def _process_timestamps(self, df: pd.DataFrame, timezone: str) -> pd.DataFrame:
        """Process timestamp column for timezone conversion"""
        # Find timestamp column
        time_col_idx = next(
            (i for i, col in enumerate(df.columns) 
             if pd.api.types.is_datetime64_any_dtype(df.iloc[:, i])), 0
        )
        
        timestamp_col = df.columns[time_col_idx]
        timestamps = pd.to_datetime(df[timestamp_col])
        
        # Ensure timezone info
        if timestamps.dt.tz is None:
            timestamps = timestamps.dt.tz_localize('UTC')
        
        # Convert and format
        local_timestamps = timestamps.dt.tz_convert(timezone)
        df['timestamp'] = local_timestamps.dt.strftime('%Y-%m-%d %H:%M:%S')
        
        return df.set_index('timestamp')

    async def fetch_historical_data(self) -> None:
        """Fetch historical data for focused symbols"""
        print("[+] Fetching historical data...")
        
        tasks = [
            self._fetch_symbol_group_data("crypto", self.account.focused["crypto"]),
            self._fetch_symbol_group_data("stock", self.account.focused["stock"])
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _fetch_symbol_group_data(self, symbol_type: str, symbols: List[str]) -> None:
        """Fetch data for a specific symbol group"""
        if not symbols:
            return
            
        print(f"[+] {symbol_type.title()}: {', '.join(symbols)}")
        
        try:
            history_method = getattr(self.account, f"{symbol_type}_history")
            data = history_method(self.config.data_type, self.config.time_interval)
            
            if data is not None and not data.empty:
                print(f"[o] {symbol_type.title()}: {len(data)} records")
            else:
                print(f"[!] No {symbol_type} historical data available")
                
        except Exception as e:
            print(f"[!] Error fetching {symbol_type} data: {e}")

    async def start_streams(self) -> None:
        """Start streaming for focused symbols"""
        if self.account.active_streams:
            print("[!] Stream already running!")
            return

        stream_tasks = [
            ("crypto", self.account.focused["crypto"], self.account.crypto_stream),
            ("stock", self.account.focused["stock"], self.account.stock_stream)
        ]
        
        started_any = False
        for stream_type, symbols, stream_method in stream_tasks:
            if symbols:
                print(f"[+] {stream_type.title()}: {', '.join(symbols)}")
                await stream_method(self.config.data_type, symbols)
                started_any = True
                if stream_type == "crypto":  # Small delay between crypto and stock
                    await asyncio.sleep(0.1)

        print("[o] Streams started" if started_any else "[!] No symbols to stream")

    async def stop_streams(self) -> None:
        """Stop all active streams"""
        if not self.account.active_streams:
            print("[!] No streams to stop")
            return
            
        print("[-] Stopping streams...")
        await self.account.stop_stream()

    def _display_menu(self) -> None:
        """Display the application menu"""
        status = self._get_stream_status()
        
        print(f"\n┌─────────────────────────────┐")
        print(f"     STATUS: {status:<12} ")
        print(f"├─────────────────────────────┤")
        for option, (description, _) in self.menu_actions.items():
            print(f"│ {option}. {description:<23} │")
        print(f"└─────────────────────────────┘")

    def _get_stream_status(self) -> str:
        """Get current streaming status"""
        self.account.get_stream_status()
        active_count = len(self.account.active_streams)
        
        if active_count == 0:
            return "STOPPED"
        
        crypto_count = len(self.account.focused["crypto"]) if self.account.focused["crypto"] else 0
        stock_count = len(self.account.focused["stock"]) if self.account.focused["stock"] else 0
        return f"ACTIVE ({crypto_count} crypto, {stock_count} stock)"

    async def _get_user_choice(self) -> str:
        """Get user menu choice asynchronously"""
        return await asyncio.get_event_loop().run_in_executor(
            None, lambda: input().strip()
        )

    async def _handle_menu_choice(self, choice: str) -> Optional[str]:
        """Handle user menu choice"""
        if choice in self.menu_actions:
            _, action = self.menu_actions[choice]
            return await action()
        else:
            print("[!] Invalid choice!")
            return None

    async def run_menu_loop(self) -> None:
        """Main menu loop"""
        while True:
            self._display_menu()
            
            try:
                choice = await self._get_user_choice()
                result = await self._handle_menu_choice(choice)
                
                if result == "exit":
                    break
                    
                await asyncio.sleep(0.1)  # Small delay to prevent console spam
                
            except KeyboardInterrupt:
                await self.stop_streams()
                break

    async def _exit_application(self) -> str:
        """Gracefully exit the application"""
        await self.stop_streams()
        print("[o] Goodbye!")
        return "exit"

    async def run(self) -> None:
        """Run the complete application"""
        # Focus on configured symbols
        self.account.focus(self.config.symbols)
        
        # Start menu loop
        await self.run_menu_loop()


async def main():
    """Application entry point"""
    config = AppConfig()
    app = Application(config)
    
    app.display_account_info()
    await app.run()


if __name__ == "__main__":
    asyncio.run(main()) 