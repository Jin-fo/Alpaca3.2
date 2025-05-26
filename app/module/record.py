from head import *

class Record:
    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self.columns = None

    def set_columns(self, columns: List[str]) -> None:
        self.columns = columns
    
    async def write(self, data: Dict[str, pd.DataFrame]) -> None:
        """Write data concurrently with one thread per file"""
        if not data:
            return
            
        def _write_file(symbol: str, df: pd.DataFrame) -> None:
            """Write single file synchronously"""
            filename = f"{self.folder}/{symbol.replace('/', '_')}.csv" 
            df.to_csv(filename)

        write_tasks = []
        for symbol, df in data.items():
            if df is not None and not df.empty:
                task = asyncio.to_thread(_write_file, symbol, df)
                write_tasks.append(task)
        
        if write_tasks:
            await asyncio.gather(*write_tasks, return_exceptions=True)

    async def read(self, symbols: Union[str, List[str]]) -> Dict[str, pd.DataFrame]:
        """Read data concurrently"""
        if isinstance(symbols, str):
            symbols = [symbols]
        def _read_file(symbol: str) -> Optional[pd.DataFrame]:
            """Read single file synchronously"""
            filename = f"{self.folder}/{symbol.replace('/', '_')}.csv"
            if not os.path.exists(filename):
                return None
            try:
                # Read CSV without date parsing (faster)
                df = pd.read_csv(filename, index_col=[0, 1])
                # Convert timestamp index to datetime (more reliable)
                df.index = df.index.set_levels(
                    pd.to_datetime(df.index.levels[1]), level=1
                )
                # Filter columns if specified
                if self.columns:
                    available_cols = [col for col in self.columns if col in df.columns]
                    if available_cols:
                        df = df[available_cols]
                
                return df
            except Exception as e:
                print(f"[!] Error reading {symbol}: {e}")
            return None
        
        read_tasks = []
        for symbol in symbols:
            task = asyncio.to_thread(_read_file, symbol)
            read_tasks.append(task)
        
        results = await asyncio.gather(*read_tasks, return_exceptions=True)
        # Return as dictionary
        return {symbol: result for symbol, result in zip(symbols, results) 
                if isinstance(result, pd.DataFrame)}

    async def append(self, data: Union[pd.DataFrame, Dict]) -> pd.DataFrame:
        df = data if isinstance(data, pd.DataFrame) else pd.DataFrame(data)
        
        mode = 'w' if not os.path.exists(self.filename) else 'a'
        header = mode == 'w'
        
        df.to_csv(self.filename, mode=mode, header=header, index=True)
        print(f"Appended {len(df)} records to {self.filename}")
        return df
        
