from head import *
from scipy.stats import norm

from py_vollib.black_scholes.implied_volatility import implied_volatility
from py_vollib.black_scholes import black_scholes as bs

                # expiry_date = datetime.strptime(chain_df['expiration_date'].iloc[0], '%Y-%m-%d')
                # time_to_expiry = max((expiry_date - datetime.now()).days / 365.0, 0.0001)  # Ensure positive time
                
                # # Risk-free rate (using current 3-month T-bill rate as approximation)
                # risk_free_rate = 0.05  # 5% as a reasonable approximation
                

                #     # Calculate implied volatility using mid price
                #     mid_price = (bid_price + ask_price) / 2 if bid_price is not None and ask_price is not None else None
                #     stock_price = row['strike_price']
                    
                #     iv = self.math.implied_volatility(stock_price, row['strike_price'], time_to_expiry, risk_free_rate, mid_price, row['option_type'])
                    
# class Math:
#     def __init__(self):
#         pass
    

    
#     def implied_volatility(self, stock_price: float, strike_price: float, time_to_expiry: float, risk_free_rate: float, option_price: float, option_type: str) -> float:
#         try:
#             S = float(stock_price)
#             K = float(strike_price)
#             t = float(time_to_expiry)  # Already in years
#             r = float(risk_free_rate)
#             price = float(option_price)
        
#             if price <= 0 or S <= 0 or K <= 0 or t <= 0:
#                 print("Invalid input values detected")
#                 return None
                
#             # Calculate implied volatility
#             flag = 'c' if option_type == 'C' else 'p'
#             iv = implied_volatility(price, S, K, t, r, flag)
#             return iv
#         except Exception as e:
#             print(f"Error in IV calculation: {str(e)}")
#             return None
        
#     async def calculate_fair_price(self, chain: pd.DataFrame, symbols: List[str]) -> pd.DataFrame:
#         def _put_call_parity(chain: pd.DataFrame) -> pd.DataFrame:
#             if 'option_type' not in chain.columns:
#                 return pd.DataFrame()
            
#             # Reset index and prepare data
#             chain = chain.reset_index()
#             now = pd.Timestamp.now(tz='UTC')
            
#             # Process expiration date
#             if 'expiration_date' not in chain.columns:
#                 return pd.DataFrame()
                
#             chain['expiration_date'] = pd.to_datetime(chain['expiration_date'])
#             if chain['expiration_date'].dt.tz is None:
#                 chain['expiration_date'] = chain['expiration_date'].dt.tz_localize('UTC')
            
#             # Calculate time to expiry and risk-free rate
#             chain['T'] = (chain['expiration_date'] - now).dt.total_seconds() / (365 * 24 * 60 * 60)
#             chain['r'] = chain.get('risk_free_rate', 0.05)

#             # Calculate weighted prices
#             chain['adjusted_price'] = chain.apply(
#                 lambda row: ((row['bid_price'] * row['ask_size']) + (row['ask_price'] * row['bid_size'])) / 
#                           (row['bid_size'] + row['ask_size']) if row['bid_size'] + row['ask_size'] > 0 else np.nan,
#                 axis=1
#             )

#             # Get calls and puts
#             calls = chain[chain['option_type'] == 'C'][['strike_price', 'adjusted_price', 'T', 'r']].rename(
#                 columns={'adjusted_price': 'call_price'}
#             )
#             puts = chain[chain['option_type'] == 'P'][['strike_price', 'adjusted_price']].rename(
#                 columns={'adjusted_price': 'put_price'}
#             )
            
#             if len(calls) == 0 or len(puts) == 0:
#                 return pd.DataFrame()
            
#             # Calculate fair price
#             result = pd.merge(calls, puts, on='strike_price')
#             result['S'] = result['call_price'] - result['put_price'] + result['strike_price'] * np.exp(-result['r'] * result['T'])
            
#             # Add average and return final result
#             result = result[['strike_price', 'S']]
#             result.loc['Average'] = ['-', result['S'].mean()]
            
#             return result

#         def _calculate_sigma_metrics(symbol: str, fair_price: pd.DataFrame, chain: pd.DataFrame) -> pd.DataFrame:
#             S = fair_price['S'].iloc[-1]
            
#             # Handle NaN values in implied volatility
#             if 'implied_volatility' in chain.columns:
#                 valid_iv = chain['implied_volatility'].dropna()
#                 if len(valid_iv) > 0:
#                     IV = valid_iv.mean()
#                 else:
#                     IV = np.nan
#             else:
#                 IV = np.nan
            
#             # Only calculate sigma if we have valid IV
#             if not np.isnan(IV):
#                 sigma = S * IV * np.sqrt(1 / 252)
#                 sigma_pct = (sigma / S) * 100
#             else:
#                 sigma = np.nan
#                 sigma_pct = np.nan
            
#             return pd.DataFrame({
#                 'metric': [f'{symbol} fair price', 'IV', 'sigma (daily)', '±1sigma (68%)', '±2sigma (95%)', '±3sigma (99.7%)'],
#                 'value': [
#                     round(S, 2),
#                     round(IV, 4) if not np.isnan(IV) else 'NaN',
#                     f"{round(sigma, 2)} ({round(sigma_pct, 2)}%)" if not np.isnan(sigma) else 'NaN',
#                     f"({round(S - sigma, 2)}, {round(S + sigma, 2)})" if not np.isnan(sigma) else 'NaN',
#                     f"({round(S - 2*sigma, 2)}, {round(S + 2*sigma, 2)})" if not np.isnan(sigma) else 'NaN',
#                     f"({round(S - 3*sigma, 2)}, {round(S + 3*sigma, 2)})" if not np.isnan(sigma) else 'NaN'
#                 ]
#             }).set_index('metric')
        
#         results = {}
#         for symbol in symbols:
#             if symbol not in chain or not isinstance(chain[symbol], pd.DataFrame):
#                 print(f"[!] Skipped {symbol}: Invalid data")
#                 continue
                
#             symbol_chain = chain[symbol]
#             fair_price = _put_call_parity(symbol_chain)
            
#             if fair_price.empty:
#                 print(f"[!] Skipped {symbol}: No options data")
#                 continue
                
#             if 'implied_volatility' in symbol_chain.columns:
#                 sigma_metrics = _calculate_sigma_metrics(symbol, fair_price, symbol_chain)
#                 results[symbol] = {
#                     'fair_price': fair_price,
#                     'sigma_metrics': sigma_metrics
#                 }
#                 print(sigma_metrics)
#             else:
#                 results[symbol] = {'fair_price': fair_price}
#                 print(f"[+] {symbol} fair price: {fair_price['S'].iloc[-1]:.2f}")
        
#         return results


class Record:
    def __init__(self):
        pass

    def _fill_gaps_helper(self, df: pd.DataFrame) -> pd.DataFrame:
        # Check for either 'timestamp' or 'index' column
        time_col = 'timestamp' if 'timestamp' in df.columns else 'index' if 'index' in df.columns else None
        if df.empty or not time_col:
            return df
        
        try:
            df = df.dropna(subset=['open', 'high', 'low', 'close'])
            if df.empty:
                return df
            
            df[time_col] = pd.to_datetime(df[time_col])
            df_indexed = df.set_index(time_col).sort_index()
            
            time_diffs = df[time_col].diff().dropna()
            if not time_diffs.empty:
                # Get all time differences in seconds
                diff_seconds = time_diffs.dt.total_seconds()
                # Find the most common interval
                most_common_diff = diff_seconds.mode()
                if not most_common_diff.empty:
                    s = most_common_diff.iloc[0]
                    freq_map = {60: "1min", 300: "5min", 900: "15min", 1800: "30min", 3600: "1h", 86400: "1D"}
                    freq = freq_map.get(s, f"{int(s/60)}min" if s < 3600 else f"{int(s/3600)}h")
                else:
                    freq = "1h"

            
            complete_index = pd.date_range(df_indexed.index.min(), df_indexed.index.max(), freq=freq)
            gaps_count = len(complete_index) - len(df_indexed)
            
            if gaps_count == 0:
                result = df_indexed.reset_index()
                result = result.rename(columns={result.columns[0]: 'timestamp'})
                return self._reorder_columns(result)
            
            print(f"[+] Filling {gaps_count} gaps")
            df_complete = df_indexed.reindex(complete_index)
            df_complete[['open', 'high', 'low', 'close']] = df_complete[['open', 'high', 'low', 'close']].ffill()
            
            for col in ['volume', 'trade_count']:
                if col in df_complete.columns:
                    df_complete[col] = df_complete[col].fillna(0)
            
            if 'vwap' in df_complete.columns:
                df_complete['vwap'] = df_complete['vwap'].ffill()
            
            if 'symbol' in df.columns:
                df_complete['symbol'] = df.iloc[0]['symbol']
            
            result = df_complete.reset_index()
            result = result.rename(columns={result.columns[0]: 'timestamp'})
            return self._reorder_columns(result)
            
        except Exception as e:
            print(f"[!] Error filling gaps: {e}")
            return df

    def _reorder_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        desired_order = ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume', 'trade_count', 'vwap']
        available_cols = [col for col in desired_order if col in df.columns]
        other_cols = [col for col in df.columns if col not in desired_order]
        return df[available_cols + other_cols]

    def _fill_gaps_file(self, filename: str) -> None:
        try:
            df = pd.read_csv(filename)
            filled_df = self._fill_gaps_helper(df)
            if len(filled_df) > len(df):
                filled_df.to_csv(filename, index=False)
        except Exception as e:
            print(f"[!] Error filling gaps: {e}")

    def load(self, config: Dict[str, Any]) -> None:
        self.folder = config["folder"]["name"]
        os.makedirs(self.folder, exist_ok=True)
        self.regular_columns = config["market"]["regular"]["columns"]
        self.option_columns = config["market"]["option"]["columns"]
    
    async def write(self, market: str, data: Dict[str, pd.DataFrame]) -> None:
        """Write data concurrently with one thread per file"""
        if not data:
            print("[!] No data to write")
            return

        def _write_file(symbol: str, df: pd.DataFrame) -> None:
            market_folder = f"{self.folder}/{market}"
            os.makedirs(market_folder, exist_ok=True)
            filename = f"{market_folder}/{symbol.replace('/', '_')}.csv" 
            
            print(f"[>] Writing path: {filename}")
            df.to_csv(filename)
            
            # Apply gap filling to the written CSV file
            self._fill_gaps_file(filename)

        try:
            write_tasks = []
            for symbol, df in data.items():
                task = asyncio.to_thread(_write_file, symbol, df)
                write_tasks.append(task)
            
            if write_tasks:
                await asyncio.gather(*write_tasks, return_exceptions=True)
        except Exception as e:
            print(f"[!] Error writing data: {e}")

    async def read(self, market: str, symbols: Union[str, List[str]]) -> Dict[str, pd.DataFrame]:
        """Read data concurrently"""
        if not symbols:
            return {}
            
        if isinstance(symbols, str):
            symbols = [symbols]
        elif isinstance(symbols, list) and len(symbols) == 0:
            print(f"[!] Empty symbols list for {market}")
            return {}

        def _read_file(symbol: str) -> Optional[pd.DataFrame]:
            """Read single file synchronously"""
            # Convert symbol name for filename (same as write method)
            clean_symbol = symbol.replace('/', '_')
            filename = f"{self.folder}/{market}/{clean_symbol}.csv"
            if not os.path.exists(filename):
                print(f"[!] File not found: {filename}")
                return None

            print(f"[<] Reading path: {filename}")
            try:
                df = pd.read_csv(filename, index_col=[0])
                
                if market == "option":
                    available_cols = [col for col in self.option_columns if col in df.columns]
                    if available_cols:
                        df = df[available_cols]
                    else:
                        print(f"[!] No matching option columns found. Available: {list(df.columns)}")
                        return None
                else:
                    available_cols = [col for col in self.regular_columns if col in df.columns]
                    if available_cols:
                        df = df[available_cols]
                    else:
                        print(f"[!] No matching regular columns found. Available: {list(df.columns)}")
                        return None
                
                return df
            except Exception as e:
                print(f"[!] Error reading file {filename}: {e}")
                return None

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

    async def append(self, market: str, data: Dict[str, pd.DataFrame]) -> None:
        """Append data concurrently with one thread per file"""
        if not data:
            print("[!] No data to append")
            return

        def _append_file(symbol: str, df: pd.DataFrame) -> None:
            """Append single file synchronously"""
            # Create market-specific folder
            market_folder = f"{self.folder}/{market}"
            os.makedirs(market_folder, exist_ok=True)
            
            filename = f"{market_folder}/{symbol.replace('/', '_')}.csv"
            
            # Determine mode and header
            file_exists = os.path.exists(filename)
            mode = 'a' if file_exists else 'w'
            header = not file_exists
            
            print(f"[>] Appending path: {filename}")
            df.to_csv(filename, mode=mode, header=header, index=False)

        try:
            append_tasks = []
            for symbol, df in data.items():
                if not df.empty:
                    task = asyncio.to_thread(_append_file, symbol, df)
                    append_tasks.append(task)
            
            if append_tasks:
                await asyncio.gather(*append_tasks, return_exceptions=True)
        except Exception as e:
            print(f"[!] Error appending data: {e}")