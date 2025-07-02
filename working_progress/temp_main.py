from head import *
from module.client import Account, DataType, MarketType
from module.record import Record, Math
from module.model import Model
import json

class Configuration:
    def __init__(self):
        self.path = "app/config.json"
        self.last_mtime = 0
        self.load()
    
    def load(self) -> None:
        try:
            with open(self.path, 'r') as f:
                self._config = json.load(f)
            
            self.account_entry = self._config['account']
            self.record_entry = self._config['record']
            self.model_entry = self._config['model']

            # Extract additional properties
            self.crypto_symbols = self.account_entry['investment']['crypto']
            self.stock_symbols = self.account_entry['investment']['stock']
            self.option_symbols = self.account_entry['investment']['option']
            self.data_type = DataType[self.record_entry['market']['regular']['type']]

            print(f"[o] Configuration loaded from {self.path}")
        except Exception as e:
            print(f"[!] Error loading config: {e}")

    def update(self) -> bool:
        try:
            current_mtime = os.path.getmtime(self.path)
            if current_mtime > self.last_mtime:
                print(f"[<] Updating Configuration from {self.path}")
                self.load()
                self.last_mtime = current_mtime
                return True
            return False
        except Exception as e:
            print(f"[!] Error updating config: {e}")
            return False
    
    @property
    def account(self) -> Dict[str, Any]:
        return self.account_entry
    
    @property
    def record(self) -> Dict[str, Any]:
        return self.record_entry
    
    @property
    def model(self) -> Dict[str, Any]:
        return self.model_entry

class Application:
    def __init__(self):
        self.config = Configuration()
        self.account = Account()
        self.record = Record()
        
        self.model = Model()

        #flags
        self.stream_running = False
        self.model_running = False

        #data
        self.crypto_data: Dict[str, pd.DataFrame] = {}
        self.stock_data: Dict[str, pd.DataFrame] = {}
        self.option_data: Dict[str, pd.DataFrame] = {}

    def update_configuration(self) -> bool:
        if self.config.update():
            self.account.load(self.config.account)
            self.record.load(self.config.record)
            self.model.load(self.config.model)
            return True
        return False

    async def display_status(self) -> None:
        print("\n" + "="*40)
        print("APPLICATION STATUS")
        print("="*40)
        
        # Stream status
        status = self.account.get_stream_status()
        print(f"Streams: {status}")
        
        # Focused symbols
        crypto_symbols = self.account.assets.get(MarketType.CRYPTO, [])
        stock_symbols = self.account.assets.get(MarketType.STOCK, [])
        
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
    # async def price_options(self) -> None:
    #     # Only calculate prices if there are symbols configured
    #     if not self.config.all_symbols:
    #         print("[!] No symbols configured for price calculation!")
    #         print(f"All symbols: {self.config.all_symbols}")
    #         return
            
    #     chain = await self.record.read(self.config.all_symbols)
    #     if chain is None:
    #         print("[!] No option chain data found!")
    #         return
            
    #     await self.math.calculate_fair_price(chain, self.config.all_symbols)

    async def file_historical(self) -> None:
        historical_tasks = {}
        market = self.config.record["market"] 
        
        # Only add stock task if there are stock symbols
        if self.config.stock_symbols:
            historical_tasks[MarketType.STOCK] = self.account.fetch_historical(MarketType.STOCK, DataType[market["regular"]["type"]], market["regular"]["time"])

        # Only add crypto task if there are crypto symbols
        if self.config.crypto_symbols:
            historical_tasks[MarketType.CRYPTO] = self.account.fetch_historical(MarketType.CRYPTO, DataType[market["regular"]["type"]], market["regular"]["time"])

        # Only add option task if there are option symbols
        if self.config.option_symbols:  # Options are based on stock symbols
            historical_tasks[MarketType.OPTION] = self.account.fetch_historical(MarketType.OPTION, DataType[market["option"]["type"]], market["option"]["expiration"])
        
        # Execute all tasks and create write tasks in one pass
        write_tasks = []
        
        for market_type, task in historical_tasks.items():
            try:
                result = await task
                
                if result is not None and not isinstance(result, Exception) and isinstance(result, dict) and result:
                    write_tasks.append(self.record.write(market_type.value, result))
                else:
                    print(f"[!] Result {market_type} is empty or invalid")
                    
            except Exception as e:
                print(f"[!] Result {market_type} failed: {e}")
        
        if write_tasks:
            await asyncio.gather(*write_tasks, return_exceptions=True)
        else:
            print("[!] No valid data to write!")

    async def load_historical(self) -> None:
     
        read_tasks = []
        read_tasks.append(self.record.read(MarketType.STOCK.value, self.config.stock_symbols))
        read_tasks.append(self.record.read(MarketType.CRYPTO.value, self.config.crypto_symbols))
        read_tasks.append(self.record.read(MarketType.OPTION.value, self.config.option_symbols))

        results = await asyncio.gather(*read_tasks, return_exceptions=True)

        # Process results for each market type
        stock_data, crypto_data, option_data = results
        
        # Process stock data
        if isinstance(stock_data, dict) and stock_data:
            for symbol, df in stock_data.items():
                self.stock_data[symbol] = df
                print(f"[+] Loaded stock data for {symbol}")
        
        # Process crypto data
        if isinstance(crypto_data, dict) and crypto_data:
            for symbol, df in crypto_data.items():
                self.crypto_data[symbol] = df
                print(f"[+] Loaded crypto data for {symbol}")
        
        # Process option data
        if isinstance(option_data, dict) and option_data:
            for symbol, df in option_data.items():
                self.option_data[symbol] = df
                print(f"[+] Loaded option data for {symbol}")
        
        # Check if any data was loaded
        total_loaded = len(self.stock_data) + len(self.crypto_data) + len(self.option_data)
        if total_loaded == 0:
            print("[!] No data found in files!")
        else:
            print(f"[+] Successfully loaded data for {total_loaded} symbols")

    async def update_tasks(self) -> None:
        while self.stream_running:
            try:
                if not self.account.client.new_data or self.account.client.new_data[0].empty:
                    await asyncio.sleep(0.1)
                    continue

                current_data = self.account.client.new_data[0]
                symbol = current_data.index[0][0]  # Get symbol from MultiIndex
                
                # Append new data
                await self.record.append(MarketType.CRYPTO.value, current_data)
                self.account.client.new_data.pop(0)
                
                # Make prediction if model is running
                if self.model_running:
                    read_data = await self.record.read(MarketType.CRYPTO.value, [symbol])
                    if read_data:
                        await self.model.predict(read_data[symbol])
                
                # Remove processed data
            except Exception as e:
                print(f"[!] Error in update task: {e}")
                await asyncio.sleep(1)  # Longer sleep on error

    async def run_stream(self) -> None:
        self.stream_running = True
        
        # Only start crypto stream if there are crypto symbols
        if self.config.crypto_symbols:
            await self.account.start_stream(MarketType.CRYPTO, self.config.data_type)
        
        # Only start stock stream if there are stock symbols
        if self.config.stock_symbols:
            await self.account.start_stream(MarketType.STOCK, self.config.data_type)
        
        # If no symbols are configured, show a message
        if not self.config.crypto_symbols and not self.config.stock_symbols:
            print("[!] No symbols configured for streaming!")
            print(f"Crypto symbols: {self.config.crypto_symbols}")
            print(f"Stock symbols: {self.config.stock_symbols}")
            self.stream_running = False
            return
        
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
        
        # Only create models for crypto if there is crypto data
        if self.crypto_data:
            for symbol, df in self.crypto_data.items():
                build_tasks.append(self.model.create(df, self.config.model, symbol))

        # Only create models for stock if there is stock data
        if self.stock_data:
            for symbol, df in self.stock_data.items():
                build_tasks.append(self.model.create(df, self.config.model, symbol))

        # If no data is available, show a message
        if not build_tasks:
            print("[!] No data available for model creation!")
            print(f"Crypto data: {len(self.crypto_data)} symbols")
            print(f"Stock data: {len(self.stock_data)} symbols")
            self.model_running = False
            return

        await asyncio.gather(*build_tasks, return_exceptions=True)

    async def verify_model(self) -> None:
        test_tasks = []
        
        # Only assess crypto models if there is crypto data
        if self.crypto_data:
            for symbol in self.crypto_data.keys():
                test_tasks.append(self.model.assess(symbol))

        # Only assess stock models if there is stock data
        if self.stock_data:
            for symbol in self.stock_data.keys():
                test_tasks.append(self.model.assess(symbol))

        # If no data is available, show a message
        if not test_tasks:
            print("[!] No data available for model verification!")
            print(f"Crypto data: {len(self.crypto_data)} symbols")
            print(f"Stock data: {len(self.stock_data)} symbols")
            return

        await asyncio.gather(*test_tasks, return_exceptions=True)

    async def stop_model(self) -> None:
        self.model_running = False
    #     self.model.save()

    async def stop_stream(self) -> None:
        """Stop all streams - placeholder for when streams are not implemented"""
        print("[o] No active streams to stop")

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
    await menu.wait_for_user()
    
    while True:
        if app.update_configuration():
            await menu.wait_for_user()

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