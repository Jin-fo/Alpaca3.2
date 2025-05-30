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
        self.columns = None

    def set_columns(self, columns: List[str]) -> None:
        self.columns = columns

    def preprocess(self, data: pd.DataFrame) -> Dict[str, np.ndarray]:
        if not self.columns:
            print("[!] No columns to process")
            return None
        print(f"begin preprocess data for {data.index[0]}")

        if len(self.columns) == 1:
            data = data.reshape(-1, 1)

        self.scaled_data = self.scaler.fit_transform(data)
        self.train_portion = int(len(self.scaled_data) * self.config['train_split'])

        return self.scaled_data

    def save(self, name: str) -> None:
        self.model.save(f"{self.folder}/{name}.keras")

    def load(self, name: str) -> None:
        self.model = load_model(f"{self.folder}/{name}.keras")
    
    def LSTM(self, name: str, config: Dict[str, int]):
        return LSTMModel(name, config, self)


class LSTMModel:
    def __init__(self, name: str, config: Dict[str, int], shared: Model):
        self.shared = shared
        self.name = name
        self.config = config
        self.model = Sequential(name=name)
        
        self.x_train = None
        self.y_train = None
        self.train_length = 0
        
    def set_dimension(self, columns: List[str]) -> None:
        self.shared.set_columns(columns)
        
    def build(self):
        self.model.compile(
            optimizer=Adam(learning_rate=self.config['learning_rate']), 
            loss=self.config['loss']
        )
        self.model.summary()
        
    async def train(self, data: Dict[str, pd.DataFrame]) -> Dict[str, float]:
        if data is None or len(data) == 0:
            print("[!] No data to process")
            return None
        
        history = {}
        for symbol, df in data.items():
            x_train, y_train = self.shared.preprocess(df)
            
            model_checkpoint = ModelCheckpoint(
                filepath=f"{self.folder}/{self.name}_{symbol}.keras",
                monitor='val_loss',
                save_best_only=True,
                save_weights_only=False,
                mode='min'
            )
            
            history = self.model.fit(
                x_train, y_train, 
                batch_size=self.config['batch_size'],
                epochs=self.config['epochs'],
                validation_split=0.1,
                verbose=1,
                callbacks=[model_checkpoint]
            )
            history[symbol] = history.history
        return history

    def test(self):
        result = self.model.evaluate(self.x_test, self.y_test, verbose=2)
        return result

    def operate(self):
        guess = self.model.predict(self.x_test)
        return guess
        
    def save(self) -> None:
        self.model.save(f"{self.folder}/{self.name}.keras")
