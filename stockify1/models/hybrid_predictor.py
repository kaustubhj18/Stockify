from models.historical_predictor import HistoricalPredictor
from models.sentiment_analyzer import SentimentAnalyzer
from models.currency_utils import convert_price_to_inr
import numpy as np
import yfinance as yf

class HybridPredictor:
    """
    Hybrid prediction model combining historical analysis and sentiment analysis
    for more accurate and reliable stock price predictions
    """
    
    def __init__(self, symbol):
        self.symbol = symbol
        self.historical_predictor = HistoricalPredictor(symbol)
        self.sentiment_analyzer = SentimentAnalyzer(symbol)
        
    def combine_predictions(self, historical_data, sentiment_data):
        """
        Combine historical and sentiment predictions using weighted average
        Weights are determined by model confidence and accuracy
        """
        # Calculate weights based on model performance
        # Historical model weight based on MAE (lower MAE = higher weight)
        historical_mae = historical_data.get('mae', 1.0)
        historical_accuracy = 1 / (1 + historical_mae)  # Convert MAE to accuracy score
        
        # Sentiment model weight based on confidence
        sentiment_confidence = sentiment_data.get('confidence', 50) / 100
        
        # Normalize weights
        total_weight = historical_accuracy + sentiment_confidence
        if total_weight > 0:
            historical_weight = historical_accuracy / total_weight
            sentiment_weight = sentiment_confidence / total_weight
        else:
            historical_weight = 0.7  # Default weights if both are 0
            sentiment_weight = 0.3
        
        # Combine predictions
        historical_predictions = historical_data.get('predictions', [])
        sentiment_predictions = sentiment_data.get('predictions', [])
        
        # Handle case where one model has no predictions
        if not historical_predictions and not sentiment_predictions:
            return [], historical_weight, sentiment_weight
        
        if not historical_predictions:
            return sentiment_predictions, 0, 1.0
        
        if not sentiment_predictions:
            return historical_predictions, 1.0, 0
        
        combined_predictions = []
        for i in range(min(len(historical_predictions), len(sentiment_predictions))):
            combined = (historical_predictions[i] * historical_weight + 
                       sentiment_predictions[i] * sentiment_weight)
            combined_predictions.append(round(combined, 2))
        
        return combined_predictions, historical_weight, sentiment_weight
    
    def calculate_risk_score(self, historical_result, sentiment_result, price_change_percent):
        """
        Calculate risk score (0-100) and provide investment recommendation
        Lower score = Lower risk, Higher score = Higher risk
        """
        risk_factors = []
        
        # Factor 1: Historical Model Accuracy (MAE)
        mae = historical_result.get('mae', 0)
        mae_risk = min(mae * 10, 30)  # Max 30 points
        risk_factors.append(('Model Accuracy Risk', mae_risk))
        
        # Factor 2: Sentiment Volatility
        sentiment_score = sentiment_result.get('sentiment_score', 50)
        sentiment_risk = abs(50 - sentiment_score) / 2  # Max 25 points
        risk_factors.append(('Sentiment Volatility', sentiment_risk))
        
        # Factor 3: Price Volatility
        volatility = abs(price_change_percent)
        volatility_risk = min(volatility * 2, 25)  # Max 25 points
        risk_factors.append(('Price Volatility', volatility_risk))
        
        # Factor 4: Market Sentiment Confidence
        confidence = sentiment_result.get('confidence', 50)
        confidence_risk = (100 - confidence) / 5  # Max 20 points
        risk_factors.append(('Market Uncertainty', confidence_risk))
        
        # Calculate total risk score
        total_risk = sum([factor[1] for factor in risk_factors])
        
        # Determine risk level and recommendation
        if total_risk < 25:
            risk_level = 'Low Risk'
            recommendation = 'Strong Buy'
            risk_color = '#10b981'
        elif total_risk < 40:
            risk_level = 'Low-Medium Risk'
            recommendation = 'Buy'
            risk_color = '#22c55e'
        elif total_risk < 55:
            risk_level = 'Medium Risk'
            recommendation = 'Hold'
            risk_color = '#f59e0b'
        elif total_risk < 70:
            risk_level = 'Medium-High Risk'
            recommendation = 'Sell'
            risk_color = '#f97316'
        else:
            risk_level = 'High Risk'
            recommendation = 'Strong Sell'
            risk_color = '#ef4444'
        
        return {
            'risk_score': round(total_risk, 2),
            'risk_level': risk_level,
            'recommendation': recommendation,
            'risk_color': risk_color,
            'risk_factors': [(name, round(score, 2)) for name, score in risk_factors]
        }
    
    def get_sector_analysis(self, sector, skip_predictions=False):
        """
        Get predictions for similar companies in the same sector
        Set skip_predictions=True for faster loading (only shows current prices)
        """
        # Mapping of sectors to major Indian and international companies
        sector_companies = {
            'Technology': ['TCS.NS', 'INFY.NS', 'WIPRO.NS', 'AAPL', 'MSFT'],
            'Financial Services': ['HDFCBANK.NS', 'ICICIBANK.NS', 'SBIN.NS', 'JPM', 'BAC'],
            'Healthcare': ['SUNPHARMA.NS', 'DRREDDY.NS', 'JNJ', 'PFE'],
            'Consumer Cyclical': ['MARUTI.NS', 'TATAMOTORS.NS', 'TSLA', 'AMZN'],
            'Energy': ['RELIANCE.NS', 'ONGC.NS', 'XOM', 'CVX'],
            'Industrials': ['LT.NS', 'BHARTIARTL.NS', 'BA', 'CAT'],
            'Basic Materials': ['TATASTEEL.NS', 'HINDALCO.NS', 'BHP'],
            'Consumer Defensive': ['ITC.NS', 'HINDUNILVR.NS', 'PG', 'KO'],
            'Communication Services': ['BHARTIARTL.NS', 'T', 'VZ', 'META'],
            'Real Estate': ['DLF.NS', 'GODREJPROP.NS', 'AMT'],
            'Utilities': ['NTPC.NS', 'POWERGRID.NS', 'NEE']
        }
        
        companies = sector_companies.get(sector, [])
        sector_predictions = []
        
        # Limit to 2 companies for faster performance (reduced from 3)
        for company_symbol in companies[:2]:
            if company_symbol == self.symbol:
                continue
                
            try:
                stock = yf.Ticker(company_symbol)
                info = stock.info
                hist = stock.history(period='3d')  # Reduced from 5d to 3d for faster loading
                
                if hist.empty:
                    continue
                
                current_price = hist['Close'].iloc[-1]
                prev_close = hist['Close'].iloc[-2] if len(hist) >= 2 else current_price
                # Avoid division by zero
                if prev_close > 0:
                    change_percent = ((current_price - prev_close) / prev_close) * 100
                else:
                    change_percent = 0
                
                if skip_predictions:
                    # Quick mode - just show current prices
                    # Estimate prediction based on recent trend
                    # Avoid division by zero
                    start_price = hist['Close'].iloc[0]
                    if start_price > 0:
                        recent_change = ((hist['Close'].iloc[-1] - start_price) / start_price) * 100
                        predicted_price = current_price * (1 + (recent_change * 0.1) / 100)
                        predicted_change = recent_change * 0.1
                    else:
                        predicted_price = current_price
                        predicted_change = 0
                    
                    # Convert to INR if foreign stock
                    current_price_inr = convert_price_to_inr(current_price, company_symbol)
                    predicted_price_inr = convert_price_to_inr(predicted_price, company_symbol)
                    
                    sector_predictions.append({
                        'symbol': company_symbol,
                        'name': info.get('longName', company_symbol),
                        'current_price': round(current_price_inr, 2),
                        'change_percent': round(change_percent, 2),
                        'predicted_price': round(predicted_price_inr, 2),
                        'predicted_change': round(predicted_change, 2)
                    })
                else:
                    # Full mode - with ML predictions (slower)
                    predictor = HistoricalPredictor(company_symbol)
                    prediction_result = predictor.predict(days=14, model_type='standard')
                    
                    if prediction_result and prediction_result.get('success'):
                        # Predictions are already converted to INR in HistoricalPredictor
                        predictions_list = prediction_result['predictions']
                        if len(predictions_list) > 0:
                            avg_prediction = sum(predictions_list) / len(predictions_list)
                            current_price_inr = prediction_result.get('current_price', current_price)
                            # Avoid division by zero
                            if current_price_inr > 0:
                                predicted_change = ((avg_prediction - current_price_inr) / current_price_inr) * 100
                            else:
                                predicted_change = 0
                        else:
                            avg_prediction = current_price
                            predicted_change = 0
                        
                        sector_predictions.append({
                            'symbol': company_symbol,
                            'name': info.get('longName', company_symbol),
                            'current_price': round(current_price_inr, 2),
                            'change_percent': round(change_percent, 2),
                            'predicted_price': round(avg_prediction, 2),
                            'predicted_change': round(predicted_change, 2)
                        })
            except Exception as e:
                print(f"Error analyzing {company_symbol}: {str(e)}")
                continue
        
        return sector_predictions
    
    def explain_prediction(self, historical_result, sentiment_result, price_change_percent):
        """
        Generate explanation for why the model predicted a certain price
        """
        explanations = []
        
        # Historical Analysis Explanation
        features = historical_result.get('features_used', [])
        mae = historical_result.get('mae', 0)
        
        if mae < 2:
            explanations.append(f"The historical model shows high accuracy (MAE: ₹{mae:.2f}), indicating reliable technical patterns.")
        elif mae < 5:
            explanations.append(f"The historical model shows moderate accuracy (MAE: ₹{mae:.2f}), suggesting some price volatility.")
        else:
            explanations.append(f"The historical model shows lower accuracy (MAE: ₹{mae:.2f}), indicating high market volatility.")
        
        # Sentiment Analysis Explanation
        sentiment_score = sentiment_result.get('sentiment_score', 50)
        sentiment_category = sentiment_result.get('overall_sentiment', 'Neutral')
        
        if sentiment_score >= 60:
            explanations.append(f"Market sentiment is {sentiment_category} ({sentiment_score}/100), with positive news coverage driving optimism.")
        elif sentiment_score >= 40:
            explanations.append(f"Market sentiment is {sentiment_category} ({sentiment_score}/100), showing balanced news coverage.")
        else:
            explanations.append(f"Market sentiment is {sentiment_category} ({sentiment_score}/100), with negative news creating caution.")
        
        # Price Movement Explanation
        if price_change_percent > 5:
            explanations.append(f"The model predicts a strong upward trend (+{price_change_percent:.2f}%) based on positive technical indicators and market sentiment.")
        elif price_change_percent > 2:
            explanations.append(f"The model predicts moderate growth (+{price_change_percent:.2f}%) supported by favorable market conditions.")
        elif price_change_percent > -2:
            explanations.append(f"The model predicts stable prices ({price_change_percent:+.2f}%) with balanced market forces.")
        elif price_change_percent > -5:
            explanations.append(f"The model predicts a moderate decline ({price_change_percent:.2f}%) due to weakening technical signals.")
        else:
            explanations.append(f"The model predicts a significant decline ({price_change_percent:.2f}%) based on negative indicators.")
        
        # Technical Indicators Explanation
        if 'RSI' in features:
            explanations.append("RSI (Relative Strength Index) helps identify overbought or oversold conditions.")
        if 'MACD' in features:
            explanations.append("MACD analysis reveals momentum shifts and potential trend reversals.")
        if 'MA_50' in features:
            explanations.append("Moving averages smooth out price data to identify the overall trend direction.")
        
        return explanations

    def predict(self, days=14):
        """
        Generate hybrid predictions combining both models
        """
        try:
            # Get predictions from both models (use standard model for speed)
            historical_result = self.historical_predictor.predict(days, model_type='standard')
            sentiment_result = self.sentiment_analyzer.analyze()
            
            if not historical_result or not historical_result.get('success'):
                return {
                    'success': False,
                    'message': 'Historical prediction failed'
                }
            
            if not sentiment_result or not sentiment_result.get('success'):
                return {
                    'success': False,
                    'message': 'Sentiment analysis failed'
                }
            
            # Combine predictions
            combined_predictions, hist_weight, sent_weight = self.combine_predictions(
                historical_result, sentiment_result
            )
            
            # Calculate metrics
            current_price = historical_result.get('current_price', 0)
            if len(combined_predictions) > 0:
                avg_prediction = sum(combined_predictions) / len(combined_predictions)
            else:
                avg_prediction = current_price
            
            price_change = avg_prediction - current_price
            # Avoid division by zero
            if current_price > 0:
                price_change_percent = (price_change / current_price) * 100
            else:
                price_change_percent = 0
            
            # Calculate prediction range (min and max)
            if combined_predictions:
                prediction_min = min(combined_predictions)
                prediction_max = max(combined_predictions)
            else:
                prediction_min = avg_prediction
                prediction_max = avg_prediction
            
            # Calculate overall confidence
            historical_confidence = (1 / (1 + historical_result.get('mae', 1))) * 100
            sentiment_confidence = sentiment_result.get('confidence', 50)
            overall_confidence = (historical_confidence * hist_weight + 
                                sentiment_confidence * sent_weight)
            
            # Generate dates for predictions
            from datetime import datetime, timedelta
            last_date = datetime.now()
            prediction_dates = [(last_date + timedelta(days=i+1)).strftime('%Y-%m-%d') 
                              for i in range(len(combined_predictions))]
            
            risk_analysis = self.calculate_risk_score(historical_result, sentiment_result, price_change_percent)
            
            explanations = self.explain_prediction(historical_result, sentiment_result, price_change_percent)
            
            stock = yf.Ticker(self.symbol)
            sector = stock.info.get('sector', 'Unknown')
            # Use quick mode (skip_predictions=True) for faster loading
            sector_analysis = self.get_sector_analysis(sector, skip_predictions=True) if sector != 'Unknown' else []
            
            return {
                'success': True,
                'current_price': current_price,
                'predictions': combined_predictions,
                'prediction_dates': prediction_dates,
                'avg_prediction': round(avg_prediction, 2),
                'price_change': round(price_change, 2),
                'price_change_percent': round(price_change_percent, 2),
                'prediction_min': round(prediction_min, 2),
                'prediction_max': round(prediction_max, 2),
                'overall_confidence': round(overall_confidence, 2),
                'historical_weight': round(hist_weight * 100, 2),
                'sentiment_weight': round(sent_weight * 100, 2),
                'historical_mae': historical_result.get('mae', 0),
                'sentiment_score': sentiment_result.get('sentiment_score', 50),
                'sentiment_category': sentiment_result.get('overall_sentiment', 'Neutral'),
                'historical_data': historical_result,
                'sentiment_data': sentiment_result,
                'risk_analysis': risk_analysis,
                'explanations': explanations,
                'sector': sector,
                'sector_analysis': sector_analysis
            }
            
        except Exception as e:
            print(f"Error in hybrid prediction: {str(e)}")
            return {
                'success': False,
                'message': str(e)
            }
