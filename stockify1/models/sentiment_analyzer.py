import requests
from bs4 import BeautifulSoup
from textblob import TextBlob
from datetime import datetime, timedelta
import yfinance as yf
import re
from models.currency_utils import convert_price_to_inr, convert_prices_array_to_inr

class SentimentAnalyzer:
    """
    Sentiment analysis for stocks using news articles and financial data
    from trusted and freely accessible sources
    """
    
    def __init__(self, symbol):
        self.symbol = symbol
        self.stock = yf.Ticker(symbol)
        
    def get_stock_news(self):
        """
        Get news articles for the stock from multiple sources
        Priority: yfinance news > Google News scraping > Yahoo Finance > Performance-based fallback
        """
        articles = []
        
        # Try 1: Get news from yfinance (most reliable when available)
        try:
            news = self.stock.news
            if news and len(news) > 0:
                formatted_news = []
                for article in news[:8]:  # Reduced from 15 to 8 for faster processing
                    # Only include articles with valid data
                    title = article.get('title', '').strip()
                    publisher = article.get('publisher', '').strip()
                    summary = article.get('summary', '').strip()
                    
                    if title and publisher:
                        formatted_news.append({
                            'title': title,
                            'publisher': publisher,
                            'link': article.get('link', '#'),
                            'summary': summary if summary else self.generate_article_summary(title, publisher),
                            'providerPublishTime': article.get('providerPublishTime', int(datetime.now().timestamp()))
                        })
                
                if len(formatted_news) >= 2:  # Lower threshold to get more news
                    return formatted_news
        except Exception as e:
            print(f"yfinance news error: {e}")
            pass
        
        # Try 2: Scrape Google News RSS feed
        try:
            info = self.stock.info
            company_name = info.get('longName', info.get('shortName', self.symbol))
            
            # Search Google Finance for news
            search_query = f"{company_name} stock news"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            # Try Google News RSS feed
            rss_url = f"https://news.google.com/rss/search?q={search_query.replace(' ', '+')}&hl=en-IN&gl=IN&ceid=IN:en"
            response = requests.get(rss_url, headers=headers, timeout=8)
            
            if response.status_code == 200:
                # Try different parsers for better compatibility
                try:
                    soup = BeautifulSoup(response.content, features='xml')
                except:
                    try:
                        soup = BeautifulSoup(response.content, features='lxml')
                    except:
                        soup = BeautifulSoup(response.content, features='html.parser')
                
                items = soup.find_all('item')
                
                for item in items[:12]:
                    title = item.find('title')
                    pub_date = item.find('pubDate')
                    link = item.find('link')
                    source = item.find('source')
                    description = item.find('description')
                    
                    if title and title.text.strip():
                        # Parse publication date
                        pub_timestamp = int(datetime.now().timestamp())
                        if pub_date:
                            try:
                                pub_datetime = datetime.strptime(pub_date.text, '%a, %d %b %Y %H:%M:%S %Z')
                                pub_timestamp = int(pub_datetime.timestamp())
                            except:
                                pass
                        
                        # Extract summary from description or generate one
                        summary = ""
                        if description and description.text.strip():
                            # Clean HTML tags from description
                            desc_text = BeautifulSoup(description.text, 'html.parser').get_text()
                            summary = desc_text[:200] + "..." if len(desc_text) > 200 else desc_text
                        else:
                            summary = self.generate_article_summary(title.text.strip(), source.text.strip() if source else 'Google News')
                        
                        articles.append({
                            'title': title.text.strip(),
                            'publisher': source.text.strip() if source else 'Google News',
                            'link': link.text.strip() if link else '#',
                            'summary': summary,
                            'providerPublishTime': pub_timestamp
                        })
                
                if len(articles) >= 2:  # Lower threshold
                    return articles[:10]
        except Exception as e:
            print(f"Google News error: {e}")
            pass
        
        # Try 3: Alternative - Yahoo Finance news page scraping
        try:
            url = f"https://finance.yahoo.com/quote/{self.symbol}/news"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=8)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                news_items = soup.find_all('h3', class_='Mb(5px)')
                
                for item in news_items[:8]:
                    title_elem = item.find('a')
                    if title_elem and title_elem.text.strip():
                        summary = self.generate_article_summary(title_elem.text.strip(), 'Yahoo Finance')
                        articles.append({
                            'title': title_elem.text.strip(),
                            'publisher': 'Yahoo Finance',
                            'link': f"https://finance.yahoo.com{title_elem.get('href', '#')}",
                            'summary': summary,
                            'providerPublishTime': int((datetime.now() - timedelta(hours=len(articles)*2)).timestamp())
                        })
                
                if len(articles) >= 2:
                    return articles[:8]
        except Exception as e:
            print(f"Yahoo Finance error: {e}")
            pass
        
        # Fallback: Return empty list - the analyze() method will handle this
        # by showing "No recent news articles available" message
        return []

    def generate_article_summary(self, title, publisher):
        """
        Generate a contextual summary based on title and publisher
        """
        try:
            # Extract key information from title
            title_lower = title.lower()
            
            # Stock-specific keywords and their summaries
            if 'earnings' in title_lower or 'quarterly' in title_lower:
                if 'beat' in title_lower or 'exceed' in title_lower or 'strong' in title_lower:
                    return f"Positive earnings report showing better-than-expected results. {publisher} reports strong quarterly performance with potential positive market impact."
                elif 'miss' in title_lower or 'disappoint' in title_lower or 'weak' in title_lower:
                    return f"Mixed earnings results with some challenges. {publisher} highlights quarterly performance concerns that may affect stock valuation."
                else:
                    return f"Latest quarterly earnings update from {publisher}. Financial results provide insights into company performance and market position."
            
            elif 'analyst' in title_lower or 'upgrade' in title_lower or 'downgrade' in title_lower:
                if 'upgrade' in title_lower or 'buy' in title_lower or 'positive' in title_lower:
                    return f"Analyst upgrade and positive outlook. {publisher} reports improved analyst sentiment with potential upside for investors."
                elif 'downgrade' in title_lower or 'sell' in title_lower or 'negative' in title_lower:
                    return f"Analyst concerns and revised outlook. {publisher} highlights changing analyst sentiment with cautious market expectations."
                else:
                    return f"Analyst coverage update from {publisher}. Professional analysis provides market insights and investment perspective."
            
            elif 'acquisition' in title_lower or 'merger' in title_lower or 'deal' in title_lower:
                return f"Strategic business development news. {publisher} reports on corporate transaction that may impact future growth and market position."
            
            elif 'dividend' in title_lower or 'payout' in title_lower:
                return f"Dividend and shareholder return update. {publisher} covers dividend policy changes affecting investor returns and company financial strategy."
            
            elif 'guidance' in title_lower or 'forecast' in title_lower or 'outlook' in title_lower:
                return f"Financial guidance and future outlook. {publisher} provides management's perspective on future performance and strategic direction."
            
            elif 'stock' in title_lower or 'share' in title_lower:
                if 'rise' in title_lower or 'gain' in title_lower or 'up' in title_lower:
                    return f"Positive stock performance update. {publisher} reports favorable market movement with potential continued momentum."
                elif 'fall' in title_lower or 'drop' in title_lower or 'down' in title_lower:
                    return f"Stock performance concerns. {publisher} highlights market challenges that may require investor attention."
                else:
                    return f"Stock market update from {publisher}. Latest trading activity and market sentiment analysis."
            
            else:
                # Generic summary based on publisher
                if 'times of india' in publisher.lower() or 'toi' in publisher.lower():
                    return f"Latest business and market news from Times of India. Comprehensive coverage of corporate developments and market trends."
                elif 'business standard' in publisher.lower():
                    return f"Financial market analysis from Business Standard. Professional insights into economic and corporate developments."
                elif 'economic times' in publisher.lower():
                    return f"Economic and financial news from Economic Times. In-depth coverage of business and market developments."
                elif 'reuters' in publisher.lower():
                    return f"Global financial news from Reuters. International perspective on market developments and corporate news."
                elif 'bloomberg' in publisher.lower():
                    return f"Financial market intelligence from Bloomberg. Professional analysis of market trends and corporate developments."
                else:
                    return f"Latest market and business news from {publisher}. Comprehensive coverage of financial developments and market trends."
                    
        except Exception as e:
            return f"Latest business news from {publisher}. Market update covering recent developments and trends."

    def analyze_text_sentiment(self, text):
        """
        Analyze sentiment of text using TextBlob
        Returns polarity (-1 to 1) and subjectivity (0 to 1)
        """
        try:
            blob = TextBlob(text)
            return {
                'polarity': blob.sentiment.polarity,
                'subjectivity': blob.sentiment.subjectivity
            }
        except:
            return {'polarity': 0, 'subjectivity': 0}
    
    def categorize_sentiment(self, polarity):
        """
        Categorize sentiment based on polarity score
        Polarity ranges from -1 to 1, which maps to 0-100 score
        Score ranges: 0-30 (Very Negative), 30-42.5 (Negative), 42.5-57.5 (Neutral), 57.5-70 (Positive), 70-100 (Very Positive)
        """
        if polarity > 0.4:  # Score > 70
            return 'Very Positive'
        elif polarity > 0.15:  # Score > 57.5
            return 'Positive'
        elif polarity > -0.15:  # Score > 42.5
            return 'Neutral'
        elif polarity > -0.4:  # Score > 30
            return 'Negative'
        else:  # Score <= 30
            return 'Very Negative'
    
    def get_sentiment_score(self, polarity):
        """
        Convert polarity to a 0-100 sentiment score
        """
        return round((polarity + 1) * 50, 2)
    
    def analyze(self):
        """
        Perform comprehensive sentiment analysis
        Returns sentiment data and predictions
        """
        try:
            # Get news articles
            news_articles = self.get_stock_news()
            
            # Get stock info for additional context - OPTIMIZED for speed
            info = self.stock.info
            hist = self.stock.history(period="3mo")  # Reduced from 6mo to 3mo for faster loading
            
            if not hist.empty and len(hist) > 20:
                current_price = hist['Close'].iloc[-1]
                
                # Calculate multiple timeframe performance
                week_ago_price = hist['Close'].iloc[-5] if len(hist) >= 5 else current_price
                month_ago_price = hist['Close'].iloc[-20] if len(hist) >= 20 else current_price
                three_month_ago_price = hist['Close'].iloc[0]
                
                # Avoid division by zero
                price_change_1w = ((current_price - week_ago_price) / week_ago_price) * 100 if week_ago_price > 0 else 0
                price_change_1m = ((current_price - month_ago_price) / month_ago_price) * 100 if month_ago_price > 0 else 0
                price_change_3m = ((current_price - three_month_ago_price) / three_month_ago_price) * 100 if three_month_ago_price > 0 else 0
                
                # Calculate volatility (standard deviation of returns)
                returns = hist['Close'].pct_change().dropna()
                volatility = returns.std() * 100
                
                # Calculate momentum indicators
                recent_returns = returns.tail(10).mean() * 100
                # Avoid division by zero in volume trend
                avg_volume = hist['Volume'].mean()
                if avg_volume > 0:
                    volume_trend = (hist['Volume'].tail(5).mean() / avg_volume) - 1
                else:
                    volume_trend = 0
            else:
                current_price = info.get('regularMarketPrice', info.get('currentPrice', 0))
                price_change_1w = 0
                price_change_1m = 0
                price_change_3m = 0
                volatility = 5
                recent_returns = 0
                volume_trend = 0
            
            if not news_articles or len(news_articles) == 0:
                
                # Weight recent performance more heavily
                weighted_performance = (price_change_1w * 0.5) + (price_change_1m * 0.3) + (price_change_3m * 0.2)
                
                # Convert performance to sentiment polarity (-1 to 1)
                if weighted_performance > 15:
                    base_sentiment = 0.7
                    sentiment_label = "Very Positive"
                elif weighted_performance > 5:
                    base_sentiment = 0.4
                    sentiment_label = "Positive"
                elif weighted_performance > 0:
                    base_sentiment = 0.15
                    sentiment_label = "Slightly Positive"
                elif weighted_performance > -5:
                    base_sentiment = -0.15
                    sentiment_label = "Slightly Negative"
                elif weighted_performance > -15:
                    base_sentiment = -0.4
                    sentiment_label = "Negative"
                else:
                    base_sentiment = -0.7
                    sentiment_label = "Very Negative"
                
                # Adjust for momentum
                momentum_adjustment = min(max(recent_returns * 0.02, -0.2), 0.2)
                
                # Adjust for volatility (high volatility = more uncertainty = lower sentiment)
                volatility_penalty = min(volatility * 0.015, 0.25)
                
                # Adjust for volume trend
                volume_adjustment = 0
                if price_change_1w > 0 and volume_trend > 0:
                    volume_adjustment = 0.1
                elif price_change_1w < 0 and volume_trend > 0:
                    volume_adjustment = -0.1
                
                # Calculate final sentiment
                final_sentiment = base_sentiment + momentum_adjustment - volatility_penalty + volume_adjustment
                final_sentiment = max(-1, min(1, final_sentiment))
                
                # Recategorize based on final sentiment
                sentiment_label = self.categorize_sentiment(final_sentiment)
                
                # Create comprehensive sentiment analysis using multiple indicators
                sentiment_indicators = []
                indicator_weights = []
                
                # Indicator 1: Recent price performance (1 week) - Weight: 0.25
                if price_change_1w > 2:
                    sentiment_indicators.append('positive')
                    indicator_weights.append(0.25)
                elif price_change_1w < -2:
                    sentiment_indicators.append('negative')
                    indicator_weights.append(0.25)
                else:
                    sentiment_indicators.append('neutral')
                    indicator_weights.append(0.25)
                
                # Indicator 2: Recent price performance (1 month) - Weight: 0.20
                if price_change_1m > 5:
                    sentiment_indicators.append('positive')
                    indicator_weights.append(0.20)
                elif price_change_1m < -5:
                    sentiment_indicators.append('negative')
                    indicator_weights.append(0.20)
                else:
                    sentiment_indicators.append('neutral')
                    indicator_weights.append(0.20)
                
                # Indicator 3: Volatility analysis - Weight: 0.15
                if volatility < 0.02:  # Low volatility = stable
                    sentiment_indicators.append('neutral')
                    indicator_weights.append(0.15)
                elif volatility > 0.05:  # High volatility
                    if weighted_performance > 0:
                        sentiment_indicators.append('positive')
                        indicator_weights.append(0.15)
                    else:
                        sentiment_indicators.append('negative')
                        indicator_weights.append(0.15)
                else:
                    sentiment_indicators.append('neutral')
                    indicator_weights.append(0.15)
                
                # Indicator 4: Momentum trend (10-day) - Weight: 0.20
                recent_prices = hist['Close'].tail(10)
                # Avoid division by zero
                start_price = recent_prices.iloc[0]
                if start_price > 0:
                    momentum = (recent_prices.iloc[-1] - start_price) / start_price * 100
                else:
                    momentum = 0
                if momentum > 1:
                    sentiment_indicators.append('positive')
                    indicator_weights.append(0.20)
                elif momentum < -1:
                    sentiment_indicators.append('negative')
                    indicator_weights.append(0.20)
                else:
                    sentiment_indicators.append('neutral')
                    indicator_weights.append(0.20)
                
                # Indicator 5: Volume analysis - Weight: 0.20
                avg_volume = hist['Volume'].mean()
                recent_volume = hist['Volume'].tail(5).mean()
                # Avoid division by zero
                if avg_volume > 0:
                    volume_ratio = recent_volume / avg_volume
                else:
                    volume_ratio = 1
                if volume_ratio > 1.2:  # High volume
                    if weighted_performance > 0:
                        sentiment_indicators.append('positive')
                        indicator_weights.append(0.20)
                    else:
                        sentiment_indicators.append('negative')
                        indicator_weights.append(0.20)
                else:
                    sentiment_indicators.append('neutral')
                    indicator_weights.append(0.20)
                
                # Calculate weighted sentiment scores
                positive_score = 0
                negative_score = 0
                neutral_score = 0
                
                for i, indicator in enumerate(sentiment_indicators):
                    weight = indicator_weights[i]
                    if indicator == 'positive':
                        positive_score += weight
                    elif indicator == 'negative':
                        negative_score += weight
                    else:
                        neutral_score += weight
                
                # Count indicators for display
                positive_count = sentiment_indicators.count('positive')
                negative_count = sentiment_indicators.count('negative')
                neutral_count = sentiment_indicators.count('neutral')
                total_indicators = len(sentiment_indicators)
                
                # Determine overall sentiment based on weighted scores
                if positive_score > negative_score and positive_score > neutral_score:
                    overall_sentiment_label = 'Positive'
                elif negative_score > positive_score and negative_score > neutral_score:
                    overall_sentiment_label = 'Negative'
                else:
                    overall_sentiment_label = 'Neutral'
                
                # Calculate sentiment score (0-100 scale) - this will be consistent with sentiment category
                sentiment_score = (positive_score - negative_score) * 100 + 50
                sentiment_score = max(0, min(100, sentiment_score))
                
                # Generate predictions based on the SAME sentiment logic to ensure consistency
                # Convert sentiment score to impact factor (-1 to 1 range)
                sentiment_impact_factor = (sentiment_score - 50) / 50  # -1 to 1
                sentiment_impact = sentiment_impact_factor * 0.08  # Max 8% impact
                momentum_impact = (weighted_performance / 100) * 0.02
                total_impact = sentiment_impact + momentum_impact
                predicted_change_percent = total_impact * 100
                
                predictions = []
                for day in range(1, 15):
                    daily_impact = total_impact * (1 - (day * 0.04))
                    predicted_price = current_price * (1 + daily_impact)
                    predictions.append(round(predicted_price, 2))
                
                # Convert prices to INR if foreign stock
                current_price_inr = convert_price_to_inr(current_price, self.symbol)
                predictions_inr = convert_prices_array_to_inr(predictions, self.symbol)
                
                # Calculate confidence
                data_confidence = min((len(hist) / 120) * 100, 100)
                volatility_confidence = max(0, 100 - (volatility * 8))
                performance_confidence = 100 - abs(weighted_performance)
                
                confidence = (data_confidence * 0.4 + volatility_confidence * 0.4 + performance_confidence * 0.2)
                confidence = max(30, min(85, confidence))
                
                return {
                    'success': True,
                    'overall_sentiment': overall_sentiment_label,
                    'sentiment_score': round(sentiment_score, 0),
                    'polarity': round(final_sentiment, 3),
                    'positive_count': positive_count,
                    'negative_count': negative_count,
                    'neutral_count': neutral_count,
                    'total_indicators': total_indicators,
                    'confidence': round(confidence, 2),
                    'current_price': round(current_price_inr, 2),
                    'predicted_change_percent': round(predicted_change_percent, 2),
                    'predictions': [round(p, 2) for p in predictions_inr],
                    'articles': [],  # Empty array - no fake articles
                    'currency': 'INR',
                    'performance_1w': round(price_change_1w, 2),
                    'performance_1m': round(price_change_1m, 2),
                    'performance_3m': round(price_change_3m, 2),
                    'volatility': round(volatility, 2),
                    'sentiment_indicators': sentiment_indicators  # For debugging
                }
            
            sentiments = []
            articles_data = []
            
            for article in news_articles[:20]:
                title = article.get('title', '')
                publisher = article.get('publisher', 'Unknown')
                link = article.get('link', '')
                published = article.get('providerPublishTime', 0)
                summary = article.get('summary', '')
                
                # Analyze title sentiment
                sentiment = self.analyze_text_sentiment(title)
                
                sentiments.append(sentiment['polarity'])
                
                articles_data.append({
                    'title': title,
                    'publisher': publisher,
                    'link': link,
                    'published': datetime.fromtimestamp(published).strftime('%Y-%m-%d %H:%M') if published else 'Unknown',
                    'summary': summary,
                    'sentiment': self.categorize_sentiment(sentiment['polarity']),
                    'polarity': round(sentiment['polarity'], 3),
                    'score': self.get_sentiment_score(sentiment['polarity'])
                })
            
            # Calculate overall sentiment from news
            if sentiments:
                avg_sentiment = sum(sentiments) / len(sentiments)
                news_positive_count = sum(1 for s in sentiments if s > 0.1)
                news_negative_count = sum(1 for s in sentiments if s < -0.1)
                news_neutral_count = len(sentiments) - news_positive_count - news_negative_count
            else:
                avg_sentiment = 0
                news_positive_count = 0
                news_negative_count = 0
                news_neutral_count = 0
            
            weighted_performance = (price_change_1w * 0.5) + (price_change_1m * 0.3) + (price_change_3m * 0.2)
            performance_adjustment = weighted_performance * 0.015
            adjusted_sentiment = (avg_sentiment * 0.6) + (performance_adjustment * 0.4)
            
            # Adjust for volatility and momentum
            volatility_penalty = min(volatility * 0.015, 0.25)
            momentum_adjustment = min(max(recent_returns * 0.02, -0.15), 0.15)
            
            final_sentiment = adjusted_sentiment + momentum_adjustment - volatility_penalty
            final_sentiment = max(-1, min(1, final_sentiment))
            
            # Generate predictions based on news sentiment and performance
            predictions = []
            
            # Calculate sentiment impact from news and performance
            news_impact = avg_sentiment * 0.05 if sentiments else 0  # Max 5% impact from news
            performance_impact = (price_change_1w + price_change_1m) / 2 * 0.01  # Performance impact
            volatility_impact = -volatility * 0.02  # Volatility penalty
            
            total_impact = news_impact + performance_impact + volatility_impact
            
            # Generate 14-day predictions
            for day in range(1, 15):
                daily_impact = total_impact * (1 - (day * 0.03))  # Decay over time
                predicted_price = current_price * (1 + daily_impact)
                predictions.append(round(predicted_price, 2))
            
            # Calculate predicted change percent for consistency
            if predictions:
                avg_prediction = sum(predictions) / len(predictions)
                predicted_change_percent = ((avg_prediction - current_price) / current_price) * 100
            else:
                predicted_change_percent = total_impact * 100
            
            # Calculate confidence
            if sentiments and len(sentiments) > 0:
                sentiment_std = (sum((s - avg_sentiment) ** 2 for s in sentiments) / len(sentiments)) ** 0.5
            else:
                sentiment_std = 0
            article_confidence = min((len(sentiments) / 20) * 100, 100)
            consistency_confidence = max(0, (1 - sentiment_std) * 100)
            volatility_confidence = max(0, 100 - (volatility * 8))
            
            confidence = (article_confidence * 0.4 + consistency_confidence * 0.3 + volatility_confidence * 0.3)
            confidence = max(40, min(95, confidence))
            
            # Convert prices to INR if foreign stock
            current_price_inr = convert_price_to_inr(current_price, self.symbol)
            predictions_inr = convert_prices_array_to_inr(predictions, self.symbol)
            
            # Create comprehensive sentiment analysis combining news and performance
            sentiment_indicators = []
            indicator_weights = []
            
            # News sentiment indicators
            if sentiments:
                # News sentiment (weighted by number of articles)
                news_weight = min(len(sentiments) / 20, 1.0) * 0.4  # Max 40% weight
                if avg_sentiment > 0.1:
                    sentiment_indicators.append('positive')
                    indicator_weights.append(news_weight)
                elif avg_sentiment < -0.1:
                    sentiment_indicators.append('negative')
                    indicator_weights.append(news_weight)
                else:
                    sentiment_indicators.append('neutral')
                    indicator_weights.append(news_weight)
            
            # Performance indicators (same as performance-based analysis)
            # Indicator 1: Recent price performance (1 week) - Weight: 0.15
            if price_change_1w > 2:
                sentiment_indicators.append('positive')
                indicator_weights.append(0.15)
            elif price_change_1w < -2:
                sentiment_indicators.append('negative')
                indicator_weights.append(0.15)
            else:
                sentiment_indicators.append('neutral')
                indicator_weights.append(0.15)
            
            # Indicator 2: Recent price performance (1 month) - Weight: 0.15
            if price_change_1m > 5:
                sentiment_indicators.append('positive')
                indicator_weights.append(0.15)
            elif price_change_1m < -5:
                sentiment_indicators.append('negative')
                indicator_weights.append(0.15)
            else:
                sentiment_indicators.append('neutral')
                indicator_weights.append(0.15)
            
            # Indicator 3: Volatility analysis - Weight: 0.10
            if volatility < 0.02:
                sentiment_indicators.append('neutral')
                indicator_weights.append(0.10)
            elif volatility > 0.05:
                if weighted_performance > 0:
                    sentiment_indicators.append('positive')
                    indicator_weights.append(0.10)
                else:
                    sentiment_indicators.append('negative')
                    indicator_weights.append(0.10)
            else:
                sentiment_indicators.append('neutral')
                indicator_weights.append(0.10)
            
            # Indicator 4: Momentum trend - Weight: 0.10
            recent_prices = hist['Close'].tail(10)
            # Avoid division by zero
            start_price = recent_prices.iloc[0]
            if start_price > 0:
                momentum = (recent_prices.iloc[-1] - start_price) / start_price * 100
            else:
                momentum = 0
            if momentum > 1:
                sentiment_indicators.append('positive')
                indicator_weights.append(0.10)
            elif momentum < -1:
                sentiment_indicators.append('negative')
                indicator_weights.append(0.10)
            else:
                sentiment_indicators.append('neutral')
                indicator_weights.append(0.10)
            
            # Calculate weighted sentiment scores
            positive_score = 0
            negative_score = 0
            neutral_score = 0
            
            for i, indicator in enumerate(sentiment_indicators):
                weight = indicator_weights[i]
                if indicator == 'positive':
                    positive_score += weight
                elif indicator == 'negative':
                    negative_score += weight
                else:
                    neutral_score += weight
            
            # Count indicators for display
            positive_count = sentiment_indicators.count('positive')
            negative_count = sentiment_indicators.count('negative')
            neutral_count = sentiment_indicators.count('neutral')
            total_indicators = len(sentiment_indicators)
            
            # Determine overall sentiment based on weighted scores
            if positive_score > negative_score and positive_score > neutral_score:
                overall_sentiment_label = 'Positive'
            elif negative_score > positive_score and negative_score > neutral_score:
                overall_sentiment_label = 'Negative'
            else:
                overall_sentiment_label = 'Neutral'
            
            # Calculate sentiment score (0-100 scale)
            sentiment_score = (positive_score - negative_score) * 100 + 50
            sentiment_score = max(0, min(100, sentiment_score))
            
            # Generate predictions based on the SAME sentiment logic to ensure consistency
            # Convert sentiment score to impact factor (-1 to 1 range)
            sentiment_impact_factor = (sentiment_score - 50) / 50  # -1 to 1
            sentiment_impact = sentiment_impact_factor * 0.08  # Max 8% impact
            momentum_impact = (weighted_performance / 100) * 0.02
            total_impact = sentiment_impact + momentum_impact
            predicted_change_percent = total_impact * 100
            
            for day in range(1, 15):
                daily_impact = total_impact * (1 - (day * 0.04))
                predicted_price = current_price * (1 + daily_impact)
                predictions.append(round(predicted_price, 2))
            
            return {
                'success': True,
                'overall_sentiment': overall_sentiment_label,
                'sentiment_score': round(sentiment_score, 0),
                'polarity': round(final_sentiment, 3),
                'positive_count': positive_count,
                'negative_count': negative_count,
                'neutral_count': neutral_count,
                'total_indicators': total_indicators,
                'total_articles': len(sentiments),
                'confidence': round(confidence, 2),
                'current_price': round(current_price_inr, 2),
                'predicted_change_percent': round(predicted_change_percent, 2),
                'predictions': [round(p, 2) for p in predictions_inr],
                'articles': articles_data[:10],
                'currency': 'INR',
                'performance_1w': round(price_change_1w, 2),
                'performance_1m': round(price_change_1m, 2),
                'performance_3m': round(price_change_3m, 2),
                'volatility': round(volatility, 2),
                'sentiment_indicators': sentiment_indicators  # For debugging
            }
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {
                'success': False,
                'message': str(e)
            }
