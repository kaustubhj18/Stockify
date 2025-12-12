from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import json
import os
from datetime import datetime, timedelta
import yfinance as yf
from functools import wraps
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error
import pandas as pd
from models.historical_predictor import HistoricalPredictor
from models.sentiment_analyzer import SentimentAnalyzer
from models.hybrid_predictor import HybridPredictor
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import requests

app = Flask(__name__)
app.secret_key = 'stockify_secret_key_2024'  # Change this in production

# File to store user credentials
USERS_FILE = 'users.json'

def format_dividend_yield(dividend_yield):
    """Format dividend yield for display"""
    if dividend_yield is None or dividend_yield == 0:
        return "No dividend"
    elif isinstance(dividend_yield, (int, float)):
        return f"{dividend_yield * 100:.2f}%" if dividend_yield < 1 else f"{dividend_yield:.2f}%"
    else:
        return str(dividend_yield)

# Currency conversion cache
USD_TO_INR_RATE = None  # Will be fetched from live sources
LAST_RATE_UPDATE = None

def fetch_live_exchange_rate():
    """Fetch live USD to INR exchange rate from multiple sources - PRIORITIZING ACCURACY"""
    
    # Method 1: Try Google Finance (most accurate and up-to-date)
    try:
        import requests
        from bs4 import BeautifulSoup
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get("https://www.google.com/finance/quote/USD-INR", headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            # Look for the exchange rate in various possible selectors
            rate_element = soup.find('div', {'data-last-price': True}) or \
                          soup.find('div', class_='YMlKec fxKbKc') or \
                          soup.find('span', class_='YMlKec fxKbKc')
            if rate_element:
                rate_text = rate_element.get('data-last-price') or rate_element.get_text()
                rate = float(rate_text.replace(',', ''))
                if rate > 70 and rate < 100:
                    print(f"Exchange rate from Google Finance: Rs {rate:.2f}/USD")
                    return rate
    except Exception as e:
        print(f"Google Finance fetch failed: {str(e)}")
    
    # Method 2: Try Yahoo Finance (backup)
    try:
        usd_inr = yf.Ticker("USDINR=X")
        hist = usd_inr.history(period="1d")
        if not hist.empty:
            rate = hist['Close'].iloc[-1]
            if rate > 70 and rate < 100:  # Sanity check
                print(f"Exchange rate from Yahoo Finance: Rs {rate:.2f}/USD")
                return rate
    except Exception as e:
        print(f"Yahoo Finance fetch failed: {str(e)}")
    
    # Method 3: Try XE.com API (very accurate)
    try:
        response = requests.get("https://api.xe.com/v1/convert_from.json/?from=USD&to=INR&amount=1", timeout=8)
        if response.status_code == 200:
            data = response.json()
            rate = float(data['rates']['INR'])
            if rate > 70 and rate < 100:
                print(f"Exchange rate from XE.com: Rs {rate:.2f}/USD")
                return rate
    except Exception as e:
        print(f"XE.com fetch failed: {str(e)}")
    
    # Method 4: Try using INR=X alternative ticker
    try:
        inr = yf.Ticker("INR=X")
        hist = inr.history(period="1d")
        if not hist.empty:
            rate = 1 / hist['Close'].iloc[-1]  # Inverse if needed
            if rate > 70 and rate < 100:
                print(f"Exchange rate from INR=X: Rs {rate:.2f}/USD")
                return rate
    except Exception as e:
        print(f"INR=X fetch failed: {str(e)}")
    
    # Method 5: Try exchangerate-api.com (free tier)
    try:
        response = requests.get("https://api.exchangerate-api.com/v4/latest/USD", timeout=5)
        if response.status_code == 200:
            data = response.json()
            rate = data['rates'].get('INR')
            if rate and rate > 70 and rate < 100:
                print(f"Exchange rate from ExchangeRate-API: Rs {rate:.2f}/USD")
                return rate
    except Exception as e:
        print(f"ExchangeRate-API fetch failed: {str(e)}")
    
    # Method 6: Try frankfurter.app (European Central Bank data)
    try:
        response = requests.get("https://api.frankfurter.app/latest?from=USD&to=INR", timeout=5)
        if response.status_code == 200:
            data = response.json()
            rate = data['rates'].get('INR')
            if rate and rate > 70 and rate < 100:
                print(f"Exchange rate from Frankfurter API: Rs {rate:.2f}/USD")
                return rate
    except Exception as e:
        print(f"Frankfurter API fetch failed: {str(e)}")
    
    # If all methods fail, raise an error
    print("ERROR: Could not fetch exchange rate from any source!")
    print("Using emergency fallback rate of Rs 83.00")
    return 83.0  # Emergency fallback only

def get_most_accurate_exchange_rate():
    """Get the most accurate exchange rate by trying multiple sources and averaging"""
    rates = []
    
    # Try Google Finance first (most accurate)
    try:
        import requests
        from bs4 import BeautifulSoup
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get("https://www.google.com/finance/quote/USD-INR", headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            rate_element = soup.find('div', {'data-last-price': True}) or \
                          soup.find('div', class_='YMlKec fxKbKc') or \
                          soup.find('span', class_='YMlKec fxKbKc')
            if rate_element:
                rate_text = rate_element.get('data-last-price') or rate_element.get_text()
                rate = float(rate_text.replace(',', ''))
                if 70 < rate < 100:
                    rates.append(rate)
                    print(f"Google Finance rate: Rs {rate:.2f}/USD")
    except Exception as e:
        print(f"Google Finance error: {str(e)}")
    
    # Try Yahoo Finance
    try:
        usd_inr = yf.Ticker("USDINR=X")
        hist = usd_inr.history(period="1d")
        if not hist.empty:
            rate = hist['Close'].iloc[-1]
            if 70 < rate < 100:
                rates.append(rate)
                print(f"Yahoo Finance rate: Rs {rate:.2f}/USD")
    except Exception as e:
        print(f"Yahoo Finance error: {str(e)}")
    
    # If we have multiple rates, return the average for highest accuracy
    if len(rates) >= 2:
        avg_rate = sum(rates) / len(rates)
        print(f"Average rate from {len(rates)} sources: Rs {avg_rate:.2f}/USD")
        return avg_rate
    elif len(rates) == 1:
        print(f"Single source rate: Rs {rates[0]:.2f}/USD")
        return rates[0]
    else:
        # Fallback to the original method
        return fetch_live_exchange_rate()

def get_usd_to_inr_rate():
    """Get current USD to INR exchange rate with caching"""
    global USD_TO_INR_RATE, LAST_RATE_UPDATE
    
    # Update rate every 2 hours (7200 seconds) - OPTIMIZED for speed
    current_time = datetime.now()
    should_update = (
        USD_TO_INR_RATE is None or 
        LAST_RATE_UPDATE is None or 
        (current_time - LAST_RATE_UPDATE).total_seconds() > 7200  # 2 hours instead of 1 hour
    )
    
    if should_update:
        try:
            USD_TO_INR_RATE = get_most_accurate_exchange_rate()  # Use the more accurate method
            LAST_RATE_UPDATE = current_time
            print(f"Current Exchange Rate: Rs {USD_TO_INR_RATE:.2f}/USD (Updated at {current_time.strftime('%I:%M %p')})")
        except Exception as e:
            print(f"Error updating exchange rate: {str(e)}")
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

# Initialize users file if it doesn't exist
if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, 'w') as f:
        json.dump([], f)

# Fetch exchange rate on startup
print("\n" + "="*60)
print("Stockify - Starting Application")
print("="*60)
print("Fetching live USD to INR exchange rate...")
try:
    initial_rate = get_usd_to_inr_rate()
    print(f"Successfully loaded exchange rate: Rs {initial_rate:.2f}/USD")
    print("="*60 + "\n")
except Exception as e:
    print(f"Warning: Could not fetch exchange rate: {str(e)}")
    print("="*60 + "\n")

def load_users():
    """Load users from JSON file"""
    with open(USERS_FILE, 'r') as f:
        return json.load(f)

def save_users(users):
    """Save users to JSON file"""
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def login_required(f):
    """Decorator to require login for routes"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_email' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Landing page - redirects to login or home"""
    if 'user_email' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/api/exchange-rate')
def get_exchange_rate():
    """Get current USD to INR exchange rate"""
    try:
        rate = get_usd_to_inr_rate()
        return jsonify({
            'success': True,
            'rate': round(rate, 2),
            'currency_pair': 'USD/INR',
            'last_updated': LAST_RATE_UPDATE.strftime('%Y-%m-%d %I:%M %p') if LAST_RATE_UPDATE else 'Just now',
            'message': f'₹{rate:.2f} per USD'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    """User signup page"""
    if request.method == 'POST':
        data = request.json
        email = data.get('email')
        password = data.get('password')
        name = data.get('name')
        
        if not email or not password or not name:
            return jsonify({'success': False, 'message': 'All fields are required'})
        
        users = load_users()
        
        # Check if user already exists
        if any(user['email'] == email for user in users):
            return jsonify({'success': False, 'message': 'User already exists. Please login.'})
        
        # Add new user
        users.append({
            'email': email,
            'password': password,  # In production, hash this!
            'name': name,
            'created_at': datetime.now().isoformat(),
            'watchlist': [],
            'portfolio': []
        })
        
        save_users(users)
        
        # Auto login after signup
        session['user_email'] = email
        session['user_name'] = name
        
        return jsonify({'success': True, 'message': 'Signup successful'})
    
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login page"""
    if request.method == 'POST':
        data = request.json
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password are required'})
        
        users = load_users()
        
        # Find user
        user = next((u for u in users if u['email'] == email), None)
        
        if not user:
            return jsonify({'success': False, 'message': 'User not found. Please signup first.'})
        
        if user['password'] != password:
            return jsonify({'success': False, 'message': 'Invalid password'})
        
        # Set session
        session['user_email'] = email
        session['user_name'] = user['name']
        
        return jsonify({'success': True, 'message': 'Login successful'})
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logout user"""
    session.clear()
    return redirect(url_for('login'))

@app.route('/home')
@login_required
def home():
    """Home page with service description"""
    return render_template('home.html', user_name=session.get('user_name'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard with market status"""
    return render_template('dashboard.html', user_name=session.get('user_name'))

@app.route('/search')
@login_required
def search_page():
    """Search stocks page"""
    return render_template('search.html', user_name=session.get('user_name'))

@app.route('/stock/<symbol>')
@login_required
def stock_details(symbol):
    """Stock details page"""
    return render_template('stock.html', symbol=symbol, user_name=session.get('user_name'))

@app.route('/api/market-status')
@login_required
def market_status():
    """Get Indian and International market status - OPTIMIZED"""
    try:
        def get_index_data(symbol):
            """Fetch index data with timeout and optimization"""
            try:
                ticker = yf.Ticker(symbol)
                # Only fetch 2 days of history, much faster than .info
                hist = ticker.history(period="2d")
                if len(hist) >= 2:
                    current = hist['Close'].iloc[-1]
                    previous = hist['Close'].iloc[-2]
                    change = current - previous
                    change_percent = (change / previous) * 100
                    return {
                        'price': round(current, 2),
                        'change': round(change, 2),
                        'change_percent': round(change_percent, 2)
                    }
                elif len(hist) == 1:
                    current = hist['Close'].iloc[-1]
                    return {
                        'price': round(current, 2),
                        'change': 0,
                        'change_percent': 0
                    }
            except:
                pass
            return {'price': 0, 'change': 0, 'change_percent': 0}
        
        # Parallel fetching for speed - all indices fetched simultaneously
        indices = {
            'nifty': '^NSEI',
            'sensex': '^BSESN',
            'sp500': '^GSPC',
            'nasdaq': '^IXIC',
            'dow': '^DJI'
        }
        
        results = {}
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_index = {executor.submit(get_index_data, symbol): name 
                             for name, symbol in indices.items()}
            
            for future in as_completed(future_to_index):
                index_name = future_to_index[future]
                try:
                    results[index_name] = future.result(timeout=3)  # 3 second timeout per index
                except:
                    results[index_name] = {'price': 0, 'change': 0, 'change_percent': 0}
        
        return jsonify({
            'success': True,
            'indian_market': {
                'nifty': results.get('nifty', {'price': 0, 'change': 0, 'change_percent': 0}),
                'sensex': results.get('sensex', {'price': 0, 'change': 0, 'change_percent': 0})
            },
            'international_market': {
                'sp500': results.get('sp500', {'price': 0, 'change': 0, 'change_percent': 0}),
                'nasdaq': results.get('nasdaq', {'price': 0, 'change': 0, 'change_percent': 0}),
                'dow': results.get('dow', {'price': 0, 'change': 0, 'change_percent': 0})
            }
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/stock/<symbol>')
@login_required
def get_stock_data(symbol):
    """Get detailed stock information - OPTIMIZED"""
    try:
        stock = yf.Ticker(symbol)
        
        # Fetch data in parallel
        def fetch_info():
            try:
                return stock.info
            except:
                return {}
        
        def fetch_history():
            try:
                return stock.history(period="6mo")  # Reduced from 1y to 6mo for faster loading
            except:
                return pd.DataFrame()
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            info_future = executor.submit(fetch_info)
            hist_future = executor.submit(fetch_history)
            
            info = info_future.result(timeout=5)
            hist = hist_future.result(timeout=5)
        
        if hist.empty:
            return jsonify({'success': False, 'message': 'Stock not found or no data available'})
        
        # Calculate additional metrics
        current_price = hist['Close'].iloc[-1]
        prev_close = hist['Close'].iloc[-2] if len(hist) >= 2 else current_price
        change = current_price - prev_close
        change_percent = (change / prev_close) * 100
        
        # Get 52-week high and low
        week_52_high = hist['High'].max()
        week_52_low = hist['Low'].min()
        
        # Calculate average volume
        avg_volume = hist['Volume'].mean()
        
        # Convert prices to INR if foreign stock
        current_price_inr = convert_price_to_inr(current_price, symbol)
        change_inr = convert_price_to_inr(change, symbol)
        week_52_high_inr = convert_price_to_inr(week_52_high, symbol)
        week_52_low_inr = convert_price_to_inr(week_52_low, symbol)
        
        # Market cap conversion
        market_cap = info.get('marketCap', 'N/A')
        if market_cap != 'N/A' and not is_indian_stock(symbol):
            market_cap = market_cap * get_usd_to_inr_rate()
        
        stock_data = {
            'success': True,
            'symbol': symbol,
            'name': info.get('longName', symbol),
            'current_price': round(current_price_inr, 2),
            'change': round(change_inr, 2),
            'change_percent': round(change_percent, 2),
            'market_cap': market_cap,
            'pe_ratio': info.get('trailingPE', 'N/A'),
            'forward_pe': info.get('forwardPE', 'N/A'),
            'dividend_yield': format_dividend_yield(info.get('dividendYield')),
            'beta': info.get('beta', 'N/A'),
            'week_52_high': round(week_52_high_inr, 2),
            'week_52_low': round(week_52_low_inr, 2),
            'avg_volume': int(avg_volume),
            'volume': int(hist['Volume'].iloc[-1]),
            'sector': info.get('sector', 'N/A'),
            'industry': info.get('industry', 'N/A'),
            'description': info.get('longBusinessSummary', 'No description available'),
            'website': info.get('website', ''),
            'employees': info.get('fullTimeEmployees', 'N/A'),
            'is_indian': is_indian_stock(symbol),
            'currency': 'INR'
        }
        
        return jsonify(stock_data)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/stock/<symbol>/history')
@login_required
def get_stock_history(symbol):
    """Get historical stock data for charts - OPTIMIZED"""
    try:
        period = request.args.get('period', '6mo')  # Default to 6 months for faster loading
        stock = yf.Ticker(symbol)
        
        # Fetch with timeout
        import signal
        
        def timeout_handler(signum, frame):
            raise TimeoutError("Stock history fetch timeout")
        
        # Set 10-second timeout (Windows compatible way)
        start_time = time.time()
        hist = stock.history(period=period)
        
        if time.time() - start_time > 10:
            return jsonify({'success': False, 'message': 'Request timeout - please try again'})
        
        if hist.empty:
            return jsonify({'success': False, 'message': 'No historical data available'})
        
        # Prepare data for charts
        dates = hist.index.strftime('%Y-%m-%d').tolist()
        
        # Convert prices to INR if foreign stock
        if is_indian_stock(symbol):
            prices = hist['Close'].round(2).tolist()
        else:
            rate = get_usd_to_inr_rate()
            prices = (hist['Close'] * rate).round(2).tolist()
        
        volumes = hist['Volume'].tolist()
        
        return jsonify({
            'success': True,
            'dates': dates,
            'prices': prices,
            'volumes': volumes,
            'currency': 'INR'
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/predict/<symbol>')
@login_required
def predict_page(symbol):
    """Prediction page for stock"""
    return render_template('predict.html', symbol=symbol, user_name=session.get('user_name'))

@app.route('/api/predict/<symbol>/historical')
@login_required
def predict_historical(symbol):
    """Get historical prediction for stock"""
    try:
        model_type = request.args.get('model_type', 'standard')  # standard or advanced
        predictor = HistoricalPredictor(symbol)
        result = predictor.predict(days=14, model_type=model_type)
        
        if result:
            return jsonify(result)
        else:
            return jsonify({'success': False, 'message': 'Unable to generate predictions'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/predict/<symbol>/sentiment')
@login_required
def predict_sentiment(symbol):
    """Get sentiment analysis prediction for stock"""
    try:
        analyzer = SentimentAnalyzer(symbol)
        result = analyzer.analyze()
        
        response = jsonify(result)
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/api/predict/<symbol>/hybrid')
@login_required
def predict_hybrid(symbol):
    """Get hybrid prediction combining historical and sentiment analysis"""
    try:
        predictor = HybridPredictor(symbol)
        result = predictor.predict(days=14)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

@app.route('/watchlist')
@login_required
def watchlist_page():
    """Watchlist page"""
    return render_template('watchlist.html', user_name=session.get('user_name'))

@app.route('/api/watchlist', methods=['GET', 'POST', 'DELETE'])
@login_required
def manage_watchlist():
    """Manage user watchlist"""
    users = load_users()
    user = next((u for u in users if u['email'] == session['user_email']), None)
    
    if not user:
        return jsonify({'success': False, 'message': 'User not found'})
    
    if request.method == 'GET':
        # Get watchlist with current prices - OPTIMIZED with parallel fetching
        watchlist = user.get('watchlist', [])
        
        def fetch_stock_data(symbol):
            """Fetch stock data with timeout"""
            try:
                stock = yf.Ticker(symbol)
                hist = stock.history(period="2d")
                if not hist.empty:
                    current_price = hist['Close'].iloc[-1]
                    prev_close = hist['Close'].iloc[-2] if len(hist) >= 2 else current_price
                    change = current_price - prev_close
                    change_percent = (change / prev_close) * 100
                    
                    # Convert to INR if foreign stock
                    current_price_inr = convert_price_to_inr(current_price, symbol)
                    change_inr = convert_price_to_inr(change, symbol)
                    
                    # Get name without calling .info (much faster)
                    name = symbol
                    try:
                        info = stock.info
                        name = info.get('longName', symbol)
                    except:
                        pass
                    
                    return {
                        'symbol': symbol,
                        'name': name,
                        'price': round(current_price_inr, 2),
                        'change': round(change_inr, 2),
                        'change_percent': round(change_percent, 2)
                    }
            except:
                pass
            return None
        
        # Parallel fetch all watchlist stocks (max 10 at a time)
        watchlist_data = []
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_symbol = {executor.submit(fetch_stock_data, symbol): symbol 
                              for symbol in watchlist}
            
            for future in as_completed(future_to_symbol):
                try:
                    result = future.result(timeout=3)
                    if result:
                        watchlist_data.append(result)
                except:
                    continue
        
        return jsonify({'success': True, 'watchlist': watchlist_data})
    
    elif request.method == 'POST':
        # Add to watchlist
        data = request.json
        symbol = data.get('symbol', '').upper()
        
        if not symbol:
            return jsonify({'success': False, 'message': 'Symbol is required'})
        
        if 'watchlist' not in user:
            user['watchlist'] = []
        
        if symbol in user['watchlist']:
            return jsonify({'success': False, 'message': 'Stock already in watchlist'})
        
        user['watchlist'].append(symbol)
        save_users(users)
        
        return jsonify({'success': True, 'message': 'Added to watchlist'})
    
    elif request.method == 'DELETE':
        # Remove from watchlist
        data = request.json
        symbol = data.get('symbol', '').upper()
        
        if symbol in user.get('watchlist', []):
            user['watchlist'].remove(symbol)
            save_users(users)
            return jsonify({'success': True, 'message': 'Removed from watchlist'})
        
        return jsonify({'success': False, 'message': 'Stock not in watchlist'})

@app.route('/portfolio')
@login_required
def portfolio_page():
    """Portfolio page"""
    return render_template('portfolio.html', user_name=session.get('user_name'))

@app.route('/api/portfolio', methods=['GET', 'POST', 'DELETE'])
@login_required
def manage_portfolio():
    """Manage user portfolio"""
    users = load_users()
    user = next((u for u in users if u['email'] == session['user_email']), None)
    
    if not user:
        return jsonify({'success': False, 'message': 'User not found'})
    
    if request.method == 'GET':
        # Get portfolio with current values - OPTIMIZED with parallel fetching
        portfolio = user.get('portfolio', [])
        
        def fetch_portfolio_item(holding):
            """Fetch portfolio item data with timeout"""
            try:
                symbol = holding['symbol']
                stock = yf.Ticker(symbol)
                hist = stock.history(period="1d")
                if not hist.empty:
                    current_price = hist['Close'].iloc[-1]
                    quantity = holding['quantity']
                    buy_price = holding['buy_price']
                    
                    # Convert current price to INR if foreign stock
                    current_price_inr = convert_price_to_inr(current_price, symbol)
                    
                    # Note: buy_price is already stored in the currency user entered
                    # For consistency, we assume buy_price was entered in INR
                    current_value = current_price_inr * quantity
                    invested_value = buy_price * quantity
                    profit_loss = current_value - invested_value
                    profit_loss_percent = (profit_loss / invested_value) * 100
                    
                    # Get name without calling .info (faster)
                    name = symbol
                    try:
                        info = stock.info
                        name = info.get('longName', symbol)
                    except:
                        pass
                    
                    return {
                        'symbol': symbol,
                        'name': name,
                        'quantity': quantity,
                        'buy_price': round(buy_price, 2),
                        'current_price': round(current_price_inr, 2),
                        'invested_value': round(invested_value, 2),
                        'current_value': round(current_value, 2),
                        'profit_loss': round(profit_loss, 2),
                        'profit_loss_percent': round(profit_loss_percent, 2)
                    }
            except:
                pass
            return None
        
        # Parallel fetch all portfolio items (max 10 at a time)
        portfolio_data = []
        total_value = 0
        total_invested = 0
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_holding = {executor.submit(fetch_portfolio_item, holding): holding 
                               for holding in portfolio}
            
            for future in as_completed(future_to_holding):
                try:
                    result = future.result(timeout=3)
                    if result:
                        portfolio_data.append(result)
                        total_value += result['current_value']
                        total_invested += result['invested_value']
                except:
                    continue
        
        total_profit_loss = total_value - total_invested
        total_profit_loss_percent = (total_profit_loss / total_invested * 100) if total_invested > 0 else 0
        
        return jsonify({
            'success': True,
            'portfolio': portfolio_data,
            'summary': {
                'total_invested': round(total_invested, 2),
                'total_value': round(total_value, 2),
                'total_profit_loss': round(total_profit_loss, 2),
                'total_profit_loss_percent': round(total_profit_loss_percent, 2)
            }
        })
    
    elif request.method == 'POST':
        # Add to portfolio
        data = request.json
        symbol = data.get('symbol', '').upper()
        quantity = data.get('quantity', 0)
        buy_price = data.get('buy_price', 0)
        
        if not symbol or quantity <= 0 or buy_price <= 0:
            return jsonify({'success': False, 'message': 'Invalid data'})
        
        if 'portfolio' not in user:
            user['portfolio'] = []
        
        user['portfolio'].append({
            'symbol': symbol,
            'quantity': quantity,
            'buy_price': buy_price,
            'date': datetime.now().isoformat()
        })
        
        save_users(users)
        
        return jsonify({'success': True, 'message': 'Added to portfolio'})
    
    elif request.method == 'DELETE':
        # Remove from portfolio
        data = request.json
        symbol = data.get('symbol', '').upper()
        
        if 'portfolio' in user:
            user['portfolio'] = [h for h in user['portfolio'] if h['symbol'] != symbol]
            save_users(users)
            return jsonify({'success': True, 'message': 'Removed from portfolio'})
        
        return jsonify({'success': False, 'message': 'Stock not in portfolio'})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
