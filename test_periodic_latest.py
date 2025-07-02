import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from head import *
from module.account import Account, MarketType

async def test_periodic_latest():
    """Test periodic latest data retrieval"""
    
    # Load configuration
    config_path = os.path.join("app", "config.json")
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    # Create account
    account = Account()
    account.load(config['account'])
    
    # Add some stock symbols for testing
    account.investment["stock"] = ["AAPL", "MSFT"]  # Override with test symbols
    
    print("=== Testing Periodic Latest Data Retrieval ===")
    
    # Start periodic latest data retrieval (every 5 minutes as per config)
    await account.start_retrieve(MarketType.STOCK)
    
    print("\nWaiting for data retrieval (every 5 minutes)...")
    print("Press Ctrl+C to stop\n")
    
    try:
        for i in range(12):
            await asyncio.sleep(30)
            
            latest_data = account.get_latest()
            if latest_data:
                print(f"\n--- Update {i+1} at {datetime.now().strftime('%H:%M:%S')} ---")
                for symbol, df in latest_data.items():
                    if not df.empty:
                        latest_bar = df.iloc[-1]
                        print(f"{symbol}: Close=${latest_bar.get('close', 'N/A'):.2f}")
                    else:
                        print(f"{symbol}: No data")
            else:
                print(f"No data yet... (check {i+1})")
    
    except KeyboardInterrupt:
        print("\nStopping...")
    
    finally:
        await account.stop_retrieve()
        print("Stopped.")

if __name__ == "__main__":
    asyncio.run(test_periodic_latest()) 