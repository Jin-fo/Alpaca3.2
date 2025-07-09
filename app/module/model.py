from head import *

from keras._tf_keras.keras.models import Sequential, load_model
from keras._tf_keras.keras.layers import Dense, LSTM as KerasLSTM, InputLayer, Dropout
from keras._tf_keras.keras.optimizers import Adam
from keras._tf_keras.keras.callbacks import ModelCheckpoint, EarlyStopping
from sklearn.preprocessing import MinMaxScaler
import joblib
import json

class Method:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.name = config["name"]
        self.folder = config["folder"]["name"]
        self.use_pretrained : bool = bool(config["use_pretrained"])

        self.scaler : MinMaxScaler = None
        self.raw_data : pd.DataFrame = None
        self.feature_names : List[str] = []  # Track feature order

        self.built : bool = False
        self.trained : bool = False

    def preprocess(self, data : pd.DataFrame) -> np.ndarray:
        try:
            self.raw_data = data.copy()
            if 'timestamp' in self.raw_data.columns:
                self.raw_data['timestamp'] = pd.to_datetime(self.raw_data['timestamp']).diff().dt.total_seconds() / 60
                self.raw_data['timestamp'] = self.raw_data['timestamp'].fillna(0)
                self.raw_data = self.raw_data.rename(columns={'timestamp': 'delta_minute'})

            # Remove symbol and timestamp columns if they exist
            columns_to_drop = ['symbol', 'timestamp']
            for col in columns_to_drop:
                if col in self.raw_data.columns:
                    self.raw_data = self.raw_data.drop(columns=[col])

            # Store feature names in order for later use
            self.feature_names = list(self.raw_data.columns)

            if self.scaler is None:
                self.scaler = MinMaxScaler(feature_range=(0, 1))
                return self.scaler.fit_transform(self.raw_data)
            else:
                return self.scaler.transform(self.raw_data)
            
        except Exception as e:
            print(f"[!] Preprocessing error: {e}")
            return None

    def postprocess(self, data : pd.DataFrame, symbol : str) -> None:
        try:
            if len(data.shape) == 1:
                data = data.reshape(-1, 1)

            x_data = self.scaler.inverse_transform(data)
            
            # Use stored feature names to maintain order
            columns = [f'{name}*' for name in self.feature_names] if self.feature_names else [f'feature_{i}*' for i in range(x_data.shape[1])]
            return pd.DataFrame(x_data, columns=columns)

        except Exception as e:
            print(f"[!] Postprocessing error: {e}")
            return None

    def _check_features(self, data: pd.DataFrame) -> bool:
        """Quick feature order check"""
        if not self.feature_names:
            return True  # Skip check if no features stored
            
        current_features = [f for f in data.columns if f not in ['symbol', 'timestamp', 'prediction_step']]
        if current_features != self.feature_names:
            print(f"[!] Feature mismatch: expected {self.feature_names}, got {current_features}")
            return False
        return True

    def _save_features(self, symbol: str) -> None:
        """Save feature order"""
        try:
            import json
            with open(f"{self.folder}/features_{symbol.replace('/', '_')}.json", 'w') as f:
                json.dump({'features': self.feature_names}, f)
        except Exception as e:
            print(f"[!] Error saving features: {e}")

    def _load_features(self, symbol: str) -> bool:
        """Load feature order"""
        try:
            import json
            with open(f"{self.folder}/features_{symbol.replace('/', '_')}.json", 'r') as f:
                self.feature_names = json.load(f)['features']
            return True
        except Exception as e:
            print(f"[!] Error loading features: {e}")
            return False

class LSTM(Method):
    def __init__(self, method_config: Dict[str, Any]) -> None:
        super().__init__(method_config)

        self.model = Sequential(name=f"{self.name}")

        self.future_step = method_config["adjustable"]["future_step"]
        self.sample_size = method_config["adjustable"]["sample_size"]

        self.lstm_layers = method_config["settings"]["lstm"]
        self.dense_layers = method_config["settings"]["dense"]
        self.seq_length = method_config["settings"]["sequence_length"]
        self.train_split = method_config["settings"]["train_split"]
        self.batch_size = method_config["settings"]["batch_size"]
        self.epochs = method_config["settings"]["epochs"]
        self.learning_rate = method_config["settings"]["learning_rate"]

        self.loss = method_config["loss"]
        self.optimizer = method_config["optimizer"]

        self.x_train = None
        self.y_train = None
        self.x_test = None
        self.y_test = None
        self.x_input = None

    def _model_info(self) -> None:
        """Print model layers and shape information"""
        if not self.built:
            print("[!] Model not built yet")
            return
            
        print(f"\n[+] Model: {self.name}")
        print("=" * 50)
        print("Model Architecture:")
        print("-" * 30)
        
        for i, layer in enumerate(self.model.layers):
            layer_type = layer.__class__.__name__

            if hasattr(layer, 'units'):
                print(f"Layer {i+1}: {layer_type} - Units: {layer.units}")
            elif hasattr(layer, 'filters'):
                print(f"Layer {i+1}: {layer_type} - Filters: {layer.filters}")
            else:
                print(f"Layer {i+1}: {layer_type}")

            if hasattr(layer, 'input_shape'):
                print(f"  Input Shape: {layer.input_shape}")
            if hasattr(layer, 'output_shape'):
                print(f"  Output Shape: {layer.output_shape}")
        
        print("-" * 30)
        print(f"Total Parameters: {self.model.count_params():,}")
        print("=" * 50)

    def build(self, data : pd.DataFrame, symbol : str) -> None:
        if len(data) < self.seq_length + 1:
            print(f"[!] Insufficient data: need {self.seq_length + 1}, got {len(data)}")
            return None
        
        print(f"[+] Building {symbol}...")
        try:
            # Preprocess and prepare data
            scaled_data = self.preprocess(data)
            
            # Sanity check features after preprocessing
            if not self._check_features(data):
                print("[!] Feature order issue detected! Stopping build.")
                return None
            
            x_seq, y_seq = [], []

            for i in range(self.seq_length, len(scaled_data)):
                x_seq.append(scaled_data[i - self.seq_length:i])
                y_seq.append(scaled_data[i, :])

            x, y = np.array(x_seq), np.array(y_seq)
            split = int(len(x) * self.train_split)

            self.x_train, self.y_train = x[:split], y[:split]
            self.x_test, self.y_test = x[split:], y[split:]
            
            # Setup directories and save data
            os.makedirs(f"{self.folder}/Scaled", exist_ok=True)
            
            clean_symbol = symbol.replace('/', '_')
            pd.DataFrame(scaled_data).to_csv(f"{self.folder}/Scaled/scaled_{clean_symbol}.csv", index=False)
            
            # Save feature information for later verification
            self._save_features(symbol)
            
            # Save scaler
            if self.scaler:

                joblib.dump(self.scaler, f"{self.folder}/{self.name}_scaler.pkl")
                print(f"[o] Scaler saved")
            
            # Build model architecture
            self.model.add(InputLayer(shape=x.shape[1:]))
            
            # LSTM layers
            for i, units in enumerate(self.lstm_layers):
                return_sequences = i < len(self.lstm_layers) - 1  # False for last layer
                self.model.add(KerasLSTM(units, return_sequences=return_sequences))
                self.model.add(Dropout(0.2))  # Add dropout after each LSTM layer

            for units in self.dense_layers:
                self.model.add(Dense(units, activation='relu'))
                self.model.add(Dropout(0.2))
            
            self.model.add(Dense(x.shape[-1]))
            
            # Compile the model
            self.model.compile(
                optimizer=Adam(learning_rate=self.learning_rate),
                loss=self.loss
            )

            self.built = True
            self._model_info()

        except Exception as e:
            print(f"[!] Building error: {e}")
            return None
    
    def train(self) -> None:

        if self.use_pretrained:
            try:
                self.model = load_model(f"{self.folder}/{self.name}.keras")
                self.scaler = joblib.load(f"{self.folder}/{self.name}_scaler.pkl")
                self.trained = True
                print("[o] Pretrained model and scaler loaded")

            except Exception as e:
                print(f"[!] Error loading pretrained model: {e}")
                return None
        else:
            if not self.built or self.x_train is None or self.y_train is None:
                print("[!] Model not built or no training data")
                return None
            
            try:
                callbacks = [
                    ModelCheckpoint(filepath=f"{self.folder}/{self.name}.keras", monitor='val_loss', save_best_only=True, mode='min'),
                    EarlyStopping(monitor='val_loss', patience=5, mode='min')
                ]
                
                history = self.model.fit(
                    x=self.x_train,
                    y=self.y_train,
                    batch_size=self.batch_size,
                    epochs=self.epochs,
                    validation_split=0.1,
                    verbose=1,
                    callbacks=callbacks
                )
                self.trained = True
                print(f"[o] Training loss: {history.history['loss'][-1]:.4f}")

            except Exception as e:
                print(f"[!] Training error: {e}")
                return None

    def _calculate_accuracy_metrics(self, predictions: np.ndarray, actual: np.ndarray) -> None:
        """Calculate and display accuracy metrics"""
        try:
            from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
            
            # Inverse transform if scaler exists
            if self.scaler:
                predictions, actual = self.scaler.inverse_transform(predictions), self.scaler.inverse_transform(actual)
            
            # Calculate metrics
            metrics = {
                'MAE': mean_absolute_error(actual, predictions),
                'MSE': mean_squared_error(actual, predictions),
                'RMSE': np.sqrt(mean_squared_error(actual, predictions)),
                'R²': r2_score(actual, predictions)
            }
            
            # Directional accuracy for price prediction
            if predictions.shape[1] >= 3:
                close_pred, close_actual = predictions[:, 2], actual[:, 2]
                pred_direction = np.diff(close_pred) > 0
                actual_direction = np.diff(close_actual) > 0
                directional_acc = np.mean(pred_direction == actual_direction) * 100
                metrics['Directional Accuracy'] = f"{directional_acc:.1f}%"
            
            print("[o] Accuracy Metrics:")
            for metric, value in metrics.items():
                print(f"    {metric}: {value:.4f}" if isinstance(value, float) else f"    {metric}: {value}")
            
        except Exception as e:
            print(f"[!] Error calculating accuracy metrics: {e}")

    def test(self) -> None:
        if not self.trained:
            print("[!] Model not trained yet")
            return None
        
        try:
            # For pretrained models, skip testing since we don't have original test data
            if self.use_pretrained:
                print("[o] Pretrained model loaded - skipping test evaluation")
                return None
            
            # For newly built models, run the test
            if self.x_test is None or self.y_test is None:
                print("[!] No test data available")
                return None
                
            loss = self.model.evaluate(self.x_test, self.y_test, verbose=0)
            print(f"[o] Test loss: {loss:.4f}")
            
            # Make predictions on test set
            predictions = self.model.predict(self.x_test, verbose=0)
            
            # Calculate accuracy metrics
            self._calculate_accuracy_metrics(predictions, self.y_test)

        except Exception as e:
            print(f"[!] Testing error: {e}") 
    
    def predict(self, data : pd.DataFrame, symbol : str) -> None:
        if not self.trained or len(data) < self.seq_length + 1:
            if not self.trained:
                return None
            print(f"[!] Insufficient data: need {self.seq_length + 1}, got {len(data)}")
            return None
        
        print(f"[+] Predicting {symbol}...")
        try:
            # Load feature info if using pretrained model
            if self.use_pretrained and not self.feature_names:
                if not self._load_features(symbol):
                    print("[!] Could not load feature info for pretrained model")
                    return None
            
            # Sanity check features before prediction
            if not self._check_features(data):
                print("[!] Feature order mismatch in prediction data!")
                return None
            
            scaled_data = self.preprocess(data.iloc[-self.seq_length+1:])
            initial_input = np.array(scaled_data[-self.seq_length:])
            
            # Generate single prediction path
            predictions = []
        
            for step in range(self.future_step):
                next_prediction = self.model.predict(initial_input.reshape(1, *initial_input.shape), verbose=0)[0]
                predictions.append(next_prediction)
                
                # Update input for next iteration
                predicted_step = next_prediction.reshape(1, -1)
                new_seq = np.concatenate([initial_input[1:], predicted_step], axis=0)
                initial_input = new_seq[-self.seq_length:]
            
            # Save prediction
            self._save_prediction(predictions, symbol)
            
            # Analyze previous prediction accuracy if new data is available
            self._analyze_previous_prediction_accuracy(symbol, data)
            
            print(f"[o] Generated prediction for {symbol}")

        except Exception as e:
            print(f"[!] Predicting error: {e}")
            return None

    def _analyze_previous_prediction_accuracy(self, symbol: str, current_data: pd.DataFrame) -> None:
        """Analyze accuracy of previous prediction using current data."""
        try:
            clean_symbol = symbol.replace('/', '_')
            trend_file = f'{self.folder}/Prediction/{clean_symbol}_trend_analysis.json'
            
            if not os.path.exists(trend_file):
                return  # No previous prediction to analyze
            
            # Load previous prediction trend
            with open(trend_file, 'r') as f:
                prev_trend = json.load(f)
            
            # Get current data trend (last few data points)
            if 'close' not in current_data.columns:
                return
            
            current_prices = current_data['close'].values
            if len(current_prices) < 2:
                return
            
            # Calculate current trend (using last few data points)
            recent_prices = current_prices[-min(5, len(current_prices)):]  # Last 5 points or all if less
            current_start, current_end = recent_prices[0], recent_prices[-1]
            current_change_pct = ((current_end - current_start) / current_start) * 100
            current_direction = "UP" if current_change_pct > 0 else "DOWN" if current_change_pct < 0 else "FLAT"
            
            # Compare with previous prediction
            predicted_direction = prev_trend['trend_direction']
            direction_correct = predicted_direction == current_direction
            
            # Calculate price accuracy
            predicted_end = prev_trend['end_price']
            price_accuracy = max(0, 100 - abs((predicted_end - current_end) / current_end) * 100)
            
            # Overall accuracy
            overall_accuracy = (100 if direction_correct else 0 + price_accuracy) / 2
            
            # Print accuracy results
            status = "✓" if direction_correct else "✗"
            print(f"[o] {symbol} Trend Accuracy: {status} Direction, {price_accuracy:.1f}% Price, {overall_accuracy:.1f}% Overall")
            
            # Save accuracy results
            accuracy_file = f'{self.folder}/Prediction/{clean_symbol}_accuracy.json'
            accuracy_data = {
                "symbol": symbol,
                "analysis_timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "predicted_direction": predicted_direction,
                "actual_direction": current_direction,
                "direction_correct": direction_correct,
                "price_accuracy": price_accuracy,
                "overall_accuracy": overall_accuracy,
                "predicted_change_pct": prev_trend['price_change_percentage'],
                "actual_change_pct": current_change_pct
            }
            
            with open(accuracy_file, 'w') as f:
                json.dump(accuracy_data, f, indent=2, default=str)
                
        except Exception as e:
            print(f"[!] Error analyzing accuracy for {symbol}: {e}")

    def _save_prediction(self, predictions: List[np.ndarray], symbol: str) -> None:
        """Save prediction and analyze trend."""
        try:
            clean_symbol = symbol.replace('/', '_')
            prediction_dir = f'{self.folder}/Prediction'
            os.makedirs(prediction_dir, exist_ok=True)
            
            # Process and save prediction
            processed_path = self.postprocess(np.array(predictions), symbol)
            processed_path['timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            processed_path['prediction_step'] = range(1, len(processed_path) + 1)
            
            processed_path.to_csv(f'{prediction_dir}/{clean_symbol}.csv', index=False)
            
            # Analyze and save trend
            trend_analysis = self._analyze_prediction_trend(processed_path, symbol)
            with open(f'{prediction_dir}/{clean_symbol}_trend_analysis.json', 'w') as f:
                json.dump(trend_analysis, f, indent=2, default=str)
            
        except Exception as e:
            print(f"[!] Error saving prediction: {e}")

    def _analyze_prediction_trend(self, prediction_df: pd.DataFrame, symbol: str) -> Dict[str, Any]:
        """Analyze prediction trend direction."""
        try:
            # Find close price column
            close_col = next((col for col in prediction_df.columns if 'close' in col.lower()), None)
            if not close_col:
                return {"error": "Close price column not found"}
            
            prices = prediction_df[close_col].values
            start, end = prices[0], prices[-1]
            change_pct = ((end - start) / start) * 100
            direction = "UP" if change_pct > 0 else "DOWN" if change_pct < 0 else "FLAT"
            
            print(f"[o] {symbol} Prediction: {direction} ({change_pct:.2f}%)")
            
            return {
                "symbol": symbol,
                "trend_direction": direction,
                "price_change_percentage": float(change_pct),
                "start_price": float(start),
                "end_price": float(end)
            }
            
        except Exception as e:
            print(f"[!] Error analyzing trend: {e}")
            return {"error": str(e)}

class Model:
    def __init__(self) -> None:
        self.model_list : List[Method] = []

    def load(self, config: Dict[str, Any]) -> None:
        self.model_list = []
        
        # The config methods are at the top level, not under a "model" key
        for method in config.values():
            if method["name"] == "Long_Short_Term_Memory":
                self.model_list.append(LSTM(method))
                print(f"[+] Added LSTM model")
            elif method["name"] == "Reforcement_Learning":
                self.model_list.append(None)
                print(f"[+] Added RL placeholder")
            elif method["name"] == "Decision_Tree":
                self.model_list.append(None)
                print(f"[+] Added DT placeholder")

    def create(self, data : pd.DataFrame, symbol : str) -> None:
        
        
        # Check if symbol column exists, if not skip the validation
        if 'symbol' in data.columns and symbol != data.iloc[0]["symbol"]:
            print(f"[!] Symbol {symbol} does not match the data symbol {data.iloc[0]['symbol']}")

        for i, model in enumerate(self.model_list):
            if model is not None:
                if not model.use_pretrained:
                    print(f"[>] Creating new model for {symbol}: {model.name}")
                    model.build(data, symbol)
                    model.train()
                    model.test()
                else:
                    print(f"[>] Using pretrained model for {symbol}: {model.name}")
                    model.train()
                    model.test()
            else:
                print(f"[!] Model {i} is None")

    def operate(self, data : pd.DataFrame, symbol : str) -> None:
        # Check if symbol column exists, if not skip the validation
        if 'symbol' in data.columns and symbol != data.iloc[0]["symbol"]:
            print(f"[!] Symbol {symbol} does not match the data symbol {data.iloc[0]['symbol']}")
            return
            
        for model in self.model_list:
            if model is not None:
                model.predict(data, symbol)

    def decide(self, data : pd.DataFrame, symbol : str) -> None:
        pass
































