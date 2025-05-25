from head import *

class Stats:
    def __init__(self):
        os.makedirs('data', exist_ok=True)
        self.filename: str = None
        self.columns: Optional[List[str]] = None

    async def write(self, data: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        try:
            for symbol, df in data.items():
                filename = f"data/{symbol.replace('/', '_')}.csv"
                df.to_csv(filename)
        except Exception as e:
            print(f"[!] Error writing data: {e}")
            return None
        return data
    
    async def read(self, symbol: str) -> pd.DataFrame:
        filename = f"data/{symbol.replace('/', '_')}.csv"
        if not os.path.exists(filename):
            return None

        return pd.read_csv(filename, parse_dates=[0], index_col=0)











    def __init__(self, symbol: str, columns: Optional[List[str]] = None):
        self.symbol = symbol
        self.filename = f"data/{symbol.replace('/', '_')}.csv"
        self.columns = columns
        os.makedirs('data', exist_ok=True)

    def write(self, data: pd.DataFrame) -> pd.DataFrame:
        data.to_csv(self.filename)
        print(f" | File: {self.filename}")
        return data

    def read(self, columns: Optional[Union[str, List[str]]] = None) -> pd.DataFrame:
        df = pd.read_csv(self.filename, parse_dates=[0], index_col=0)
        
        if columns is None:
            return df
            
        target_columns = [columns] if isinstance(columns, str) else columns
        available_columns = [col for col in target_columns if col in df.columns]
        
        return df[available_columns] if available_columns else df

    def append(self, data: Union[pd.DataFrame, Dict]) -> pd.DataFrame:
        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
        
        mode = 'w' if not os.path.exists(self.filename) else 'a'
        header = mode == 'w'
        
        df.to_csv(self.filename, mode=mode, header=header, index=True)
        print(f"Appended {len(df)} records to {self.filename}")
        return df
        
