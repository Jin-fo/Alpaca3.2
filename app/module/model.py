from head import *
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

from keras._tf_keras.keras.models import Sequential, load_model
from keras._tf_keras.keras.layers import Dense, LSTM as KerasLSTM, InputLayer
from keras._tf_keras.keras.optimizers import Adam
from keras._tf_keras.keras.callbacks import ModelCheckpoint
from sklearn.preprocessing import MinMaxScaler

class Model:
    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self.scaler = MinMaxScaler(feature_range=(0, 1))
        self.config = None
        self.model_list : dict[str, any] = {}

    def get_model(self, symbol: str) -> any:
        try:
            return self.model_list.get(symbol)
        except Exception as e:
            print(f"Error getting model: {e}")
            return None
    
    def clear_model(self,) -> None:
        self.model_list = {}
    
    def preprocess(self, data: pd.DataFrame) -> pd.DataFrame:
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
            self.scaled_data = self.scaler.fit_transform(data)
            self.train_portion = int(len(self.scaled_data) * self.config['train_split'])
            
            x_seq, y_seq = [], []
            for i in range(self.config['sequence_length'], len(self.scaled_data)):
                if self.scaled_data.shape[1] == 1:
                    x_seq.append(self.scaled_data[i-self.config['sequence_length']:i, 0])
                else:
                    x_seq.append(self.scaled_data[i-self.config['sequence_length']:i, :])
                y_seq.append(self.scaled_data[i, :])
            
            x_train, y_train = np.array(x_seq), np.array(y_seq)

            if len(x_train.shape) == 2:
                x_train = np.reshape(x_train, (x_train.shape[0], x_train.shape[1], 1))
                
            return x_train,  y_train
        except Exception as e:
            print(f"Error preprocess data: {e}")
            return None

    def postprocess(self, data: pd.DataFrame) -> pd.DataFrame:
        pass

    def save(self, name: str) -> None:
        self.model.save(f"{self.folder}/{name}.keras")

    def load(self, name: str) -> None:
        self.model = load_model(f"{self.folder}/{name}.keras")
    
    def LSTM(self, name: str, config: Dict[str, int]):
        self.config = config
        return LSTMModel(name, config, self)


class LSTMModel:
    def __init__(self, name: str, config: Dict[str, int], shared: Model):
        self.shared = shared
        self.name = name
        self.config = config
        
        self.symbol = None
        self.x_train = None
        self.y_train = None
        self.model = None

    async def build(self, symbol: str, df: pd.DataFrame) -> None:
        def _add_layer(model: any, x_train: np.ndarray) -> any:
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
        
        if '/' in symbol:
            symbol = symbol.replace('/', '_')
        
        try:
            self.model = Sequential(name=f"{self.name}_{symbol}")

            self.x_train, self.y_train = self.shared.preprocess(df)

            self.model = _add_layer(self.model, self.x_train)
            self.model.compile(
                optimizer=Adam(learning_rate=self.config['learning_rate']), 
                loss=self.config['loss']
            )
            self.model.summary()

            self.shared.model_list[symbol] = self

        except Exception as e:
            print(f"Error building model: {e}")

    async def train(self, symbol: str) -> None:
        if '/' in symbol:
            symbol = symbol.replace('/', '_')
        try:
            self.symbol = symbol
            self.model = self.shared.get_model(symbol).model
            self.x_train = self.shared.get_model(symbol).x_train
            self.y_train = self.shared.get_model(symbol).y_train
        except Exception as e:
            print(f"Error training model: {e}")
            return

        if self.x_train is None or self.y_train is None:
            print("[!] No data to process")
            return
        
        print(f"Training model {self.name}_{self.symbol}")
        
        try:
            model_checkpoint = ModelCheckpoint(
                filepath=f"{self.shared.folder}/{self.name}_{self.symbol}.keras",
                monitor='val_loss',
                save_best_only=True,
                save_weights_only=False,
                mode='min'
            )
        
            history = self.model.fit(
                self.x_train, self.y_train, 
                batch_size=self.config['batch_size'],
                epochs=self.config['epochs'],
                validation_split=0.1, # 10% of data for validation
                verbose=1,
                callbacks=[model_checkpoint]
            )
            print(f"history: {history.history}")

        except Exception as e:
            print(f"Error training model: {e}")
            return None

    def test(self):
        result = self.model.evaluate(self.x_test, self.y_test, verbose=2)
        return result

    def operate(self):
        self.model.summary()
        pass
        
    def save(self) -> None:
        self.model.save(f"{self.folder}/{self.name}.keras")
