from head import *
import os
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
        
    def build(self) -> None:
        def _add_layer(x_train: np.ndarray) -> any:
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
            self.model = _add_layer(self.dataset['x_train'])
            self.model.compile(
                optimizer=Adam(learning_rate=self.config['learning_rate']), 
                loss=self.config['loss']
            )
            self.model.summary()

            print(f"Loading model for {self.name}")
        except Exception as e:
            print(f"Error building model: {e}")
            return None
        
    def train(self) -> None:
        if self.dataset['x_train'] is None or self.dataset['y_train'] is None:
            print("[!] No data to process")
            return
        
        print(f"Training model {self.name}")
        
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
                verbose=1,
                callbacks=[model_checkpoint]
            )
            print(f"history: {history.history}")

        except Exception as e:
            print(f"Error training model: {e}")
            return None

    def test(self) -> None:
        if self.dataset['x_test'] is None or self.dataset['y_test'] is None:
            print("[!] No data to process")
            return
        
        print(f"Assessing model {self.name}")
        
        try:
            result = self.model.evaluate(self.dataset['x_test'], self.dataset['y_test'], verbose=2)
            print(f"{self.model.name} result: {result}")
            return result
        except Exception as e:
            print(f"Error assessing model: {e}")
            return None
        
    def operate(self) -> None:
        """Generate predictions using the trained model"""
        if not hasattr(self, 'model') or self.model is None:
            print("[!] Model not built. Cannot operate.")
            return
            
        try:
            print(f"[o] Running model: {self.name}")
            self.model.summary()
            
            # Here you could add code to make predictions
            # This would depend on your specific requirements
            # For example, making future predictions based on the latest data
        except Exception as e:
            print(f"[!] Error operating model: {e}")


class Model:
    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.config = None
        self.model_list : dict[str, any] = {}

    def preprocess(self, data: pd.DataFrame) -> None:
        def _flatten_timestamp(data: pd.DataFrame) -> pd.DataFrame:
            try:
                timestamps = data.index.get_level_values('timestamp')
                reference = timestamps[0]
                minutes = (timestamps - reference).total_seconds() / 60
                new_index = pd.MultiIndex.from_arrays([minutes], names=['timestamp'])
                data.index = new_index
                data = data.reset_index(level='timestamp')
                return data
            except Exception as e:
                print(f"Error flattening timestamp: {e}")
                return data
        
        if data is None or data.empty:
            print("[!] No data to process")
            return None
        
        print(f"[>] Preprocessing data for {data.index[0]}")
        
        data = _flatten_timestamp(data)

        try:
            scaled_data = self.scaler.fit_transform(data)

            x_seq, y_seq = [], []
            for i in range(self.config['sequence_length'], len(scaled_data)):
                if scaled_data.shape[1] == 1:
                    x_seq.append(scaled_data[i-self.config['sequence_length']:i, 0])
                else:
                    x_seq.append(scaled_data[i-self.config['sequence_length']:i, :])
                y_seq.append(scaled_data[i, :])
            
            x_train = np.array(x_seq)
            y_train = np.array(y_seq)
            train_length = int(len(scaled_data) * self.config['train_split'])

            x_test = x_train[train_length:]
            y_test = y_train[train_length:]

            x_train = x_train[:train_length]
            y_train = y_train[:train_length]


            if len(x_train.shape) == 2:
                x_train = np.reshape(x_train, (x_train.shape[0], x_train.shape[1], 1))
                
            return {"x_train": x_train, "y_train": y_train, "x_test": x_test, "y_test": y_test}
        except Exception as e:
            print(f"Error preprocess data: {e}")
            return None
        
    async def create(self, symbol: str, config: Dict[str, int]) -> None:
        if '/' in symbol:
            symbol = symbol.replace('/', '_')
        
        if symbol in self.model_list.keys():
            print(f"Model {symbol} already exists")
            return None
        
        if config['model_type'] == "LSTM":
            self.model_list[symbol] = LSTM(symbol, config)
            # Set the folder attribute to be used in train
            self.model_list[symbol].folder = self.folder
            # Store the config for use in preprocess method
            self.config = config
            print(f"Created model {self.model_list[symbol].name}")
        else:
            print(f"Model type {config['model_type']} not supported")
            return None
    
    async def source(self, symbol: str, data: pd.DataFrame) -> None:
        if '/' in symbol:
            symbol = symbol.replace('/', '_')
        
        if symbol not in self.model_list.keys():
            print(f"Model {symbol} does not exist")
            return None

        self.model_list[symbol].dataset = self.preprocess(data)

        self.model_list[symbol].build()
        self.model_list[symbol].train()
        self.model_list[symbol].test()

    async def assess(self, symbol: str) -> None:
        if '/' in symbol:
            symbol = symbol.replace('/', '_')
        
        if symbol not in self.model_list.keys():
            print(f"Model {symbol} does not exist")
            return None

        self.model_list[symbol].test()