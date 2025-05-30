from head import *
from module.client import Account, DataType, CurrencyType
from module.record import Record
from module.model import Model, LSTM
import os


@dataclass
class Parameters:
    """Simple user configuration"""
    
    # API Configuration
    api_key: str = "PKE1B8WAV2KJ324ZKQKC"
    secret_key: str = "Ro7nFRclHQekQSf5Tt3zbpJAr9AaXhQ7r67sJJDy"
    paper_trading: bool = True

    # Account Settings
    account_name: str = "main_account"

    # Record Directory/folder name
    record_folder: str = "data"

    # Trading Symbols
    crypto_symbols: List[str] = None
    stock_symbols: List[str] = None
    
    # Data Settings
    data_type: DataType = DataType.BARS

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
            "range": {"day": 0.5, "hour": 0, "minute": 0},
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
        self.account.focus(self.param.all_symbols)

        self.record = Record(self.param.record_folder)
        self.record.set_columns(self.param.column_config)

        self.crypto_data: Dict[str, pd.DataFrame] = {}
        self.stock_data: Dict[str, pd.DataFrame] = {}

    async def display_status(self) -> None:
        print("\n" + "="*40)
        print("APPLICATION STATUS")
        print("="*40)
        
        # Stream status
        status = self.account.get_stream_status()
        print(f"Streams: {status}")
        
        # Focused symbols
        crypto_symbols = self.account.focused.get(CurrencyType.CRYPTO, [])
        stock_symbols = self.account.focused.get(CurrencyType.STOCK, [])
        
        print(f"Crypto symbols: {crypto_symbols if crypto_symbols else 'None'}")
        print(f"Stock symbols: {stock_symbols if stock_symbols else 'None'}")
        
        # Data type
        print(f"Data type: {self.param.data_type.value}")
        
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

    async def file_historical(self) -> None:
        historical_tasks = [
            self.account.fetch_historical(CurrencyType.CRYPTO, self.param.data_type, self.param.time_config),
            self.account.fetch_historical(CurrencyType.STOCK, self.param.data_type, self.param.time_config),
        ]
        
        crypto_data, stock_data = await asyncio.gather(*historical_tasks, return_exceptions=True)

        write_tasks = [
            self.record.write(crypto_data) if crypto_data is not None else None,
            self.record.write(stock_data) if stock_data is not None else None
        ]
        await asyncio.gather(*write_tasks, return_exceptions=True)

    async def sample_data(self) -> None:
        data = await self.record.read(self.param.all_symbols)
        if data is None:
            print("[!] No data found in file!")
            return
        
        # Separate data by symbol type
        for symbol, df in data.items():
            if symbol in self.param.crypto_symbols:
                self.crypto_data[symbol] = df
                print(f"[o] Sampled crypto: {symbol}\n{df}")
            elif symbol in self.param.stock_symbols:
                self.stock_data[symbol] = df
                print(f"[o] Sampled stock: {symbol}\n{df}")

    async def start_stream(self) -> None:
        self.stream_running = True
        
        async def _append_tasks():
            while self.stream_running:
                if self.account.new_data and not self.account.new_data[0].empty:
                    await self.record.append(self.account.new_data[0])
                    self.account.new_data.pop(0)
                
                await asyncio.sleep(0.1)
        
        # Start the streams - these methods already create tasks internally
        await self.account.start_stream(CurrencyType.CRYPTO, self.param.data_type)
        await self.account.start_stream(CurrencyType.STOCK, self.param.data_type)
        
        # Create our append task separately
        self.append_task = asyncio.create_task(_append_tasks())
        
        # Return immediately to keep the menu responsive

    async def stop_stream(self) -> None:
        self.stream_running = False
        
        # Cancel our append task
        if hasattr(self, 'append_task') and not self.append_task.done():
            self.append_task.cancel()
            
        # This will handle cancelling the stream tasks created by the client
        await self.account.stop_stream()

    async def exit_app(self) -> int:
        print("[+] Shutting down application...")
        
        # Stop all streams first
        await self.stop_stream()
        
        # Final cleanup
        import gc
        gc.collect()
        
        print("[o] Goodbye!")
        return 0
#account protection
class Menu():

    class MenuOption(Enum):
        DISPLAY_STATUS = "0"
        FILE_HISTORICAL = "1"
        SAMPLE_DATA = "2"
        START_STREAM = "3"
        STOP_STREAM = "4"
        EXIT = "5"

    def __init__(self, app: Application):
        self.app = app
        self.menu_actions: Dict[str, Tuple[str, Callable]] = {
            self.MenuOption.DISPLAY_STATUS.value: ("Display Status", self.app.display_status),
            self.MenuOption.FILE_HISTORICAL.value: ("File Historical", self.app.file_historical),
            self.MenuOption.SAMPLE_DATA.value: ("Sample Data", self.app.sample_data),
            self.MenuOption.START_STREAM.value: ("Start Stream", self.app.start_stream),
            self.MenuOption.STOP_STREAM.value: ("Stop Stream", self.app.stop_stream),
            self.MenuOption.EXIT.value: ("Exit", self.app.exit_app)
        }

    async def select_action(self) -> str:
        return await asyncio.get_event_loop().run_in_executor(None, lambda: input("Enter your choice: ").strip())
    
    async def wait_for_user(self, message: str = "Press Enter to continue...\n") -> None:
        """Non-blocking wait for user input that doesn't interfere with streams"""
        await asyncio.get_event_loop().run_in_executor(None, lambda: input(message))
    
    async def handle_action(self, choice: str) -> Optional[str]:
        if choice in self.menu_actions:
            _, action = self.menu_actions[choice]
            return await action()
        else:
            print("[!] Invalid choice!")
            return None

    def display_menu(self) -> None:
        os.system('cls' if os.name == 'nt' else 'clear')
        for key, (description, _) in self.menu_actions.items():
            print(f" {key}. {description:<24}")


async def main():
    """Application entry point"""
    app = Application()
    menu = Menu(app)
    
    while True:
        menu.display_menu()
        try:
            choice = await menu.select_action()
            result = await menu.handle_action(choice)

            # Use async-friendly input instead of blocking os.system('pause')
            await menu.wait_for_user()
            
            if result == 0:
                break
                
        except KeyboardInterrupt:
            await app.stop_stream()
            break
        except Exception as e:
            print(f"[!] Error: {e}")
            os.system('pause')

if __name__ == "__main__":
    asyncio.run(main())