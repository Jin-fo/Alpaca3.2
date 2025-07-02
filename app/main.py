from head import *
from module.account import DataType, MarketType, Account
from module.record import *
from module.model import *
import json
import asyncio
import pandas as pd
import os
import gc

class Configuration:
    def __init__(self):
        self.path = "app/config.json"
        self.last_mtime = 0
        self._account_args = None
        self._record_args = None
        self._model_args = None
        self.load()

    def load(self):
        try:
            with open(self.path, 'r') as f:
                self._config = json.load(f)

            self._account_args = self._config['account']
            self._record_args = self._config['record']
            self._model_args = self._config['model']

        except Exception as e:
            print(f"[!] Error loading config: {e}")

    def update(self):
        try:
            current_mtime = os.path.getmtime(self.path)
            if current_mtime > self.last_mtime:
                self.load()
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
    def __init__(self):
        self.config = Configuration()
        self.account = Account()
        self.record = Record()
        self.model = Model()

        self.is_browsing : bool = False
        self.is_streaming : bool = False
        self.is_retrieving : bool = True
        self.is_analyzing : bool = False #ploting, 
        self.is_predicting : bool = False
        self.is_deciding : bool = False #order, buy, sell

        asyncio.create_task(self._data_pipeline_loop())
        
    def update_configuration(self):
        if self.config.update():
            self.account.load(self.config.account_args)
            self.record.load(self.config.record_args)
            self.model.load(self.config.model_args)
            return True
        return False
    
    async def _data_pipeline_loop(self):

        predicted : bool = False

        while True:
            if self.is_browsing:
                pass
            if self.is_streaming:
                crypto_data, stock_data, option_data = await asyncio.gather(
                    self.account.stream.pop_new_data(MarketType.CRYPTO),
                    self.account.stream.pop_new_data(MarketType.STOCK),
                    self.account.stream.pop_new_data(MarketType.OPTION)
                )

                append_tasks = []
                if crypto_data:
                    print(f"[o] Crypto data: {crypto_data}")
                    append_tasks.append(self.record.append(MarketType.CRYPTO.value, crypto_data))
                    predicted = False

                if stock_data:
                    print(f"[o] Stock data: {stock_data}")
                    append_tasks.append(self.record.append(MarketType.STOCK.value, stock_data))

                if option_data:
                    print(f"[o] Option data: {option_data}")
                    append_tasks.append(self.record.append(MarketType.OPTION.value, option_data))

                await asyncio.gather(*append_tasks, return_exceptions=True)

                
            if self.is_retrieving:
                pass

            if self.is_analyzing:
                pass
            if self.is_predicting and not predicted:
                # Run predictions on new data if available
                crypto_df = await self.record.read(MarketType.CRYPTO.value, self.account.investment.get("crypto"))
                stock_df = await self.record.read(MarketType.STOCK.value, self.account.investment.get("stock"))

                # Run predictions synchronously
                if crypto_df and isinstance(crypto_df, dict):
                    for symbol, df in crypto_df.items():
                        if df is not None and not df.empty:
                            self.model.operate(df, symbol)
                
                if stock_df and isinstance(stock_df, dict):
                    for symbol, df in stock_df.items():
                        if df is not None and not df.empty:
                            self.model.operate(df, symbol)

                predicted = True         
            
            await asyncio.sleep(0.1)  # Prevent infinite loop from blocking

    async def display_status(self):
        """Display comprehensive application status"""
        await self.account.display_status()
    
    async def file_historical(self):
        print("\n[+] Fetching historical data...")
        
        # Create historical tasks for each market type
        historical_tasks = {}
        
        # Stock historical data
        if self.account.investment.get("stock"):
            historical_tasks[MarketType.STOCK] = self.account.fetch_historical(MarketType.STOCK)
        
        # Crypto historical data
        if self.account.investment.get("crypto"):
            historical_tasks[MarketType.CRYPTO] = self.account.fetch_historical(MarketType.CRYPTO)
        
        # Option historical data
        if self.account.investment.get("option"):
            historical_tasks[MarketType.OPTION] = self.account.fetch_historical(MarketType.OPTION)
        
        # Execute all tasks and create write tasks
        write_tasks = []
        
        for market_type, task in historical_tasks.items():
            try:
                result = await task
                
                # Skip if result is invalid
                if result is None:
                    print(f"[!] No data received for {market_type.value}")
                    continue
                
                # Handle dictionary results (stock/crypto/option data)
                if isinstance(result, dict) and result:
                    write_tasks.append(self.record.write(market_type.value, result))
                    print(f"[+] Added {len(result)} symbols for {market_type.value}")
                else:
                    print(f"[!] Invalid result format for {market_type.value}: {type(result)}")
                    
            except Exception as e:
                print(f"[!] Error processing {market_type.value} historical data: {e}")
        
        if write_tasks:
            await asyncio.gather(*write_tasks, return_exceptions=True)
            print("[+] Historical data fetch and write completed")
        else:
            print("[!] No valid data to write!")

    async def run_stream(self):
        print("\n[+] Starting streams...")
        try:
            await self.account.start_stream(MarketType.STOCK)
            print("[+] Stock stream started")
            
            await self.account.start_stream(MarketType.CRYPTO)
            print("[+] Crypto stream started")

            self.is_streaming = self.account.stream.running_stream
            print("[+] Streams started successfully")
            return True
        except Exception as e:
            print(f"[!] Error starting streams: {e}")
            return False

    async def auto_retrieve(self):
        print("\n[+] Auto retrieving...")
        pass

    async def stop_retrieve(self):
        print("\n[+] Stopping auto retrieving...")
        pass
    async def stop_stream(self):
        print("\n[+] Stopping all streams...")
        try:
            await self.account.stop_stream()

            self.is_streaming = self.account.stream.running_stream
            print("[+] All streams stopped successfully")
            return True
        except Exception as e:
            print(f"[!] Error stopping streams: {e}")
            return False

    async def run_models(self):
        print("\n[+] Running models...")        
        # If no streaming data is available, try to load historical data
        crypto_data = await self.record.read(MarketType.CRYPTO.value, self.account.investment.get("crypto"))
        stock_data = await self.record.read(MarketType.STOCK.value, self.account.investment.get("stock"))
        
        models_created = False
        
        # Only create models for crypto if there is crypto data
        if crypto_data and isinstance(crypto_data, dict):
            for symbol, df in crypto_data.items():
                if df is not None and not df.empty:
                    self.model.create(df, symbol)
                    models_created = True
                else:
                    print(f"[!] No data for {symbol}")
        elif self.account.investment.get("crypto"):
            print("[!] No crypto data available for model creation!")

        # Only create models for stock if there is stock data
        if stock_data and isinstance(stock_data, dict):
            for symbol, df in stock_data.items():
                if df is not None and not df.empty:
                    self.model.create(df, symbol)
                    models_created = True
                else:
                    print(f"[!] No data for {symbol}")
        elif self.account.investment.get("stock"):
            print("[!] No stock data available for model creation!")

        # If no data is available, show a message
        if not models_created:
            print("[!] No models were created!")
            self.is_predicting = False
            return False
        
        self.is_predicting = True
        print("[+] Models created successfully")
        return True

    async def stop_models(self):
        print("\n[+] Stopping models...")
        self.is_predicting = False
        return True

    # async def verify_models(self):
    #     print("\n[+] Verifying models...")
    #     test_tasks = []
        
    #     # Only assess crypto models if there is crypto data
    #     if self.crypto_data:
    #         for symbol in self.crypto_data.keys():
    #             test_tasks.append(self.model.assess(symbol))

    #     # Only assess stock models if there is stock data
    #     if self.stock_data:
    #         for symbol in self.stock_data.keys():
    #             test_tasks.append(self.model.assess(symbol))

    #     # If no data is available, show a message
    #     if not test_tasks:
    #         print("[!] No data available for model verification!")
    #         print(f"Crypto data: {len(self.crypto_data)} symbols")
    #         print(f"Stock data: {len(self.stock_data)} symbols")
    #         return False

    #     await asyncio.gather(*test_tasks, return_exceptions=True)
    #     return True

    async def run_order(self):
        print("\n[+] Running order...")
        pass

    async def stop_order(self):
        print("\n[+] Stopping order...")
        pass

    async def display_models(self):
        """Display information about all loaded models"""
        print("\n[+] Model Information:")
        self.model.print_all_models_info()

    async def exit_app(self) -> int:
        print("[+] Shutting down application...")
        
        # Stop all streams first
        if self.is_streaming:
            await self.stop_stream()
        
        # Stop models if running
        if self.is_model_running:
            await self.stop_models()
        
        # Final cleanup
        gc.collect()
        return 0

class Menu:
    class Option(Enum):
        DISPLAY_STATUS = "I"
        FILE_HISTORICAL = "1"
        STREAM_SWITCH = "2"
        MODELS_SWITCH = "3"
        ORDER_SWITCH = "4"
        DISPLAY_MODELS = "5"
        
        EXIT = "x"

    def __init__(self, app: Application):
        self.app = app
        self.toggle_historical = False
        self.toggle_stream = False
        self.toggle_models = False
        self.toggle_order = False

        self.menu_actions: Dict[str, tuple] = {
            self.Option.DISPLAY_STATUS.value: ("Display Status", self.app.display_status),
            self.Option.FILE_HISTORICAL.value: ("File Historical", self.app.file_historical),
            self.Option.STREAM_SWITCH.value: ("Stream Switch", (self.app.run_stream, self.app.stop_stream)[self.toggle_stream]),
            self.Option.MODELS_SWITCH.value: ("Models Switch", (self.app.run_models, self.app.stop_models)[self.toggle_models]),
            self.Option.ORDER_SWITCH.value: ("Order Switch", (self.app.run_order, self.app.stop_order)[self.toggle_order]),
            self.Option.DISPLAY_MODELS.value: ("Display Models", self.app.display_models),
            self.Option.EXIT.value: ("Exit", self.app.exit_app)
        }

    async def select_action(self) -> str:
        return await asyncio.get_event_loop().run_in_executor(None, lambda: input("Enter your choice: ").strip())
    
    async def wait_for_user(self, message: str = "Press Enter to continue...\n") -> None:
        await asyncio.get_event_loop().run_in_executor(None, lambda: input(message))
    
    async def handle_action(self, choice: str) -> Optional[str]:
        if choice in self.menu_actions:
            _, action = self.menu_actions[choice]
            
            # Execute the action
            if asyncio.iscoroutinefunction(action):
                result = await action()
            else:
                result = action()
            
            # Update toggle states based on the action executed
            if choice == self.Option.STREAM_SWITCH.value:
                self.toggle_stream = not self.toggle_stream
                self.app.is_streaming = self.toggle_stream
            elif choice == self.Option.MODELS_SWITCH.value:
                self.toggle_models = not self.toggle_models
                self.app.is_model_running = self.toggle_models
            elif choice == self.Option.ORDER_SWITCH.value:
                self.toggle_order = not self.toggle_order
                self.app.is_deciding = self.toggle_order
            
            # Update menu actions with new toggle states
            self.menu_actions = {
                self.Option.DISPLAY_STATUS.value: ("Display Status", self.app.display_status),
                self.Option.FILE_HISTORICAL.value: ("File Historical", self.app.file_historical),
                self.Option.STREAM_SWITCH.value: ("Stream Switch", (self.app.run_stream, self.app.stop_stream)[self.toggle_stream]),
                self.Option.MODELS_SWITCH.value: ("Models Switch", (self.app.run_models, self.app.stop_models)[self.toggle_models]),
                self.Option.ORDER_SWITCH.value: ("Order Switch", (self.app.run_order, self.app.stop_order)[self.toggle_order]),
                self.Option.DISPLAY_MODELS.value: ("Display Models", self.app.display_models),
                self.Option.EXIT.value: ("Exit", self.app.exit_app)
            }
            
            return result
        else:
            print("[!] Invalid choice!")
            return None

    def display_menu(self) -> None:
        os.system('cls' if os.name == 'nt' else 'clear')
        print("=" * 40)
        print("ALPACA TRADING APPLICATION")
        print("=" * 40)
        for key, (description, _) in self.menu_actions.items():
            print(f" {key}. {description:<24}")
        print("=" * 40)

async def main():
    app = Application()
    menu = Menu(app)
    
    print("Welcome to Alpaca Trading Application!")
    await menu.wait_for_user()
    
    while True:
        if app.update_configuration():
            print("[+] Configuration updated!")
            await menu.wait_for_user()

        menu.display_menu()
        try:
            choice = await menu.select_action()
            result = await menu.handle_action(choice)
            await menu.wait_for_user()
            if result == 0:
                break
        except KeyboardInterrupt:
            print("\n[!] Interrupted by user")
            break
        except Exception as e:
            print(f"[!] Error: {e}")
            await menu.wait_for_user()

if __name__ == "__main__":
    asyncio.run(main())




