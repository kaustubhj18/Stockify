"""
Currency conversion utilities for stock prices
Fetches real-time exchange rates from multiple sources
"""
import yfinance as yf
from datetime import datetime
import requests

# Currency conversion cache
USD_TO_INR_RATE = None  # Will be fetched from live sources
LAST_RATE_UPDATE = None

def fetch_live_exchange_rate():
    """Fetch live USD to INR exchange rate from multiple sources"""
    
    # Method 1: Try Yahoo Finance (most reliable)
    try:
        usd_inr = yf.Ticker("USDINR=X")
        hist = usd_inr.history(period="1d")
        if not hist.empty:
            rate = hist['Close'].iloc[-1]
            if rate > 70 and rate < 100:  # Sanity check
                return rate
    except:
        pass
    
    # Method 2: Try using INR=X alternative ticker
    try:
        inr = yf.Ticker("INR=X")
        hist = inr.history(period="1d")
        if not hist.empty:
            rate = 1 / hist['Close'].iloc[-1]
            if rate > 70 and rate < 100:
                return rate
    except:
        pass
    
    # Method 3: Try exchangerate-api.com (free tier)
    try:
        response = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
        if response.status_code == 200:
            data = response.json()
            rate = data['rates'].get('INR')
            if rate and rate > 70 and rate < 100:
                return rate
    except:
        pass
    
    # Method 4: Try frankfurter.app (European Central Bank data)
    try:
        response = requests.get("https://api.frankfurter.app/latest?from=USD&to=INR", timeout=5)
        if response.status_code == 200:
            data = response.json()
            rate = data['rates'].get('INR')
            if rate and rate > 70 and rate < 100:
                return rate
    except:
        pass
    
    # Emergency fallback only
    return 83.0

def get_usd_to_inr_rate():
    """Get current USD to INR exchange rate with caching"""
    global USD_TO_INR_RATE, LAST_RATE_UPDATE
    
    # Update rate every 1 hour (3600 seconds)
    current_time = datetime.now()
    should_update = (
        USD_TO_INR_RATE is None or 
        LAST_RATE_UPDATE is None or 
        (current_time - LAST_RATE_UPDATE).total_seconds() > 3600
    )
    
    if should_update:
        try:
            USD_TO_INR_RATE = fetch_live_exchange_rate()
            LAST_RATE_UPDATE = current_time
        except:
            if USD_TO_INR_RATE is None:
                USD_TO_INR_RATE = 83.0  # Only use fallback if never fetched
    
    return USD_TO_INR_RATE

def is_indian_stock(symbol):
    """Check if stock is Indian (NSE/BSE) or foreign (mainly US)"""
    indian_suffixes = ['.NS', '.BO', '.BSE', '.NSE']
    return any(symbol.upper().endswith(suffix) for suffix in indian_suffixes)

def convert_price_to_inr(price, symbol):
    """Convert price to INR if it's a foreign stock"""
    if is_indian_stock(symbol):
        # Already in INR
        return price
    else:
        # Foreign stock (USD), convert to INR
        rate = get_usd_to_inr_rate()
        return price * rate

def convert_prices_array_to_inr(prices, symbol):
    """Convert an array of prices to INR if foreign stock"""
    if is_indian_stock(symbol):
        return prices
    else:
        rate = get_usd_to_inr_rate()
        return [price * rate for price in prices]

