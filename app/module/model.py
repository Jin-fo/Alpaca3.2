from head import *
import os
import pickle
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

from keras._tf_keras.keras.models import Sequential, load_model
from keras._tf_keras.keras.layers import Dense, LSTM as KerasLSTM, InputLayer
from keras._tf_keras.keras.optimizers import Adam
from keras._tf_keras.keras.callbacks import ModelCheckpoint
from sklearn.preprocessing import MinMaxScaler


class LSTM:
    def __init__(self, symbol: str, config: Dict[str, int]):
        self.folder = None  # Add folder attribute to be set by Model class
        self.name = f"LSTM_{symbol}"
        self.model = Sequential(name=f"{self.name}")
        self.config = config
        self.dataset : dict[str, np.ndarray] = {}
        self.data_input = None
        self.scalers : dict[str, MinMaxScaler] = {}
        
    def build(self) -> None:
        def _add_layer(x_train: np.ndarray) -> Sequential:
            print(f"[>] Building model with input shape: {x_train.shape}")
            
            input_shape = x_train.shape[1:]
            
            #add input layer
            self.model.add(InputLayer(shape=input_shape))

            #add lstm layers
            for i, units in enumerate(self.config['lstm_units']):
                return_sequences = i < len(self.config['lstm_units']) - 1
                self.model.add(KerasLSTM(units, return_sequences=return_sequences))

            #add dense layers
            for units in self.config['dense_units'][:-1]:
                self.model.add(Dense(units, activation='relu'))
            #add output layer
            self.model.add(Dense(self.config['dense_units'][-1]))
            return self.model
        
        try:
            if 'x_train' not in self.dataset or self.dataset['x_train'] is None:
                print(f"[!] No training data available for building model")
                return None
            
            # Reset the model to avoid adding layers to an existing model
            self.model = Sequential(name=f"{self.name}")
                
            self.model = _add_layer(self.dataset['x_train'])
            self.model.compile(
                optimizer=Adam(learning_rate=self.config['learning_rate']), 
                loss=self.config['loss']
            )
            print(f"[>] Model built: {self.model}")
            self.built = True
        except Exception as e:
            print(f"[!] Error building model: {e}")
            return None
        
    def train(self) -> None:
        if 'x_train' not in self.dataset or self.dataset['x_train'] is None or 'y_train' not in self.dataset or self.dataset['y_train'] is None:
            print("[!] No data to process")
            return
        
        if not self.built or self.model is None:
            print("[!] Model not built properly. Cannot train.")
            return
        
        try:
            model_checkpoint = ModelCheckpoint(
                filepath=f"{self.folder}/{self.name}.keras",  # Default to models directory
                monitor='val_loss',
                save_best_only=True,
                save_weights_only=False,
                mode='min'
            )
        
            history = self.model.fit(
                x=self.dataset['x_train'], 
                y=self.dataset['y_train'], 
                batch_size=self.config['batch_size'],
                epochs=self.config['epochs'],
                validation_split=0.1, # last 10% of data for validation
                verbose=0,
                callbacks=[model_checkpoint]
            )
            print(f"[o] Training loss: {history.history['loss'][-1]}")
            print(f"[o] Validation loss: {history.history['val_loss'][-1]}")

        except Exception as e:
            print(f"[!] Error training model: {e}")
            return None

    def test(self) -> None:
        if 'x_test' not in self.dataset or self.dataset['x_test'] is None or 'y_test' not in self.dataset or self.dataset['y_test'] is None:
            print("[!] No data to process")
            return
        
        if not self.built or self.model is None:
            print("[!] Model not built properly. Cannot test.")
            return
        
        try:
            result = self.model.evaluate(self.dataset['x_test'], self.dataset['y_test'], verbose=0)
            print(f"[o] Test loss: {result}")
            
        except Exception as e:
            print(f"[!] Error assessing model: {e}")
            return None
        
    def operate(self, data_input: dict[str, np.ndarray]) -> None:
        """Generate predictions using the trained model"""
        if not self.built or self.model is None:
            print("[!] Model not built. Cannot operate.")
            return
            
        try:
            print(f"[>] Running model: {self.name}")
            
            # Reshape input to (1, sequence_length, features)
            x_input = data_input['x_input']
            x_input = x_input.reshape(1, x_input.shape[0], x_input.shape[1])
            print(f"[>] Reshaped input: {x_input.shape}")
            
            future = self.model.predict(x_input)
            print(f"[o] Predicted future:\n{future}")
            
        except Exception as e:
            print(f"[!] Error operating model: {e}")

class Model:
    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.config = None
        self.model_dict : dict[str, any] = {}
        self.scalers = {}  # Dictionary to store scalers for each symbol

    def preprocess(self, data: pd.DataFrame) -> dict[str, np.ndarray] | None:
    
        def _delta_timestamp(data: pd.DataFrame) -> pd.DataFrame:
            try:
                # Create explicit copy to avoid SettingWithCopyWarning
                data_copy = data.copy()
                
                # Convert to datetime (if not already)
                if "delta_minute" not in data_copy.columns:
                    # Convert timestamp to datetime and calculate deltas
                    data_copy['timestamp'] = pd.to_datetime(data_copy['timestamp'], errors='coerce')
                    data_copy['timestamp'] = data_copy['timestamp'].diff().dt.total_seconds() / 60
                    data_copy['timestamp'] = data_copy['timestamp'].fillna(0).infer_objects(copy=False).astype('float64')
                    data_copy = data_copy.rename(columns={'timestamp': 'delta_minute'})
                
                return data_copy
            except Exception as e:
                print(f"[!] Error flattening timestamp: {e}")
                return data

        if data is None or data.empty:
            print("[!] No data to process")
            return None
        
        symbol = data.index[0]
        if "/" in symbol:
            symbol = symbol.replace("/", "_")
            
        print(f"[>] Preprocessing data for {symbol}")
        print(f"[>] Data shape: {data.shape}, Columns: {data.columns}")

        try:
            data = _delta_timestamp(data)

            seq_len = self.config['sequence_length']

            if len(data) == seq_len+1:
                # Check if we have a saved scaler for this symbol
                if symbol in self.scalers:
                    print(f"[>] Using saved scaler for {symbol}")
                    scaled = self.scalers[symbol].transform(data)
                else:
                    # If no saved scaler, use the general one
                    print(f"[>] No saved scaler found for {symbol}, using general scaler")
                    scaled = self.scalers[symbol].transform(data)
                
                x_input = np.array(scaled[-seq_len:])

                pd.DataFrame(scaled).to_csv(f'Scaled/Stream/scaled_{symbol}.csv', index=False)
                return {"x_input": x_input}
            
            else:
                x_seq = []
                y_seq = []

                # For historical data, fit and save the scaler
                self.scalers[symbol] = MinMaxScaler(feature_range=(0, 1))
                scaled = self.scalers[symbol].fit_transform(data)
                
                # Save the scaler for future use
                scaler_file = f"{self.folder}/scaler_{symbol}.pkl"
                with open(scaler_file, 'wb') as f:
                    pickle.dump(self.scalers[symbol], f)
                print(f"[>] Saved scaler for {symbol} to {scaler_file}")
                
                for i in range(seq_len, len(scaled)):
                    x_seq.append(scaled[i - seq_len:i])
                    y_seq.append(scaled[i, :])

                x, y = np.array(x_seq), np.array(y_seq)
                
                split = int(len(x) * self.config['train_split'])
                if split == 0:
                    print("[!] Train split too small")
                    return None

                x_train, x_test = x[:split], x[split:]
                y_train, y_test = y[:split], y[split:]
                # NumPy arrays don't have to_csv method, using pandas to save it
                pd.DataFrame(scaled).to_csv(f'Scaled/History/scaled_{symbol}.csv', index=False)
                #print(f"[o] Shapes - X_train: {x_train.shape}, Y_train: {y_train.shape}, X_test: {x_test.shape}, Y_test: {y_test.shape}")
                return {"x_train": x_train, "y_train": y_train, "x_test": x_test, "y_test": y_test}

        except Exception as e:
            print(f"[!] Preprocessing error: {e}")
            return None

    def postprocess(self, data: pd.DataFrame) -> None:
        pass
    
    async def create(self, data: pd.DataFrame, config: Dict[str, int]) -> None:
        symbol = data.index[0]

        if "/" in symbol:
            symbol = symbol.replace("/", "_")
            
        # Try to load a saved scaler if it exists
        scaler_file = f"{self.folder}/scaler_{symbol}.pkl"
        if os.path.exists(scaler_file):
            try:
                with open(scaler_file, 'rb') as f:
                    self.scalers[symbol] = pickle.load(f)
                print(f"[>] Loaded saved scaler for {symbol}")
            except Exception as e:
                print(f"[!] Error loading scaler: {e}")
                
        # Always recreate the model for consistency
        self.model_dict[symbol] = LSTM(symbol, config)
        self.model_dict[symbol].folder = self.folder
        self.config = config
        
        print(f"-----------------------------------------------------")
        print(f"[>] Created model {self.model_dict[symbol].name}")

        dataset = self.preprocess(data)
        if dataset is None:
            print(f"[!] Failed to preprocess data for {symbol}")
            return None
            
        self.model_dict[symbol].dataset = dataset
        
        self.model_dict[symbol].build()
        self.model_dict[symbol].train()
        self.model_dict[symbol].test()
        self.model_dict[symbol].model.summary()
    
    async def assess(self, symbol: str) -> None:
        if "/" in symbol:
            symbol = symbol.replace("/", "_")

        if symbol not in self.model_dict.keys():
            print(f"[!][Assess] Model {symbol} does not exist")
            return None

        self.model_dict[symbol].test()

    async def predict(self, data: pd.DataFrame) -> None:
        symbol = data.index[0]  
        symbol = symbol.replace('/', '_')  # Replace / with _

        if symbol not in self.model_dict.keys():
            print(f"[!][Predict] Model {symbol} does not exist")
            return None
        data = data.iloc[-(self.config['sequence_length']+1):]
        data_input = self.preprocess(data)

        if data_input is None:
            print(f"[!] Failed to preprocess data for {symbol}")
            return None
 
        self.model_dict[symbol].operate(data_input)

        return None