from head import *
from module.client import Account
from module.stats import Stats
from module.model import Model, LSTM
from datetime import datetime

# class Application:
#     """Application for market data analysis and prediction."""
    
#     def __init__(self, api_key=None, secret_key=None):
#         # API credentials
#         self.api_key = api_key or "PKE1B8WAV2KJ324ZKQKC"
#         self.secret_key = secret_key or "Ro7nFRclHQekQSf5Tt3zbpJAr9AaXhQ7r67sJJDy"
        
#         # Configuration
#         self.symbols = ["BTC/USD"]
        
#         self.account_config = {
#             "paper": True,
#             "name": "Paper Account",
#             "timezone": "America/New_York"
#         }
        
#         self.history_config = {
#             "date": 10,  # days
#             "step": 5    # minutes
#         }
        
#         self.model_config = {
#             'sequence_length': 60,
#             'train_split': 0.8,
#             'lstm_units': [50, 50],
#             'dense_units': [25, 1],
#             'batch_size': 16,
#             'epochs': 1,
#             'learning_rate': 0.001
#         }
#         self.stats_config = {
#             "columns": ["timestamp", "symbol", "open", "high", "low", "close"]
#         }
        
#         # Trend prediction tracking
#         self.predictions_history = []
#         self.actual_trends = []
#         self.predicted_trends = []
#         self.trend_accuracy = {
#             'correct': 0,
#             'incorrect': 0,
#             'accuracy': 0.0
#         }


        
#     async def _historical(self) -> None:
#         """Get and process historical data."""
#         print("Getting historical data...")
 
#         data = self.account.history("bars", self.history_config["date"], self.history_config["step"])
#         df = self.clean_data(data, self.account.zone(), self.stats_config["columns"])
        
#         # Update the stats instance with the data and write to file
#         self.stats.write(df)
        
#         print(f"Historical data loaded: {len(df)} records")

#     async def _model(self) -> None:
#         """Train and run prediction model."""
#         try:
#             # Read the historical data
#             df = self.stats.read(['close'])
            
#             # Prepare data for the model
#             self.model.preprocess(df, ['close'])
            
#             # Build and train the model
#             self.model.build()
#             history = self.model.train()
            
#             print(f"Model trained successfully")
            
#             # Generate predictions
#             predictions = self.model.operate(df.iloc[-self.model_config['sequence_length']:], 6)
#             print(f"Generated {len(predictions)} predictions")
            
#         except Exception as e:
#             print(f"Error in model training/prediction: {e}")
#             import traceback
#             traceback.print_exc()
    
#     async def _stream(self) -> None:
#         """Stream market data asynchronously."""
#         print("Starting market data stream...")
        
#         try:
#             stream_started = await self.account.stream("bars")
#             if not stream_started:
#                 print("Failed to start stream")
#                 return
                
#             print("Stream started successfully")
            
#             while stream_started:
#                 # Check if we have new data
#                 if self.account.new_data is not None:
#                     try:
#                         # Clean and process the new data
#                         new_df = self.clean_data(self.account.new_data, self.account.zone(), self.stats_config["columns"])
                        
#                         print("New data received:")
#                         print(new_df)
                        
#                         # Evaluate trend prediction accuracy
#                         self.evaluate_trend_accuracy(new_df)
                        
#                         # Save to stats
#                         if self.stats:
#                             self.stats.append(new_df)
                        
#                         # Make new predictions
#                         await self._predict()
                        
#                         # Clear the processed data
#                         self.account.new_data = None
#                     except Exception as e:
#                         print(f"Error processing data: {e}")
#                         self.account.new_data = None
                
#                 await asyncio.sleep(1)
                
#         except Exception as e:
#             print(f"Stream error: {e}")
#             import traceback
#             traceback.print_exc()
#     async def _predict(self) -> None:
#         """Predict future data."""
#         print("Predicting future data...")
#         try:
#             # Get historical data
#             historical_data = self.stats.read(['close'])
#             if historical_data is None or historical_data.empty:
#                 print("Error: No historical data available for prediction")
#                 return
                
#             print(f"Making predictions based on {len(historical_data)} historical records")
            
#             # Get the most recent data points for prediction
#             recent_data = historical_data.iloc[-self.model_config['sequence_length']:]
#             print(f"Using last {len(recent_data)} data points for prediction")
            
#             # Make predictions
#             predictions = self.model.operate(recent_data, future_steps=6)
            
#             # Print predictions in a readable format
#             print("\nPrediction Results:")
#             print("-" * 50)
#             print(predictions)
#             print("-" * 50)
            
#             # Calculate basic stats on predictions
#             if not predictions.empty:
#                 last_actual = float(recent_data.iloc[-1]['close'])
#                 first_pred = float(predictions.iloc[0]['Predicted'])
#                 last_pred = float(predictions.iloc[-1]['Predicted'])
                
#                 print(f"Last actual close: {last_actual:.2f}")
#                 print(f"First prediction: {first_pred:.2f} ({(first_pred-last_actual)/last_actual*100:.2f}% change)")
#                 print(f"Final prediction: {last_pred:.2f} ({(last_pred-last_actual)/last_actual*100:.2f}% change)")
                
#                 # Determine trend
#                 predicted_trend = "UP" if last_pred > last_actual else "DOWN"
#                 print(f"Predicted trend: {'⬆️' if predicted_trend == 'UP' else '⬇️'} {predicted_trend}")
                
#                 # Store prediction for later accuracy evaluation
#                 timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#                 prediction_record = {
#                     'timestamp': timestamp,
#                     'last_actual': last_actual,
#                     'predicted_next': first_pred,
#                     'predicted_trend': predicted_trend,
#                     'actual_trend': None,  # Will be filled when new data arrives
#                     'trend_correct': None  # Will be filled when new data arrives
#                 }
#                 self.predictions_history.append(prediction_record)
#                 self.predicted_trends.append(predicted_trend)
            
#             print(f"Predicted {len(predictions)} future data points")
            
#         except Exception as e:
#             print(f"Error in prediction: {e}")
#             import traceback
#             traceback.print_exc()

#     def evaluate_trend_accuracy(self, new_data):
#         """Evaluate the accuracy of previous trend predictions."""
#         if not self.predictions_history or len(self.predictions_history) == 0:
#             return
            
#         # Get the most recent prediction
#         latest_prediction = self.predictions_history[-1]
        
#         # Skip if this prediction was already evaluated
#         if latest_prediction['actual_trend'] is not None:
#             return
            
#         # Get the actual trend
#         predicted_price = latest_prediction['predicted_next']
#         current_price = float(new_data['close'].iloc[0])
#         predicted_trend = latest_prediction['predicted_trend']
        
#         # Determine actual trend
#         actual_trend = "UP" if current_price > latest_prediction['last_actual'] else "DOWN"
#         self.actual_trends.append(actual_trend)
        
#         # Update the prediction record
#         latest_prediction['actual_trend'] = actual_trend
#         latest_prediction['actual_next'] = current_price
#         latest_prediction['trend_correct'] = (predicted_trend == actual_trend)
        
#         # Update accuracy statistics
#         if predicted_trend == actual_trend:
#             self.trend_accuracy['correct'] += 1
#         else:
#             self.trend_accuracy['incorrect'] += 1
            
#         total_predictions = self.trend_accuracy['correct'] + self.trend_accuracy['incorrect']
#         if total_predictions > 0:
#             self.trend_accuracy['accuracy'] = (self.trend_accuracy['correct'] / total_predictions) * 100
            
#         # Print accuracy report
#         print("\n-- Trend Prediction Accuracy Report --")
#         print(f"Last predicted trend: {predicted_trend} at price {latest_prediction['last_actual']:.2f}")
#         print(f"Actual trend: {actual_trend} with current price {current_price:.2f}")
#         print(f"Prediction was: {'✓ CORRECT' if latest_prediction['trend_correct'] else '✗ INCORRECT'}")
#         print(f"Overall accuracy: {self.trend_accuracy['accuracy']:.2f}% ({self.trend_accuracy['correct']}/{total_predictions})")
#         print("-" * 40)

    # async def run(self):
    #     """Run the application."""
    #     self.account = Account(self.api_key, 
    #                            self.secret_key, 
    #                            self.account_config["paper"], 
    #                            self.account_config["name"], 
    #                            self.account_config["timezone"])
    #     self.asset = self.account.focus(self.symbols)
    #     self.stats = Stats(self.asset.symbol, 
    #                        self.stats_config["columns"])
    #     self.model = LSTM(config=self.model_config)
        
    #     print(f"Starting application for {self.symbols}")
        
    #     try:
    #         # First get historical data and train model
    #         await self._historical()
    #         await self._model()
    #         # Then start streaming for real-time data
    #         await self._stream()
    #     except Exception as e:
    #         print(f"Error: {e}")
    #         import traceback
    #         traceback.print_exc()
class Application:
    client_config : dict = {
        "API_KEY" : "PKE1B8WAV2KJ324ZKQKC",
        "SECRET_KEY" : "Ro7nFRclHQekQSf5Tt3zbpJAr9AaXhQ7r67sJJDy",
        "paper" : True,
    }

    time_interval : dict = {
        "range" : {
            "day" : 1,
            "hour" : 0,
            "minute" : 0,
        },
        "step" : {
            "day" : 0,
            "hour" : 0,
            "minute" : 5,
        },
    }
    
    data_param : dict = {
        "type" : "bars",
        "symbols" : ["BTC/USD", "NVDA", "AAPL"],
        "interval" : time_interval,
        "columns" : ["timestamp", "symbol", "open", "high", "low", "close"],
    }
    account : Account
    stats : Stats
    model : Model

    def __init__(self):
        self.config = {
            "API_KEY": "PKE1B8WAV2KJ324ZKQKC",
            "SECRET_KEY": "Ro7nFRclHQekQSf5Tt3zbpJAr9AaXhQ7r67sJJDy",
            "paper": True,
        }
        self.symbols = ["BTC/USD", "NVDA", "AAPL"]  # Both crypto and stock symbols
        self.account = Account(self.config, "Paper Account")
        self.streaming = False
        self.stream_task = None

    def account_info(self):
        print("-" * 30)
        self.account.account_info()
        print("-" * 30)

    def clean_data(self, data, zone: str, columns: list[str]) -> pd.DataFrame:
        """Convert data to DataFrame with timezone handling."""
        try:
            # Try to get DataFrame from data object
            df = data.df.reset_index()
            
            # Copy only the specified columns that exist
            result = pd.DataFrame()
            for col in columns:
                if col in df.columns:
                    result[col] = df[col]
                    
        except:
            # Fallback: create DataFrame from individual attributes
            result = pd.DataFrame()
            result['timestamp'] = [data.timestamp]
            for col in columns:
                if col != 'timestamp':  # timestamp already added
                    result[col] = [getattr(data, col, 0)]

        # Process timestamp column for timezone conversion
        time_col = next((i for i, col in enumerate(result.columns) 
                        if pd.api.types.is_datetime64_any_dtype(result.iloc[:, i])), 0)
    
        # Ensure proper timezone conversion
        timestamp_col = result.columns[time_col]
        timestamps = pd.to_datetime(result[timestamp_col])
    
        # Check if timestamps already have timezone info
        if timestamps.dt.tz is None:
            timestamps = timestamps.dt.tz_localize('UTC')
        
        # Convert to the requested timezone and format as string
        local_timestamps = timestamps.dt.tz_convert(zone)
        result['timestamp'] = local_timestamps.dt.strftime('%Y-%m-%d %H:%M:%S')
                
        return result.set_index('timestamp')
    
    async def file_historical(self):
        """Get historical data for both crypto and stock symbols"""
        try:
            print("[+] Fetching historical data...")
            
            # Get crypto historical data
            crypto_symbols = self.account.focused["crypto"]
            if crypto_symbols:
                print(f"[+] Crypto: {', '.join(crypto_symbols)}")
                crypto_data = self.account.crypto_history("bars", self.time_interval)
                
                if crypto_data is not None and not crypto_data.empty:
                    print(f"[o] Crypto: {len(crypto_data)} records")
                else:
                    print("[!] No crypto historical data available")
            
            # Get stock historical data
            stock_symbols = self.account.focused["stock"]
            if stock_symbols:
                print(f"\n[+] Stock: {', '.join(stock_symbols)}")
                stock_data = self.account.stock_history("bars", self.time_interval)
                
                if stock_data is not None and not stock_data.empty:
                    print(f"[o] Stock: {len(stock_data)} records")
                else:
                    print("[!] No stock historical data available")
                
        except Exception as e:
            print(f"[!] Error getting historical data: {e}")
    
    async def start_stream(self):
        """Start streams for both crypto and stock symbols"""
        if self.account.active_stream:
            print("[!] Stream already running!")
            return
            
        try:
            # Start crypto stream if we have crypto symbols
            crypto_symbols = self.account.focused["crypto"]
            if crypto_symbols:
                print(f"[+] Crypto: {', '.join(crypto_symbols)}")
                await self.account.crypto_stream(self.data_param["type"], crypto_symbols)
            
            # Start stock stream if we have stock symbols
            stock_symbols = self.account.focused["stock"]
            if stock_symbols:
                print(f"[+] Stock: {', '.join(stock_symbols)}")
                await self.account.stock_stream(self.data_param["type"], stock_symbols)
            
            if self.account.active_stream:
                print("[o] Streams started")
            else:
                print("[!] No symbols to stream")
            
        except Exception as e:
            print(f"[!] Failed to start streams: {e}")

    async def stop_stream(self):
        """Stop streams with complete object deletion"""
        if not self.account.active_stream:
            print("[!] No streams to stop")
            return
            
        print("[-] Stopping streams...")
        await self.account.stream_stop()

    async def home(self):
        """Simple stream control menu"""
        # Define menu actions
        menu_actions = {
            "1": ("Start Stream", self.start_stream),
            "2": ("Stop Stream", self.stop_stream),
            "3": ("File Historical", self.file_historical),
            "4": ("Exit", self._exit_app)
        }
        
        while True:
            # Clean up finished tasks and get current status
            self.account.get_stream_status()
            active_count = len(self.account.active_stream)
            
            if active_count > 0:
                crypto_count = len(self.account.focused["crypto"]) if self.account.focused["crypto"] else 0
                stock_count = len(self.account.focused["stock"]) if self.account.focused["stock"] else 0
                status = f"ACTIVE ({crypto_count} crypto, {stock_count} stock)"
            else:
                status = "STOPPED"
            
            # Display chart-like menu
            print(f"\n┌─────────────────────────────┐")
            print(f"     STATUS: {status:<12} ")
            print(f"├─────────────────────────────┤")
            print(f"│ 1. Start Stream             │")
            print(f"│ 2. Stop Stream              │")
            print(f"│ 3. File Historical          │")
            print(f"│ 4. Exit                     │")
            print(f"└─────────────────────────────┘")
            
            try:
                # Use asyncio to make input non-blocking
                choice = await asyncio.get_event_loop().run_in_executor(
                    None, input
                )
                choice = choice.strip()
                
                if choice in menu_actions:
                    _, action = menu_actions[choice]
                    result = await action()
                    if result == "exit":
                        break
                else:
                    print("[!] Invalid choice!")
                    
                # Small delay to prevent overwhelming the console
                await asyncio.sleep(0.1)
                    
            except KeyboardInterrupt:
                await self.stop_stream()
                break
    
    async def _exit_app(self):
        """Exit the application gracefully"""
        await self.stop_stream()
        print("[o] Goodbye!")
        return "exit"

    async def run(self):
        self.account.focus(self.data_param["symbols"])
        await self.home()

async def main():
    app = Application()
    app.account_info()
    await app.run()

if __name__ == "__main__":
    asyncio.run(main())



