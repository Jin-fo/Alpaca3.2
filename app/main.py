from head import *
from module.account import *
from module.record import *
from module.model import *

import questionary

class Configuration:
    def __init__(self):
        self.path = "app/config.json"
        self.last_mtime = 0
        self._account_args = None
        self._record_args = None
        self._model_args = None
        self._load()

    def _load(self):
        try:
            with open(self.path, 'r') as f:
                self._config = json.load(f)

            self._account_args = self._config['account']
            self._record_args = self._config['record']
            self._model_args = self._config['model']

        except Exception as e:
            print(f"[!] Error loading config: {e}")

    def has_update(self):
        try:
            current_mtime = os.path.getmtime(self.path)
            if current_mtime > self.last_mtime:
                self._load()
                self.last_mtime = current_mtime
                return True
            else:
                return False
        except Exception as e:
            print(f"[!] Error updating config: {e}")
            return False
        
    @property
    def account_args(self):
        return self._account_args
    
    @property
    def record_args(self):
        return self._record_args
    
    @property
    def model_args(self):
        return self._model_args

class Application:

    class Flag(Enum):
        IS_CONFIGURED = auto()
        IS_BROWSING = auto()
        IS_RETRIEVING = auto()
        IS_PREDICTING = auto()
        IS_DECIDING = auto()

    def _check(self, flag: Flag) -> bool:
        return flag in self.active_flags
    
    def __init__(self):
        self.config = Configuration()
        self.account = Account()
        self.record = Record()
        self.model = Model()

        self.active_flags : set[self.Flag] = set()
        asyncio.create_task(self.controller_loop(), name="Controller")

    def updating_configuration(self):
        if self.config.has_update():
            self.account.load(self.config.account_args)
            self.record.load(self.config.record_args)
            self.model.load(self.config.model_args)
            self.active_flags.add(self.Flag.IS_CONFIGURED)
            
        else:
            self.active_flags.discard(self.Flag.IS_CONFIGURED)
            
        return self._check(self.Flag.IS_CONFIGURED)

    async def controller_loop(self):
        perdicted = False
        while self._check(self.Flag.IS_CONFIGURED):

            if self._check(self.Flag.IS_BROWSING):
                pass

            if self._check(self.Flag.IS_RETRIEVING):
                crypto_data, stock_data, option_data = await asyncio.gather(
                    self.account.historical.pop_new_data(MarketType.CRYPTO),
                    self.account.historical.pop_new_data(MarketType.STOCK),
                    self.account.historical.pop_new_data(MarketType.OPTION)
                )

                if crypto_data:
                    await self.record.write(MarketType.CRYPTO.value, crypto_data)
                if stock_data:
                    await self.record.write(MarketType.STOCK.value, stock_data)
                if option_data:
                    await self.record.write(MarketType.OPTION.value, option_data)
                
                perdicted = False

            if self._check(self.Flag.IS_PREDICTING) and not perdicted:
                crypto_data = await self.record.read(MarketType.CRYPTO.value, self.account.investment.get("crypto", []))
                stock_data = await self.record.read(MarketType.STOCK.value, self.account.investment.get("stock", []))
                option_data = await self.record.read(MarketType.OPTION.value, self.account.investment.get("option", []))

                for symbol, df in crypto_data.items():
                    if df is not None and not df.empty:
                        self.model.operate(df, symbol)
                
                for symbol, df in stock_data.items():
                    if df is not None and not df.empty:
                        self.model.operate(df, symbol)
                
                perdicted = True

            if self._check(self.Flag.IS_DECIDING):
                pass

            await asyncio.sleep(0.1)

    async def run_news(self):
        print("[!] News Not implemented")
        pass

    async def stop_news(self):
        print("[!] News Not implemented")
        pass
    
    async def run_history(self):
        historical_tasks = []
        task_types = []

        if self.account.investment.get("stock"):
            historical_tasks.append(self.account.fetch_historical(MarketType.STOCK))
            task_types.append(MarketType.STOCK)

        if self.account.investment.get("crypto"):
            historical_tasks.append(self.account.fetch_historical(MarketType.CRYPTO))
            task_types.append(MarketType.CRYPTO)

        if self.account.investment.get("option"):
            historical_tasks.append(self.account.fetch_historical(MarketType.OPTION))
            task_types.append(MarketType.OPTION)

        if historical_tasks:
            results = await asyncio.gather(*historical_tasks, return_exceptions=True)

        self.active_flags.add(self.Flag.IS_RETRIEVING)

        write_tasks = []
        for i, result in enumerate(results):
            if result and not isinstance(result, Exception):
                write_tasks.append(self.record.write(task_types[i].value, result))

        if write_tasks:
            await asyncio.gather(*write_tasks, return_exceptions=True)
    
    async def stop_history(self):
        await self.account.stop_historical()
        self.active_flags.discard(self.Flag.IS_RETRIEVING)

    
    async def run_models(self):
        # Get symbols from account configuration
        crypto_symbols = self.account.investment.get("crypto", [])
        stock_symbols = self.account.investment.get("stock", [])
        
        crypto_data = await self.record.read(MarketType.CRYPTO.value, crypto_symbols)
        stock_data = await self.record.read(MarketType.STOCK.value, stock_symbols)

        for symbol, df in crypto_data.items():
            if df is not None and not df.empty:
                self.model.create(df, symbol)

        for symbol, df in stock_data.items():
            if df is not None and not df.empty:
                self.model.create(df, symbol)

        self.active_flags.add(self.Flag.IS_PREDICTING)
    
    async def stop_models(self):
        self.active_flags.discard(self.Flag.IS_PREDICTING)
    
    async def run_order(self):
        print("[!] Order Not implemented")
        pass

    async def stop_order(self):
        print("[!] Order Not implemented")
        pass

    async def display_status(self):
        print("\n" + "="*60)
        print("APPLICATION STATUS".center(60))
        print("="*60)
        
        print(f"Account: {self.account.name}")
        print(f"Location: {self.account.location}")
        
        # Background process status
        print(f"\nBackground Processes:")
        print(f"  Historical Data Collection: {'Active' if self._check(self.Flag.IS_RETRIEVING) else 'Inactive'}")
        print(f"  Model Prediction: {'Active' if self._check(self.Flag.IS_PREDICTING) else 'Inactive'}")
        print(f"  News Browsing: {'Active' if self._check(self.Flag.IS_BROWSING) else 'Inactive'}")
        print(f"  Order Processing: {'Active' if self._check(self.Flag.IS_DECIDING) else 'Inactive'}")
        
        # Component status
        try:
            self.account.stream.status()
            print("Periodic Latest:")
            self.account.historical.status()
        except Exception as e:
            print(f"Status Error: {e}")
        
        # Investment symbols
        print(f"\nInvestment Symbols:")
        for market_type, symbols in self.account.investment.items():
            symbol_list = ', '.join(symbols) if symbols else 'None'
            print(f"  {market_type.title()}: {symbol_list}")
        
        # Task status
        all_tasks = asyncio.all_tasks()
        running_tasks = [task for task in all_tasks if not task.done()]
        print(f"\nTasks: Running={len(running_tasks)}, Total={len(all_tasks)}")
        
        if running_tasks:
            print("  Running Tasks:")
            for i, task in enumerate(running_tasks, 1):
                # Try to get the task name
                task_name = None
                if hasattr(task, 'get_name'):
                    task_name = task.get_name()
                
                # If no name or default name, try to extract from coroutine
                if not task_name or task_name.startswith("Task-"):
                    if hasattr(task, '_coro'):
                        coro_name = task._coro.__name__ if hasattr(task._coro, '__name__') else "Unknown"
                        task_name = f"{coro_name}-{i}"
                    else:
                        task_name = f"Background-{i}"
                
                print(f"    {i}. {task_name}")
        
        print("="*60)

class Menu:

    class Option(Enum):
        START = auto()
        TOGGLE_Browse = auto()
        TOGGLE_Retrieve = auto()
        TOGGLE_Predict = auto()
        TOGGLE_Decide = auto()
        RESET = auto()
        EXIT = auto()
        
    def __init__(self, app: Application):
        self.app = app

    def get_window(self):
        return [
            (self.Option.START, "Start"),
            (self.Option.TOGGLE_Browse, f"  [{'+' if self.app._check(self.app.Flag.IS_BROWSING) else '-'}] Browse News"),
            (self.Option.TOGGLE_Retrieve, f"  [{'+' if self.app._check(self.app.Flag.IS_RETRIEVING) else '-'}] Retrieve Data"),
            (self.Option.TOGGLE_Predict, f"  [{'+' if self.app._check(self.app.Flag.IS_PREDICTING) else '-'}] Predict Trend"),
            (self.Option.TOGGLE_Decide, f"  [{'+' if self.app._check(self.app.Flag.IS_DECIDING) else '-'}] Decide Order"),
            (None, "─"*60),
            (self.Option.RESET, "Reset"),
            (self.Option.EXIT, "Exit")
        ]

    async def pause(self):
        await asyncio.get_event_loop().run_in_executor(None, lambda: input("[Menu] Press 'Enter' to continue..."))
        os.system('cls' if os.name == 'nt' else 'clear')

    async def refresh(self):
        if self.app.updating_configuration():
            await self.pause()
        
        else:
            await self.pause()

        await self.app.display_status()

    async def select_action(self):
        loop = asyncio.get_event_loop()
        window = self.get_window()
        selected_label = await loop.run_in_executor(
            None,
            lambda: questionary.select(
                "Select an action:",
                choices=[label for _, label in window]
            ).ask()
        )
        
        # Find the corresponding option for the selected label
        for option, label in window:
            if label == selected_label:
                return option
        return None

    async def handle_action(self, choice: Option):
        match choice:
            case self.Option.START:
                await self.app.run_history()

                await asyncio.sleep(0.1)

                await self.app.run_models()

            case self.Option.TOGGLE_Browse:
                if self.app._check(self.app.Flag.IS_BROWSING):
                    await self.app.stop_news()
                else:
                    await self.app.run_news()

            case self.Option.TOGGLE_Retrieve:
                if self.app._check(self.app.Flag.IS_RETRIEVING):
                    await self.app.stop_history()
                else:
                    await self.app.run_history()

            case self.Option.TOGGLE_Predict:
                if self.app._check(self.app.Flag.IS_PREDICTING):
                    await self.app.stop_models()
                else:
                    await self.app.run_models()

            case self.Option.TOGGLE_Decide:
                if self.app._check(self.app.Flag.IS_DECIDING):
                    await self.app.stop_order()
                else:
                    await self.app.run_order()

            case self.Option.RESET:
                await self.app.stop_news()
                await asyncio.sleep(0.1)

                await self.app.stop_history()
                await asyncio.sleep(0.1)

                await self.app.stop_models()
                await asyncio.sleep(0.1)

                await self.app.stop_order()
                await asyncio.sleep(0.1)
                gc.collect()

            case self.Option.EXIT:
                return 0

async def main():
    app = Application()
    menu = Menu(app)

    version = datetime.now().strftime('v%Y.%m.%d')
    print("=" * 60)
    print()
    print("SMART TRADE TERMINAL".center(60))
    print("Powered by Alpaca API & Keras ML Framework".center(60))
    print(f"{version}".center(60))
    print()
    print(("-"*50).center(60))
    print()
    print("A commission-free trading infrastructure ".center(60))
    print("for stocks & crypto, leveraging advanced ".center(60))
    print("neural networks built on top of TensorFlow.".center(60))
    print()
    print("=" * 60)
    await menu.pause()

    while True:
        await menu.refresh()

        try:    
            choice = await menu.select_action()
            if choice is None:
                continue  # User cancelled selection
            response = await menu.handle_action(choice)
            if response == 0:
                break

        except KeyboardInterrupt:
            print("\n[!] Interrupted by user")
            break
        except Exception as e:
            print(f"[!] Error: {e}")
            await menu.pause()
    
if __name__ == "__main__":
    asyncio.run(main())








































# class Application:
#     def __init__(self):
#         self.config = Configuration()
#         self.account = Account()
#         self.record = Record()
#         self.model = Model()

#         self.is_browsing : bool = False
#         self.is_streaming : bool = False
#         self.is_retrieving : bool = False
#         self.is_analyzing : bool = False #ploting, 
#         self.is_predicting : bool = False
#         self.is_deciding : bool = False #order, buy, sell

#         asyncio.create_task(self._data_pipeline_loop(), name="DataPipelineLoop")
        
#     def update_configuration(self):
#         if self.config.update():
#             self.account.load(self.config.account_args)
#             self.record.load(self.config.record_args)
#             self.model.load(self.config.model_args)
#             return True
#         return False
    
#     async def _data_pipeline_loop(self):
#         predicted = False
#         timestamp = lambda: datetime.now(ZoneInfo(self.account.location)).strftime('%H:%M:%S')

#         while True:
#             if self.is_browsing:
#                 pass

#             if self.is_retrieving:
#                 crypto_data, stock_data, option_data = await asyncio.gather(
#                     self.account.historical.pop_new_data(MarketType.CRYPTO),
#                     self.account.historical.pop_new_data(MarketType.STOCK),
#                     self.account.historical.pop_new_data(MarketType.OPTION)
#                 )
                
#                 append_tasks = []
                
#                 if crypto_data:
#                     print(f"[Historical - {datetime.now(ZoneInfo(self.account.location)).strftime('%H:%M:%S')}] Crypto : \n{crypto_data}")
#                     append_tasks.append(self.record.append(MarketType.CRYPTO.value, crypto_data))

#                 if stock_data:
#                     print(f"[Historical - {datetime.now(ZoneInfo(self.account.location)).strftime('%H:%M:%S')}] Stock : \n{stock_data}")
#                     append_tasks.append(self.record.append(MarketType.STOCK.value, stock_data))

#                 if option_data:
#                     print(f"[Historical - {datetime.now(ZoneInfo(self.account.location)).strftime('%H:%M:%S')}] Option : \n{option_data}")
#                     append_tasks.append(self.record.append(MarketType.OPTION.value, option_data))

#                 if append_tasks:
#                     await asyncio.gather(*append_tasks, return_exceptions=True)
#                     predicted = False

#             if self.is_streaming:
#                 crypto_data, stock_data, option_data = await asyncio.gather(
#                     self.account.stream.pop_new_data(MarketType.CRYPTO),
#                     self.account.stream.pop_new_data(MarketType.STOCK),
#                     self.account.stream.pop_new_data(MarketType.OPTION)
#                 )

#                 if crypto_data:
#                     print(f"[Stream] Crypto : \n{crypto_data}")

#                 if stock_data:
#                     print(f"[Stream] Stock : \n{stock_data}")

#                 if option_data:
#                     print(f"[Stream] Option : \n{option_data}")

#             if self.is_analyzing:
#                 pass
#             if self.is_predicting and not predicted:
#                 # Run predictions on new data if available
#                 crypto_df = await self.record.read(MarketType.CRYPTO.value, self.account.investment.get("crypto"))
#                 stock_df = await self.record.read(MarketType.STOCK.value, self.account.investment.get("stock"))

#                 operate_tasks = []
#                 # Run predictions synchronously
#                 for symbol, df in crypto_df.items():
#                     if df is not None and not df.empty:
#                         operate_tasks.append(self.model.operate(df, symbol))
                
#                 for symbol, df in stock_df.items():
#                     if df is not None and not df.empty:
#                         operate_tasks.append(self.model.operate(df, symbol))

#                 if operate_tasks:
#                     await asyncio.gather(*operate_tasks, return_exceptions=True)

#                 predicted = True         
            
#             await asyncio.sleep(0.1)

#     async def display_status(self):
#         """Display application status"""
#         print("\n" + "="*40)
#         print("APPLICATION STATUS")
#         print("="*40)
        
#         print(f"Account: {self.account.name}")
#         print(f"Location: {self.account.location}")
        
#         # Background process status
#         print(f"\nBackground Processes:")
#         print(f"  Historical Data Collection: {'Active' if self.is_retrieving else 'Inactive'}")
#         print(f"  Model Prediction: {'Active' if self.is_predicting else 'Inactive'}")
#         print(f"  Streaming: {'Active' if self.is_streaming else 'Inactive'}")
#         print(f"  Order Processing: {'Active' if self.is_deciding else 'Inactive'}")
        
#         # Component status
#         try:
#             self.account.stream.status()
#             print("Periodic Latest:")
#             self.account.historical.status()
#         except Exception as e:
#             print(f"Status Error: {e}")
        
#         # Investment symbols
#         print(f"\nInvestment Symbols:")
#         for market_type, symbols in self.account.investment.items():
#             symbol_list = ', '.join(symbols) if symbols else 'None'
#             print(f"  {market_type.title()}: {symbol_list}")
        
#         # Task status
#         all_tasks = asyncio.all_tasks()
#         running_tasks = [task for task in all_tasks if not task.done()]
#         print(f"\nTasks: Running={len(running_tasks)}, Total={len(all_tasks)}")
        
#         if running_tasks:
#             print("  Running Tasks:")
#             for i, task in enumerate(running_tasks, 1):
#                 # Try to get the task name
#                 task_name = None
#                 if hasattr(task, 'get_name'):
#                     task_name = task.get_name()
                
#                 # If no name or default name, try to extract from coroutine
#                 if not task_name or task_name.startswith("Task-"):
#                     if hasattr(task, '_coro'):
#                         coro_name = task._coro.__name__ if hasattr(task._coro, '__name__') else "Unknown"
#                         task_name = f"{coro_name}-{i}"
#                     else:
#                         task_name = f"Background-{i}"
                
#                 print(f"    {i}. {task_name}")
        
#         print("="*40)

#     async def run_historical(self):
#         historical_tasks = {}
        
#         if self.account.investment.get("stock"):
#             historical_tasks[MarketType.STOCK] = self.account.fetch_historical(MarketType.STOCK)
        
#         # Crypto historical data
#         if self.account.investment.get("crypto"):
#             historical_tasks[MarketType.CRYPTO] = self.account.fetch_historical(MarketType.CRYPTO)
        
#         # Option historical data
#         if self.account.investment.get("option"):
#             historical_tasks[MarketType.OPTION] = self.account.fetch_historical(MarketType.OPTION)
        
#         # Execute all tasks and create write tasks
#         write_tasks = []
        
#         for market_type, task in historical_tasks.items():
#             try:
#                 result = await task
                
#                 # Skip if result is invalid
#                 if result is None:
#                     print(f"[!] No data received for {market_type.value}")
#                     continue
                
#                 # Handle dictionary results (stock/crypto/option data)
#                 if isinstance(result, dict) and result:
#                     write_tasks.append(self.record.write(market_type.value, result))
#                 else:
#                     print(f"[!] Invalid result format for {market_type.value}: {type(result)}")
                    
#             except Exception as e:
#                 print(f"[!] Error processing {market_type.value} historical data: {e}")
        
#         if write_tasks:
#             await asyncio.gather(*write_tasks, return_exceptions=True)
#         else:
#             print("[!] No valid data to write!")

#         self.is_retrieving = True

#     async def stop_historical(self):
#         print("\n[+] Stopping historical data...")
#         await self.account.stop_historical()
#         self.is_retrieving = False

#     async def run_stream(self):
#         print("\n[+] Starting streams...")
#         try:
#             await self.account.start_stream(MarketType.STOCK)
#             print("[+] Stock stream started")
            
#             await self.account.start_stream(MarketType.CRYPTO)
#             print("[+] Crypto stream started")

#             self.is_streaming = self.account.stream.running_stream
#             return True
#         except Exception as e:
#             print(f"[!] Error starting streams: {e}")
#             return False

#     async def stop_stream(self):
#         print("\n[+] Stopping all streams...")
#         try:
#             await self.account.stop_stream()

#             self.is_streaming = self.account.stream.running_stream
#             return True
#         except Exception as e:
#             print(f"[!] Error stopping streams: {e}")
#             return False

#     async def run_models(self):
#         print("\n[+] Running models...")        
#         # If no streaming data is available, try to load historical data
#         crypto_data = await self.record.read(MarketType.CRYPTO.value, self.account.investment.get("crypto"))
#         stock_data = await self.record.read(MarketType.STOCK.value, self.account.investment.get("stock"))
        
#         models_created = False
        
#         # Only create models for crypto if there is crypto data
#         if crypto_data and isinstance(crypto_data, dict):
#             for symbol, df in crypto_data.items():
#                 if df is not None and not df.empty:
#                     self.model.create(df, symbol)
#                     models_created = True
#                 else:
#                     print(f"[!] No data for {symbol}")
#         elif self.account.investment.get("crypto"):
#             print("[!] No crypto data available for model creation!")

#         # Only create models for stock if there is stock data
#         if stock_data and isinstance(stock_data, dict):
#             for symbol, df in stock_data.items():
#                 if df is not None and not df.empty:
#                     self.model.create(df, symbol)
#                     models_created = True
#                 else:
#                     print(f"[!] No data for {symbol}")
#         elif self.account.investment.get("stock"):
#             print("[!] No stock data available for model creation!")

#         # If no data is available, show a message
#         if not models_created:
#             print("[!] No models were created!")
#             self.is_predicting = False
#             return False
        
#         self.is_predicting = True
#         return True

#     async def stop_models(self):
#         print("\n[+] Stopping models...")
#         self.is_predicting = False
#         return True

#     async def run_order(self):
#         print("\n[+] Running order...")
#         pass

#     async def stop_order(self):
#         print("\n[+] Stopping order...")
#         pass

#     async def exit_app(self) -> int:
#         print("[+] Shutting down application...")
        
#         # Stop all streams first
#         if self.is_streaming:
#             await self.stop_stream()
        
#         # Stop models if running
#         if self.is_predicting:
#             await self.stop_models()
        
#         # Final cleanup
#         gc.collect()
#         return 0

# class Menu:
#     class Option(Enum):
#         DISPLAY_STATUS = "I"
#         RUN_SWITCH = "1"
#         STREAM_SWITCH = "2"
#         ORDER_SWITCH = "3"
#         DISPLAY_MODELS = "4"
        
#         EXIT = "x"

#     def __init__(self, app: Application):
#         self.app = app
#         self.toggle_run = False
#         self.toggle_stream = False
#         self.toggle_order = False

#         self.menu_actions: Dict[str, tuple] = {
#             self.Option.DISPLAY_STATUS.value: ("Display Status", self.app.display_status),
#             self.Option.RUN_SWITCH.value: ("Run Switch (Historical + Models)", (self.run_historical_and_models, self.stop_historical_and_models)[self.toggle_run]),
#             self.Option.STREAM_SWITCH.value: ("Stream Switch", (self.app.run_stream, self.app.stop_stream)[self.toggle_stream]),
#             self.Option.ORDER_SWITCH.value: ("Order Switch", (self.app.run_order, self.app.stop_order)[self.toggle_order]),
#             self.Option.DISPLAY_MODELS.value: ("Display Models", self.app.display_models),
#             self.Option.EXIT.value: ("Exit", self.app.exit_app)
#         }
#     async def run_historical_and_models(self):
#         """Run both historical data collection and model training/prediction"""
#         print("\n[+] Starting historical data collection and model training...")
        
#         # First run historical data collection
#         await self.app.run_historical()
        
#         # Wait a moment for data to be processed
#         await asyncio.sleep(1)
        
#         # Then run models
#         success = await self.app.run_models()

#     async def stop_historical_and_models(self):
#         """Stop both historical data collection and model prediction"""
#         print("\n[+] Stopping historical data collection and model prediction...")
        
#         # Stop historical data collection
#         await self.app.stop_historical()
        
#         # Stop models
#         await self.app.stop_models()
        
#         print("[+] Historical data collection and model prediction stopped!")
#         return True

#     async def select_action(self) -> str:
#         return await asyncio.get_event_loop().run_in_executor(None, lambda: input("Enter your choice: ").strip())
    
#     async def wait_for_user(self, message: str = "Press Enter to continue...\n") -> None:
#         await asyncio.get_event_loop().run_in_executor(None, lambda: input(message))
    
#     async def handle_action(self, choice: str) -> Optional[str]:
#         if choice in self.menu_actions:
#             # Get the action based on CURRENT toggle state
#             _, action = self.menu_actions[choice]
            
#             # Execute the action
#             if asyncio.iscoroutinefunction(action):
#                 result = await action()
#             else:
#                 result = action()
            
#             # Update toggle states AFTER executing action
#             if choice == self.Option.RUN_SWITCH.value:
#                 self.toggle_run = not self.toggle_run
#                 self.app.is_retrieving = self.toggle_run
#                 self.app.is_predicting = self.toggle_run
#             elif choice == self.Option.STREAM_SWITCH.value:
#                 self.toggle_stream = not self.toggle_stream
#                 self.app.is_streaming = self.toggle_stream
#             elif choice == self.Option.ORDER_SWITCH.value:
#                 self.toggle_order = not self.toggle_order
#                 self.app.is_deciding = self.toggle_order
            
#             # Update menu actions with new toggle states
#             self.menu_actions = {
#                 self.Option.DISPLAY_STATUS.value: ("Display Status", self.app.display_status),
#                 self.Option.RUN_SWITCH.value: ("Run Switch (Historical + Models)", (self.run_historical_and_models, self.stop_historical_and_models)[self.toggle_run]),
#                 self.Option.STREAM_SWITCH.value: ("Stream Switch", (self.app.run_stream, self.app.stop_stream)[self.toggle_stream]),
#                 self.Option.ORDER_SWITCH.value: ("Order Switch", (self.app.run_order, self.app.stop_order)[self.toggle_order]),
#                 self.Option.DISPLAY_MODELS.value: ("Display Models", self.app.display_models),
#                 self.Option.EXIT.value: ("Exit", self.app.exit_app)
#             }
            
#             return result
#         else:
#             print("[!] Invalid choice!")
#             return None

#     def display_menu(self) -> None:
#         os.system('cls' if os.name == 'nt' else 'clear')
#         print("=" * 40)
#         print("ALPACA TRADING APPLICATION")
#         print("=" * 40)
#         for key, (description, _) in self.menu_actions.items():
#             print(f" {key}. {description:<24}")
#         print("=" * 40)

# async def main():
#     app = Application()
#     menu = Menu(app)
    
#     print("Welcome to Alpaca Trading Application!")
#     await menu.wait_for_user()
    
#     while True:
#         if app.update_configuration():
#             print("[+] Configuration updated!")
#             await menu.wait_for_user()

#         menu.display_menu()
#         try:
#             choice = await menu.select_action()
#             result = await menu.handle_action(choice)
#             await menu.wait_for_user()
#             if result == 0:
#                 break
#         except KeyboardInterrupt:
#             print("\n[!] Interrupted by user")
#             break
#         except Exception as e:
#             print(f"[!] Error: {e}")
#             await menu.wait_for_user()

# if __name__ == "__main__":
#     asyncio.run(main())




