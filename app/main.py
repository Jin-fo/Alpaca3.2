from head import *
from module.client import Account, DataType, CurrencyType
from module.record import Record, Math
from module.model import Model
import os
import json

class Configuration:
    """Configuration loaded from JSON file"""

    def __init__(self):
        self.path = "app/config.json"
        self.last_mtime = 0  # Store last known modified time
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, 'r') as f:
                self._config = json.load(f)

            # API Configuration
            self.api_key = self._config['api']['key']
            self.secret_key = self._config['api']['secret']
            self.paper_trading = self._config['api']['paper']

            # Account Settings
            self.account_name = self._config['account']['name']
            self.model_name = self._config['account']['model']
            self.record_folder = self._config['account']['folders']['data']
            self.model_folder = self._config['account']['folders']['models']

            # Trading Symbols
            self.crypto_symbols = self._config['symbols']['crypto']
            self.stock_symbols = self._config['symbols']['stock']

            # Data Settings
            self.data_type = DataType[self._config['data']['type']]

            # Update last_mtime after successful load
            self.last_mtime = os.path.getmtime(self.path)
            print(f"[Info] Configuration loaded from {self.path}")
        except Exception as e:
            print(f"[!] Error loading config: {e}")

    def update(self) -> None:
        """Reload config if file was modified"""
        print("[Debug] Checking for config updates...")  # Debug print
        try:
            current_mtime = os.path.getmtime(self.path)
            if current_mtime > self.last_mtime:
                print(f"[#] Config file modified")
                self.load()

        except Exception as e:
            print(f"[!] Error updating config: {e}")
    
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
        return self._config['data']['time']
    
    @property
    def column_config(self) -> List[str]:
        return self._config['data']['columns']
    
    @property
    def lstm_config(self) -> Dict[str, Any]:
        config = self._config['model'].copy()
        # Convert layers structure to match expected format
        config['lstm_units'] = config['layers']['lstm']
        config['dense_units'] = config['layers']['dense']
        del config['layers']
        return config

class Application:
    def __init__(self):
        self.config = Configuration()

        self.account = Account(self.config.api_config, self.config.account_name)
        self.record = Record(self.config.record_folder)

        self.math = Math()
        self.model = Model(self.config.model_folder)

        self.stream_running = False
        self.model_running = False

        self.crypto_data: Dict[str, pd.DataFrame] = {}
        self.stock_data: Dict[str, pd.DataFrame] = {}
        self.update_configuration()

    def update_configuration(self) -> None:
        """Update application configuration and reset components"""
        self.config.update()
        
        # Clear existing data and reset components
        self.crypto_data.clear()
        self.stock_data.clear()
        
        # Update components with new configuration
        self.account.focus(self.config.all_symbols)
        self.record.set_columns(self.config.column_config)
        self.model.set_config(self.config.lstm_config)

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
        print(f"Data type: {self.config.data_type.value}")
        
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
    
    async def file_options(self) -> None:
        result = await self.account.fetch_options(CurrencyType.STOCK)
        await self.record.write(result) if result is not None else None

    async def price_options(self) -> None:
        chain = await self.record.read(self.config.all_symbols)
        await self.math.calculate_fair_price(chain, self.config.all_symbols)

    async def file_historical(self) -> None:
        historical_tasks = [
            self.account.fetch_historical(CurrencyType.CRYPTO, self.config.data_type, self.config.time_config),
            self.account.fetch_historical(CurrencyType.STOCK, self.config.data_type, self.config.time_config),
        ]
        
        crypto_data, stock_data = await asyncio.gather(*historical_tasks, return_exceptions=True)

        write_tasks = [
            self.record.write(crypto_data) if crypto_data is not None else None,
            self.record.write(stock_data) if stock_data is not None else None
        ]
        await asyncio.gather(*write_tasks, return_exceptions=True)

    async def load_historical(self) -> None:
        data = await self.record.read(self.config.all_symbols)
        if data is None:
            print("[!] No data found in file!")
            return
        
        # Separate data by symbol type
        for symbol, df in data.items():
            if symbol in self.config.crypto_symbols:
                self.crypto_data[symbol] = df
            elif symbol in self.config.stock_symbols:
                self.stock_data[symbol] = df
                
            # Display sample data in a clean format
            print(f"\n{'='*80}")
            print(f"Historical Data for {symbol}")
            print('='*80)
            
            # Format numeric columns
            pd.set_option('display.float_format', lambda x: '%.2f' % x)
            
            # Display first and last few rows
            print("\nFirst 5 rows:")
            print('-'*80)
            print(df.head().to_string())
            
            print("\nLast 5 rows:")
            print('-'*80)
            print(df.tail().to_string())
            
            # Display basic statistics
            print("\nBasic Statistics:")
            print('-'*80)
            print(df.describe().to_string())
            print('='*80)

    async def update_tasks(self) -> None:
        while self.stream_running:
            try:
                if not self.account.new_data or self.account.new_data[0].empty:
                    await asyncio.sleep(0.1)
                    continue

                current_data = self.account.new_data[0]
                symbol = current_data.index[0][0]  # Get symbol from MultiIndex
                
                # Append new data
                await self.record.append(current_data)
                self.account.new_data.pop(0)
                
                # Make prediction if model is running
                if self.model_running:
                    read_data = await self.record.read([symbol])
                    if read_data:
                        await self.model.predict(read_data[symbol])
                
                # Remove processed data
            except Exception as e:
                print(f"[!] Error in update task: {e}")
                await asyncio.sleep(1)  # Longer sleep on error

    async def run_stream(self) -> None:
        self.stream_running = True
        
        # Start the streams - these methods already create tasks internally
        await self.account.start_stream(CurrencyType.CRYPTO, self.config.data_type)
        await self.account.start_stream(CurrencyType.STOCK, self.config.data_type)
        
        # Create our append task separately
        self.append_task = asyncio.create_task(self.update_tasks())
        
    async def stop_stream(self) -> None:
        self.stream_running = False
        
        # Cancel our append task
        if hasattr(self, 'append_task') and not self.append_task.done():
            self.append_task.cancel()
            
        # This will handle cancelling the stream tasks created by the client
        await self.account.end_stream()
    
    async def run_model(self) -> None:
        self.model_running = True
        build_tasks = []
        for df in self.crypto_data.values():
            build_tasks.append(self.model.create(df, self.config.lstm_config))

        for df in self.stock_data.values():
            build_tasks.append(self.model.create(df, self.config.lstm_config))

        await asyncio.gather(*build_tasks, return_exceptions=True)

    async def verify_model(self) -> None:
        test_tasks = []
        for symbol in self.crypto_data.keys():
            test_tasks.append(self.model.assess(symbol))

        for symbol in self.stock_data.keys():
            test_tasks.append(self.model.assess(symbol))

        await asyncio.gather(*test_tasks, return_exceptions=True)

    async def stop_model(self) -> None:
        self.model_running = False
        self.model.save()

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
        DISPLAY_STATUS = "I"
        AUTO_START = "A"
        ANALYZE_OPTIONS = "B"
        FILE_HISTORICAL = "1"   
        LOAD_HISTORICAL = "2"
        RUN_STREAM = "3"
        STOP_STREAM = "4"
        RUN_MODEL = "5"
        VERIFY_MODEL = "6"
        STOP_MODEL = "7"
        EXIT = "8"

    def __init__(self, app: Application):
        self.app = app
        self.menu_actions: Dict[str, Tuple[str, Callable]] = {
            self.MenuOption.DISPLAY_STATUS.value: ("Display Status", self.app.display_status),
            self.MenuOption.AUTO_START.value: ("Auto Start", self.auto_start),
            self.MenuOption.ANALYZE_OPTIONS.value: ("Analyze Options", self.analyze_options),
            self.MenuOption.FILE_HISTORICAL.value: ("File Historical", self.app.file_historical),
            self.MenuOption.LOAD_HISTORICAL.value: ("Load Historical", self.app.load_historical),
            self.MenuOption.RUN_STREAM.value: ("Run Stream", self.app.run_stream),
            self.MenuOption.STOP_STREAM.value: ("Stop Stream", self.app.stop_stream),
            self.MenuOption.RUN_MODEL.value: ("Run Model", self.app.run_model),
            self.MenuOption.VERIFY_MODEL.value: ("Verify Model", self.app.verify_model),
            self.MenuOption.STOP_MODEL.value: ("Stop Model", self.app.stop_model),
            self.MenuOption.EXIT.value: ("Exit", self.app.exit_app)
        }

    async def auto_start(self) -> None:
        await self.app.file_historical()
        await self.app.load_historical()
        await self.app.run_model()
        await self.app.verify_model()
        await self.app.run_stream()

    async def analyze_options(self) -> None:
        await self.app.file_options()
        await self.app.price_options()

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
        app.update_configuration()
        menu.display_menu()
        
        # Ensure this line is executed
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