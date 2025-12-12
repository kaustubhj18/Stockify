import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import yfinance as yf
from datetime import datetime, timedelta
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, Bidirectional, Attention, Layer
from tensorflow.keras.callbacks import EarlyStopping
import tensorflow as tf
from models.currency_utils import convert_price_to_inr, convert_prices_array_to_inr

class HistoricalPredictor:
    """
    Historical stock price prediction using LSTM
    with multiple technical features.
    Supports both standard LSTM and advanced Bidirectional LSTM models.
    """

    def __init__(self, symbol):
        self.symbol = symbol
        self.scaler = MinMaxScaler()

    def prepare_features(self, df):
        """Prepare multiple features from historical data"""
        df['MA_7'] = df['Close'].rolling(window=7).mean()
        df['MA_21'] = df['Close'].rolling(window=21).mean()
        df['MA_50'] = df['Close'].rolling(window=50).mean()

        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        # Avoid division by zero in RSI calculation
        rs = gain / loss.replace(0, 0.001)  # Replace 0 with small value to avoid division by zero
        df['RSI'] = 100 - (100 / (1 + rs))

        # MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()

        # Bollinger Bands
        df['BB_Middle'] = df['Close'].rolling(window=20).mean()
        bb_std = df['Close'].rolling(window=20).std()
        df['BB_Upper'] = df['BB_Middle'] + (bb_std * 2)
        df['BB_Lower'] = df['BB_Middle'] - (bb_std * 2)

        # Volume & volatility
        df['Volume_MA'] = df['Volume'].rolling(window=20).mean()
        # Avoid division by zero in volume ratio calculation
        df['Volume_Ratio'] = df['Volume'] / df['Volume_MA'].replace(0, 1)  # Replace 0 with 1 to avoid division by zero
        df['Momentum'] = df['Close'] - df['Close'].shift(10)
        df['Volatility'] = df['Close'].rolling(window=10).std()

        df = df.dropna()
        return df

    def create_sequences(self, data, sequence_length=60):
        """Create input sequences and labels for LSTM"""
        X, y = [], []
        for i in range(sequence_length, len(data)):
            X.append(data[i-sequence_length:i])
            y.append(data[i, 0])  # Predict Close
        return np.array(X), np.array(y)

    def build_lstm_model(self, input_shape):
        """Define the standard LSTM model"""
        model = Sequential([
            LSTM(32, return_sequences=False, input_shape=input_shape),  # Reduced from 64 to 32 for speed
            Dropout(0.1),  # Reduced from 0.2 to 0.1
            Dense(16, activation='relu'),  # Reduced from 32 to 16
            Dense(1)
        ])
        model.compile(optimizer='adam', loss='mse', metrics=['mae'])
        return model
    
    def build_advanced_lstm_model(self, input_shape):
        """Define the advanced Bidirectional LSTM model with multiple layers"""
        model = Sequential([
            Bidirectional(LSTM(128, return_sequences=True, input_shape=input_shape)),
            Dropout(0.3),
            Bidirectional(LSTM(64, return_sequences=True)),
            Dropout(0.3),
            LSTM(32, return_sequences=False),
            Dropout(0.2),
            Dense(64, activation='relu'),
            Dropout(0.2),
            Dense(32, activation='relu'),
            Dense(1)
        ])
        model.compile(optimizer='adam', loss='mse', metrics=['mae'])
        return model

    def predict(self, days=14, model_type='standard'):
        """
        Train LSTM and predict future stock prices
        
        Args:
            days (int): Number of days to predict
            model_type (str): 'standard' for basic LSTM or 'advanced' for Bidirectional LSTM
        """
        try:
            stock = yf.Ticker(self.symbol)
            df = stock.history(period="2y")

            if df.empty:
                print("No data found for symbol:", self.symbol)
                return None

            df = self.prepare_features(df)

            feature_columns = [
                'Close', 'Volume', 'MA_7', 'MA_21', 'MA_50',
                'RSI', 'MACD', 'Signal_Line', 'Volume_Ratio',
                'Momentum', 'Volatility'
            ]
            feature_columns = [col for col in feature_columns if col in df.columns]
            data = df[feature_columns].values

            # Scale features
            scaled_data = self.scaler.fit_transform(data)
            sequence_length = 30  # Reduced from 60 to 30 for faster processing
            X, y = self.create_sequences(scaled_data, sequence_length)

            if len(X) == 0:
                print("Not enough data for training.")
                return None

            # Train-test split
            split = int(0.8 * len(X))
            X_train, X_test = X[:split], X[split:]
            y_train, y_test = y[:split], y[split:]

            # Build and train model based on model_type - ULTRA FAST MODE
            if model_type == 'advanced':
                model = self.build_advanced_lstm_model((sequence_length, len(feature_columns)))
                epochs = 10  # Ultra fast training
                batch_size = 64  # Larger batch for speed
                print(f"Training Advanced Bidirectional LSTM model...")
            else:
                model = self.build_lstm_model((sequence_length, len(feature_columns)))
                epochs = 8  # Ultra fast training
                batch_size = 64  # Larger batch for speed
                print(f"Training Standard LSTM model...")
            
            early_stop = EarlyStopping(monitor='loss', patience=2, restore_best_weights=True)
            history = model.fit(X_train, y_train, epochs=epochs, batch_size=batch_size, 
                              verbose=0, callbacks=[early_stop], validation_split=0.05)

            # Evaluate
            y_pred = model.predict(X_test)
            mae = mean_absolute_error(y_test, y_pred)
            mse = mean_squared_error(y_test, y_pred)
            rmse = np.sqrt(mse)
            r2 = r2_score(y_test, y_pred)
            
            print(f"Mean Absolute Error: {mae:.4f}")
            print(f"Root Mean Squared Error: {rmse:.4f}")
            print(f"R² Score: {r2:.4f}")

            # Predict future days
            future_predictions = []
            last_sequence = X[-1]

            for _ in range(days):
                next_pred = model.predict(last_sequence.reshape(1, sequence_length, len(feature_columns)), verbose=0)[0][0]
                new_row = np.copy(last_sequence[-1])
                new_row[0] = next_pred  # update Close price with predicted value
                last_sequence = np.vstack([last_sequence[1:], new_row])
                future_predictions.append(next_pred)

            # Denormalize
            dummy = np.zeros((len(future_predictions), scaled_data.shape[1]))
            dummy[:, 0] = future_predictions
            predictions_denorm = self.scaler.inverse_transform(dummy)[:, 0]

            # Dates for visualization
            historical_dates = df.index[-90:].strftime('%Y-%m-%d').tolist()
            historical_prices_raw = df['Close'].iloc[-90:].tolist()
            last_date = df.index[-1]
            prediction_dates = [(last_date + timedelta(days=i+1)).strftime('%Y-%m-%d') for i in range(days)]

            # Convert prices to INR if foreign stock
            historical_prices = convert_prices_array_to_inr(historical_prices_raw, self.symbol)
            predictions_inr = convert_prices_array_to_inr(predictions_denorm.tolist(), self.symbol)
            current_price_inr = convert_price_to_inr(df['Close'].iloc[-1], self.symbol)
            mae_inr = convert_price_to_inr(mae, self.symbol)
            rmse_inr = convert_price_to_inr(rmse, self.symbol)

            # Calculate confidence based on multiple metrics
            # Avoid division by zero in confidence calculation
            current_price = df['Close'].iloc[-1]
            if current_price > 0:
                confidence = max(0, min(100, (1 - mae / current_price) * 100))
            else:
                confidence = 50  # Default confidence if current price is 0
            
            # Model architecture info
            model_info = {
                'type': model_type,
                'layers': len(model.layers),
                'total_params': model.count_params(),
                'epochs_trained': len(history.history['loss'])
            }

            return {
                'success': True,
                'historical_dates': historical_dates,
                'historical_prices': historical_prices,
                'prediction_dates': prediction_dates,
                'predictions': predictions_inr,
                'mae': float(mae_inr),
                'rmse': float(rmse_inr),
                'r2_score': float(r2),
                'confidence': float(confidence),
                'current_price': float(current_price_inr),
                'features_used': feature_columns,
                'model_info': model_info,
                'model_type': model_type,
                'currency': 'INR'
            }

        except Exception as e:
            print("Error in prediction:", str(e))
            import traceback
            traceback.print_exc()
            return None


# Example usage
if __name__ == "__main__":
    predictor = HistoricalPredictor("AAPL")  # Example: Apple stock
    result = predictor.predict(days=7)
    if result and result['success']:
        print("Predicted prices for next 7 days:")
        for d, p in zip(result['prediction_dates'], result['predictions']):
            print(f"{d}: {p:.2f}")