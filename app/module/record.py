from head import *

class Record:
    def __init__(self, folder: str):
        self.folder = folder
        os.makedirs(folder, exist_ok=True)
        self.columns = None
        #self.file_path : Dict[str, str] = {}
        
    def set_columns(self, columns: List[str]) -> None:
        self.columns = columns
    
    async def write(self, data: Dict[str, pd.DataFrame]) -> None:
        """Write data concurrently with one thread per file"""
        if not data:
            print("[!] No data to write")

        def _write_file(symbol: str, df: pd.DataFrame) -> None:
            """Write single file synchronously"""
            filename = f"{self.folder}/{symbol.replace('/', '_')}.csv" 
            print(f"[>] Writing path: {filename}")
            df.to_csv(filename)        

        try:   
            write_tasks = []
            for symbol, df in data.items():
                task = asyncio.to_thread(_write_file, symbol, df)
                write_tasks.append(task)
            
                if write_tasks:
                    await asyncio.gather(*write_tasks, return_exceptions=True)
        except Exception as e:
            print(f"[!] Error writing data: {e}")

    async def read(self, symbols: Union[str, List[str]]) -> Dict[str, pd.DataFrame]:
        """Read data concurrently"""
        if isinstance(symbols, str):
            symbols = [symbols]

        def _read_file(symbol: str) -> Optional[pd.DataFrame]:
            """Read single file synchronously"""
            filename = f"{self.folder}/{symbol.replace('/', '_')}.csv"
            if not os.path.exists(filename):
                return None

            print(f"[<] Reading path: {filename}")
            df = pd.read_csv(filename, index_col=[0, 1])
            df.index = df.index.set_levels(
                pd.to_datetime(df.index.levels[1]), level=1
            )
            if self.columns:
                available_cols = [col for col in self.columns if col in df.columns]
                if available_cols:
                    df = df[available_cols]
            return df

        try:     
            read_tasks = []
            for symbol in symbols:         
                task = asyncio.to_thread(_read_file, symbol)
                read_tasks.append(task) 
            results = await asyncio.gather(*read_tasks, return_exceptions=True)
            # Return as dictionary
            return {symbol: result for symbol, result in zip(symbols, results) 
                    if isinstance(result, pd.DataFrame)}
        except Exception as e:
            print(f"[!] Error reading data: {e}")
            return {}
        
    async def append(self, data: pd.DataFrame) -> None:
        """Append data to existing files"""
        if data.empty:
            print("[!] No data to append")
            return

        try:
            # Get symbol from the MultiIndex
            symbol = data.index[0][0]
            filename = f"{self.folder}/{symbol.replace('/', '_')}.csv"
            
            # Determine mode and header
            file_exists = os.path.exists(filename)
            mode = 'a' if file_exists else 'w'
            header = not file_exists
            
            # Write to CSV
            data.to_csv(filename, mode=mode, header=header)
            print(f"[+] Appended to {filename}")
            
        except Exception as e:
            print(f"[!] Error appending data: {e}")
