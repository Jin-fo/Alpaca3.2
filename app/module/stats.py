from head import *

import matplotlib.pyplot as plt
import csv

class Stats:
    data = None
    symbol = None
    filename = None
    column = None

    def __init__(self, symbol: str, column: list[str] = None): 
        self.symbol = symbol
        self.filename = f"data/{symbol.replace('/', '_')}_stream.csv"
        self.column = column
        
        os.makedirs('data', exist_ok=True)
    def write(self, data: pd.DataFrame = None) -> pd.DataFrame:
        os.makedirs(os.path.dirname(self.filename), exist_ok=True)
        self.data = data

        # Write data
        self.data.to_csv(self.filename)
        print(f" |Filed: {self.filename}")
        return self.data    
    
    def read(self, column: int) -> pd.DataFrame:
        df = pd.read_csv(self.filename, parse_dates=[0], index_col=0)
        
        if isinstance(column, (str, list)):
            # Convert single string to list
            columns_to_get = [column] if isinstance(column, str) else column
            
            # Filter to only include columns that exist in the DataFrame
            valid_columns = [col for col in columns_to_get if col in df.columns]
            
            if valid_columns:
                return df[valid_columns]
            else:
                return df
        else:
                return df
        
    def append(self, data) -> pd.DataFrame:
        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
        
        # Create file with headers if it doesn't exist
        if not os.path.exists(self.filename):
            os.makedirs(os.path.dirname(self.filename), exist_ok=True)
            df.to_csv(self.filename, index=True)
        else:
            # Append without headers to existing file
            df.to_csv(self.filename, mode='a', header=False, index=True)
            
        print(f"Appended {len(df)} records to {self.filename}")
        return df
        
