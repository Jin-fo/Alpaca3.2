from head import *
from scipy.stats import norm

from py_vollib.black_scholes.implied_volatility import implied_volatility
from py_vollib.black_scholes import black_scholes as bs
from py_vollib.black_scholes.greeks.analytical import delta, gamma, theta, vega, rho
                # expiry_date = datetime.strptime(chain_df['expiration_date'].iloc[0], '%Y-%m-%d')
                # time_to_expiry = max((expiry_date - datetime.now()).days / 365.0, 0.0001)  # Ensure positive time
                
                # # Risk-free rate (using current 3-month T-bill rate as approximation)
                # risk_free_rate = 0.05  # 5% as a reasonable approximation
                

                #     # Calculate implied volatility using mid price
                #     mid_price = (bid_price + ask_price) / 2 if bid_price is not None and ask_price is not None else None
                #     stock_price = row['strike_price']
                    
                #     iv = self.math.implied_volatility(stock_price, row['strike_price'], time_to_expiry, risk_free_rate, mid_price, row['option_type'])
                    
class Math:
    def __init__(self):
        pass
    

    
    def implied_volatility(self, stock_price: float, strike_price: float, time_to_expiry: float, risk_free_rate: float, option_price: float, option_type: str) -> float:
        try:
            S = float(stock_price)
            K = float(strike_price)
            t = float(time_to_expiry)  # Already in years
            r = float(risk_free_rate)
            price = float(option_price)
        
            if price <= 0 or S <= 0 or K <= 0 or t <= 0:
                print("Invalid input values detected")
                return None
                
            # Calculate implied volatility
            flag = 'c' if option_type == 'C' else 'p'
            iv = implied_volatility(price, S, K, t, r, flag)
            return iv
        except Exception as e:
            print(f"Error in IV calculation: {str(e)}")
            return None
        
    async def calculate_fair_price(self, chain: pd.DataFrame, symbols: List[str]) -> pd.DataFrame:
        def _put_call_parity(chain: pd.DataFrame) -> pd.DataFrame:
            if 'option_type' not in chain.columns:
                return pd.DataFrame()
            
            # Reset index and prepare data
            chain = chain.reset_index()
            now = pd.Timestamp.now(tz='UTC')
            
            # Process expiration date
            if 'expiration_date' not in chain.columns:
                return pd.DataFrame()
                
            chain['expiration_date'] = pd.to_datetime(chain['expiration_date'])
            if chain['expiration_date'].dt.tz is None:
                chain['expiration_date'] = chain['expiration_date'].dt.tz_localize('UTC')
            
            # Calculate time to expiry and risk-free rate
            chain['T'] = (chain['expiration_date'] - now).dt.total_seconds() / (365 * 24 * 60 * 60)
            chain['r'] = chain.get('risk_free_rate', 0.05)

            # Calculate weighted prices
            chain['adjusted_price'] = chain.apply(
                lambda row: ((row['bid_price'] * row['ask_size']) + (row['ask_price'] * row['bid_size'])) / 
                          (row['bid_size'] + row['ask_size']) if row['bid_size'] + row['ask_size'] > 0 else np.nan,
                axis=1
            )

            # Get calls and puts
            calls = chain[chain['option_type'] == 'C'][['strike_price', 'adjusted_price', 'T', 'r']].rename(
                columns={'adjusted_price': 'call_price'}
            )
            puts = chain[chain['option_type'] == 'P'][['strike_price', 'adjusted_price']].rename(
                columns={'adjusted_price': 'put_price'}
            )
            
            if len(calls) == 0 or len(puts) == 0:
                return pd.DataFrame()
            
            # Calculate fair price
            result = pd.merge(calls, puts, on='strike_price')
            result['S'] = result['call_price'] - result['put_price'] + result['strike_price'] * np.exp(-result['r'] * result['T'])
            
            # Add average and return final result
            result = result[['strike_price', 'S']]
            result.loc['Average'] = ['-', result['S'].mean()]
            
            return result

        def _calculate_sigma_metrics(symbol: str, fair_price: pd.DataFrame, chain: pd.DataFrame) -> pd.DataFrame:
            S = fair_price['S'].iloc[-1]
            IV = chain['implied_volatility'].mean()
            sigma = S * IV * np.sqrt(1 / 252)
            sigma_pct = (sigma / S) * 100
            
            return pd.DataFrame({
                'metric': [f'{symbol} fair price', 'IV', 'sigma (daily)', '±1sigma (68%)', '±2sigma (95%)', '±3sigma (99.7%)'],
                'value': [
                    round(S, 2),
                    round(IV, 4),
                    f"{round(sigma, 2)} ({round(sigma_pct, 2)}%)",
                    f"({round(S - sigma, 2)}, {round(S + sigma, 2)})",
                    f"({round(S - 2*sigma, 2)}, {round(S + 2*sigma, 2)})",
                    f"({round(S - 3*sigma, 2)}, {round(S + 3*sigma, 2)})"
                ]
            }).set_index('metric')
        
        results = {}
        for symbol in symbols:
            if symbol not in chain or not isinstance(chain[symbol], pd.DataFrame):
                print(f"[!] Skipped {symbol}: Invalid data")
                continue
                
            symbol_chain = chain[symbol]
            fair_price = _put_call_parity(symbol_chain)
            
            if fair_price.empty:
                print(f"[!] Skipped {symbol}: No options data")
                continue
                
            if 'implied_volatility' in symbol_chain.columns:
                sigma_metrics = _calculate_sigma_metrics(symbol, fair_price, symbol_chain)
                results[symbol] = {
                    'fair_price': fair_price,
                    'sigma_metrics': sigma_metrics
                }
                print(sigma_metrics)
            else:
                results[symbol] = {'fair_price': fair_price}
                print(f"[+] {symbol} fair price: {fair_price['S'].iloc[-1]:.2f}")
        
        return results

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
            df = pd.read_csv(filename, index_col=[0])
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
            symbol = data.index[0][0]  # Get the symbol part of the tuple
            # Clean the symbol for filename
            clean_symbol = symbol.replace('/', '_')
            
            filename = f"{self.folder}/{clean_symbol}.csv"
            
            # Determine mode and header
            file_exists = os.path.exists(filename)
            mode = 'a' if file_exists else 'w'
            header = not file_exists
            
            # Write to CSV
            print(f"[+] Appending path: {filename}")
            data.to_csv(filename, mode=mode, header=header)
            
            
        except Exception as e:
            print(f"[!] Error appending data: {e}")
            print(f"[DEBUG] Full error details: {str(e)}")
