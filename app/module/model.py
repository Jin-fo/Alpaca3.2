from head import *

from keras._tf_keras.keras.models import Sequential
from keras._tf_keras.keras.layers import Dense, LSTM as KerasLSTM, InputLayer, Dropout
from keras._tf_keras.keras.optimizers import Adam
from keras._tf_keras.keras.callbacks import ModelCheckpoint
from sklearn.preprocessing import MinMaxScaler
import json

class Method:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.name = config["name"]
        self.folder = config["folder"]["name"]

        self.scaler : MinMaxScaler = None
        self.raw_data : pd.DataFrame = None

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
            columns = list(self.raw_data.columns)

            columns = [f'{name}*' for name in columns]
            return pd.DataFrame(x_data, columns=columns)

        except Exception as e:
            print(f"[!] Postprocessing error: {e}")
            return None

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
            # preprocess data
            scaled_data = self.preprocess(data)
            x_seq, y_seq = [], []

            for i in range(self.seq_length, len(scaled_data)):
                x_seq.append(scaled_data[i - self.seq_length:i])
                y_seq.append(scaled_data[i, :])

            x, y = np.array(x_seq), np.array(y_seq)
            split = int(len(x) * self.train_split)

            self.x_train = x[:split]
            self.y_train = y[:split]
            self.x_test = x[split:]
            self.y_test = y[split:]
            
            # build model
            os.makedirs(f"{self.folder}/Scaled/History", exist_ok=True)
            os.makedirs(f"{self.folder}/Scaled/Stream", exist_ok=True)
            
            # Clean symbol for filename
            clean_symbol = symbol.replace('/', '_')
            pd.DataFrame(scaled_data).to_csv(f"{self.folder}/Scaled/History/scaled_{clean_symbol}.csv", index=False)
            
            input_shape = x.shape[1:]
            self.model.add(InputLayer(shape=input_shape))

            # Add LSTM layers - only the last one should not return sequences
            for i, units in enumerate(self.lstm_layers):
                return_sequences = i < len(self.lstm_layers) - 1  # False for last layer
                self.model.add(KerasLSTM(units, return_sequences=return_sequences))
                self.model.add(Dropout(0.2))  # Add dropout after each LSTM layer

            for units in self.dense_layers:
                self.model.add(Dense(units, activation='relu'))
                self.model.add(Dropout(0.2))  # Add dropout after each dense layer
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
        if self.built == False:
            print("[!] Model not built yet")
            return None
        
        if self.x_train is None or self.y_train is None:
            print("[!] No training data")
            return None
        
        try:
            checkpoint = ModelCheckpoint(
                filepath=f"{self.folder}/{self.name}.keras",
                monitor='val_loss',
                save_best_only=True,
                mode='min'
            )

            history = self.model.fit(
                x=self.x_train,
                y=self.y_train,
                batch_size=self.batch_size,
                epochs=self.epochs,
                validation_split=0.1,
                verbose=1,
                callbacks=[checkpoint]
            ) 
            # steps per epoch = len(x_train) / batch_size
            self.trained = True
            print(f"[o] Training loss: {history.history['loss'][-1]:.4f}")

        except Exception as e:
            print(f"[!] Training error: {e}")

    def test(self) -> None:
        if not self.trained:
            print("[!] Model not trained yet")
            return None
        
        try:
            loss = self.model.evaluate(self.x_test, self.y_test, verbose=0)
            print(f"[o] Test loss: {loss:.4f}")

        except Exception as e:
            print(f"[!] Testing error: {e}")

    def predict(self, data : pd.DataFrame, symbol : str) -> None:
        if not self.trained:
            #print("[!] Model not trained yet")
            return None
        
        if len(data) < self.seq_length + 1:
            print(f"[!] Insufficient data: need {self.seq_length + 1}, got {len(data)}")
            return None
        
        print(f"[+] Predicting {symbol}...")
        try:
            # Preprocess data and get initial input
            scaled_data = self.preprocess(data.iloc[-self.seq_length+1:])
            initial_input = np.array(scaled_data[-self.seq_length:])
       
            # Generate multiple prediction paths
            all_paths = self._generate_paths(initial_input)
            
            # Save paths and statistics
            self._save_paths(all_paths, symbol)
            
            print(f"[o] Generated {len(all_paths)} prediction paths for {symbol}")

        except Exception as e:
            print(f"[!] Predicting error: {e}")
            return None
        
    #enters only one branch of the tree
    def _generate_paths(self, initial_input: np.ndarray) -> List[List[np.ndarray]]:
        """Generate multiple prediction paths using MC Dropout for uncertainty estimation."""
        # Initialize with sample_size copies
        current_inputs = np.tile(initial_input, (self.sample_size, 1, 1))
        all_paths = [[] for _ in range(self.sample_size)]
        
        for step in range(self.future_step):
            # Use MC Dropout: keep dropout active during inference for uncertainty
            next_predictions = self.model(current_inputs, training=True).numpy()
            
            # Store predictions
            for path_idx in range(self.sample_size):
                all_paths[path_idx].append(next_predictions[path_idx])
            
            # Update inputs for next iteration
            new_inputs = []
            for path_idx in range(self.sample_size):
                current_seq = current_inputs[path_idx]
                predicted_step = next_predictions[path_idx].reshape(1, -1)
                new_seq = np.concatenate([current_seq[1:], predicted_step], axis=0)
                new_inputs.append(new_seq[-self.seq_length:])
            
            current_inputs = np.array(new_inputs)
        
        return all_paths

    def _save_paths(self, all_paths: List[List[np.ndarray]], symbol: str) -> None:
        """Save all prediction paths and calculate statistics."""
        try:
            # Clean symbol for filename
            clean_symbol = symbol.replace('/', '_')
            
            # Add timestamp for tracking
            from datetime import datetime
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Save individual paths
            for path_idx, path in enumerate(all_paths):
                path_array = np.array(path)
                processed_path = self.postprocess(path_array, symbol)
                
                # Add timestamp column
                processed_path['timestamp'] = timestamp
                processed_path['prediction_step'] = range(1, len(processed_path) + 1)
                
                path_filename = f'{self.folder}/Scaled/Stream/predicted_{clean_symbol}_path_{path_idx}.csv'
                
                processed_path.to_csv(path_filename, mode='w', header=True, index=False)
            
        except Exception as e:
            print(f"[!] Error saving paths: {e}")

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
                print(f"[>] Creating model for {symbol}: {model.name}")
                model.build(data, symbol)
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

    #def decide

































