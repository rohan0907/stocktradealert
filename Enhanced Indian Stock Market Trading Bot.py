# Enhanced Indian Stock Market Trading Bot with News and Whale Trading Focus
# Features:
# - Focuses on news-driven and institutional trading alerts only
# - Market hours detection (no alerts when market is closed)
# - Precise entry/exit prices with take profit and stop loss
# - News categorization by impact level (Low/Medium/High)
# - Integration with IndianAPI.in stock market API
# - Rich alert messages with emojis
# - Command-based interaction for user requests

import os
import logging
import time
import asyncio
import json
import random
from datetime import datetime, timedelta, time as dt_time
import requests
import pandas as pd
import numpy as np
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration (replace with your actual tokens)
TELEGRAM_TOKEN = "7758199040:AAGaYwxPLAsAioJLncJx76Qz6e6PeXZl0GA"
TELEGRAM_CHAT_ID = "1500589101"  # The chat ID where alerts will be sent
INDIAN_API_KEY = "sk-live-G5Wk78i1kbFjhTLQbeWSGTFUYuAu4wBeMfZzrW3m"  # Replace with your IndianAPI.in API key

# Initialize sentiment analyzer
sentiment_analyzer = SentimentIntensityAnalyzer()

# Store processed news to avoid duplicates
processed_news = set()

# Headers for web scraping
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Market hours configuration for Indian markets
MARKET_OPEN_TIME = dt_time(9, 15)  # 9:15 AM
MARKET_CLOSE_TIME = dt_time(15, 30)  # 3:30 PM
MARKET_DAYS = [0, 1, 2, 3, 4]  # Monday to Friday (0-4)

def is_market_open():
    """Check if the market is currently open"""
    now = datetime.now()
    current_time = now.time()
    current_day = now.weekday()
    
    # Check if it's a weekday and within market hours
    return (current_day in MARKET_DAYS and 
            MARKET_OPEN_TIME <= current_time <= MARKET_CLOSE_TIME)

def analyze_sentiment(text):
    """Analyze the sentiment of news text using VADER"""
    sentiment_dict = sentiment_analyzer.polarity_scores(text)
    compound_score = sentiment_dict['compound']
    
    if compound_score >= 0.05:
        return "Positive"
    elif compound_score <= -0.05:
        return "Negative"
    else:
        return "Neutral"

def determine_news_impact(headline, sentiment, volume_change=None):
    """Determine the impact level of news (Low/Medium/High)"""
    # Keywords suggesting high impact news
    high_impact_keywords = [
        "merger", "acquisition", "takeover", "buyout", "bankrupt", 
        "fraud", "scandal", "investigation", "lawsuit", "breakout", 
        "breakthrough", "fda approval", "patent granted", "major contract",
        "quarterly results", "profit warning", "guidance raised", "dividend",
        "stock split", "massive", "huge", "significant", "crisis"
    ]
    
    # Calculate base impact score
    impact_score = 0
    
    # Check for high impact keywords
    for keyword in high_impact_keywords:
        if keyword.lower() in headline.lower():
            impact_score += 2
    
    # Sentiment intensity affects impact
    sentiment_magnitude = abs(sentiment_analyzer.polarity_scores(headline)['compound'])
    impact_score += sentiment_magnitude * 3
    
    # Volume change affects impact (if provided)
    if volume_change:
        if volume_change > 100:  # >100% volume increase
            impact_score += 3
        elif volume_change > 50:  # >50% volume increase
            impact_score += 2
        elif volume_change > 20:  # >20% volume increase
            impact_score += 1
    
    # Determine impact level based on score
    if impact_score >= 4:
        return "High"
    elif impact_score >= 2:
        return "Medium"
    else:
        return "Low"

def determine_action(sentiment, volume_change=None, whale_activity=None):
    """Determine trading action based on sentiment, volume and whale activity"""
    # Strong whale activity is the most important signal
    if whale_activity:
        if whale_activity == "buying":
            return "BUY", "Institutional buying detected"
        elif whale_activity == "selling":
            return "SELL", "Institutional selling detected"
    
    # Significant volume change with matching sentiment
    if volume_change:
        if volume_change > 50 and sentiment == "Positive":
            return "BUY", f"Unusual volume (+{volume_change}%) with positive sentiment"
        elif volume_change > 50 and sentiment == "Negative":
            return "SELL", f"Unusual volume (+{volume_change}%) with negative sentiment"
    
    # Only use pure sentiment signals if they're strong
    if sentiment == "Positive":
        return "BUY", "Strong positive sentiment in news"
    elif sentiment == "Negative":
        return "SELL", "Strong negative sentiment in news"
    
    return "HOLD", "No clear signal"

def fetch_stock_data_from_indian_api(symbol):
    """Fetch stock data from IndianAPI.in"""
    try:
        # Endpoint for stock quote
        url = f"https://indianapi.in/api/v1/stock/{symbol}"
        
        # Add your API key to headers
        api_headers = {
            'Authorization': f'Bearer {INDIAN_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(url, headers=api_headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            logger.error(f"Error fetching data from IndianAPI: {response.status_code}")
            return None
    
    except Exception as e:
        logger.error(f"Exception fetching data from IndianAPI: {str(e)}")
        return None

def fetch_market_news_from_indian_api():
    """Fetch latest market news from IndianAPI.in"""
    try:
        # Endpoint for market news
        url = "https://indianapi.in/api/v1/news/market"
        
        # Add your API key to headers
        api_headers = {
            'Authorization': f'Bearer {INDIAN_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(url, headers=api_headers, timeout=10)
        
        if response.status_code == 200:
            news_items = response.json().get('data', [])
            return news_items
        else:
            logger.error(f"Error fetching news from IndianAPI: {response.status_code}")
            return []
    
    except Exception as e:
        logger.error(f"Exception fetching news from IndianAPI: {str(e)}")
        return []

def fetch_institutional_activity():
    """Fetch institutional/whale trading activity from IndianAPI.in"""
    try:
        # Endpoint for institutional activity
        url = "https://indianapi.in/api/v1/institutions/activity"
        
        # Add your API key to headers
        api_headers = {
            'Authorization': f'Bearer {INDIAN_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(url, headers=api_headers, timeout=10)
        
        if response.status_code == 200:
            activity_data = response.json().get('data', [])
            return activity_data
        else:
            logger.error(f"Error fetching institutional activity from IndianAPI: {response.status_code}")
            return []
    
    except Exception as e:
        logger.error(f"Exception fetching institutional activity from IndianAPI: {str(e)}")
        return []

def calculate_price_targets(current_price, action, volatility=None):
    """Calculate precise entry, exit, target and stop-loss based on stock volatility"""
    if not volatility:
        # Default volatility if not provided
        volatility = 0.02  # 2%
    
    if action == "BUY":
        entry_price = current_price
        stop_loss = round(current_price * (1 - volatility), 2)
        target1 = round(current_price * (1 + volatility * 1.5), 2)
        target2 = round(current_price * (1 + volatility * 2.5), 2)
        target3 = round(current_price * (1 + volatility * 3.5), 2)
    else:  # SELL
        entry_price = current_price
        stop_loss = round(current_price * (1 + volatility), 2)
        target1 = round(current_price * (1 - volatility * 1.5), 2)
        target2 = round(current_price * (1 - volatility * 2.5), 2)
        target3 = round(current_price * (1 - volatility * 3.5), 2)
    
    return {
        'entry_price': entry_price,
        'stop_loss': stop_loss,
        'target1': target1,
        'target2': target2,
        'target3': target3
    }

def fetch_stock_volatility(symbol):
    """Calculate stock volatility using IndianAPI.in historical data"""
    try:
        # Endpoint for historical data
        url = f"https://indianapi.in/api/v1/stock/{symbol}/historical"
        
        # Add your API key to headers
        api_headers = {
            'Authorization': f'Bearer {INDIAN_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        # Parameters for last 20 days
        params = {
            'interval': 'daily',
            'period': '20d'
        }
        
        response = requests.get(url, headers=api_headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json().get('data', [])
            
            if data:
                # Extract closing prices
                closes = [float(day['close']) for day in data]
                
                # Calculate daily returns
                returns = [(closes[i] / closes[i-1]) - 1 for i in range(1, len(closes))]
                
                # Calculate volatility as standard deviation of returns
                volatility = np.std(returns)
                
                # Add a minimum volatility floor
                return max(volatility, 0.015)  # Minimum 1.5% volatility
            else:
                return 0.02  # Default 2% if no data
        else:
            logger.error(f"Error fetching historical data from IndianAPI: {response.status_code}")
            return 0.02  # Default 2% if API error
    
    except Exception as e:
        logger.error(f"Exception calculating volatility: {str(e)}")
        return 0.02  # Default 2% if exception

def format_alert(news_item):
    """Format alert message for Telegram with enhanced emojis"""
    # Use current time for the alert
    current_timestamp = datetime.now()
    timestamp_str = current_timestamp.strftime("%d-%b-%Y %H:%M")
    
    # Use emojis based on sentiment and action
    if news_item['action'] == "BUY":
        action_emoji = "🟢 BUY"
    elif news_item['action'] == "SELL":
        action_emoji = "🔴 SELL"
    else:
        action_emoji = "⚪ HOLD"
        
    if news_item['sentiment'] == "Positive":
        sentiment_emoji = "😀 Positive"
    elif news_item['sentiment'] == "Negative":
        sentiment_emoji = "😟 Negative"
    else:
        sentiment_emoji = "😐 Neutral"
    
    # Impact level emoji
    if news_item['impact'] == "High":
        impact_emoji = "🔥 High"
    elif news_item['impact'] == "Medium":
        impact_emoji = "⚡ Medium"
    else:
        impact_emoji = "💧 Low"
    
    # Format price targets section
    if 'price_targets' in news_item:
        targets = news_item['price_targets']
        
        if news_item['action'] == "BUY":
            price_section = f"""
💰 *Entry:* ₹{targets['entry_price']}
🎯 *Targets:*
  T1: ₹{targets['target1']} (+{round((targets['target1']/targets['entry_price']-1)*100, 1)}%)
  T2: ₹{targets['target2']} (+{round((targets['target2']/targets['entry_price']-1)*100, 1)}%)
  T3: ₹{targets['target3']} (+{round((targets['target3']/targets['entry_price']-1)*100, 1)}%)
🛑 *Stop Loss:* ₹{targets['stop_loss']} (-{round((1-targets['stop_loss']/targets['entry_price'])*100, 1)}%)"""
        else:  # SELL
            price_section = f"""
💰 *Entry:* ₹{targets['entry_price']}
🎯 *Targets:*
  T1: ₹{targets['target1']} (-{round((1-targets['target1']/targets['entry_price'])*100, 1)}%)
  T2: ₹{targets['target2']} (-{round((1-targets['target2']/targets['entry_price'])*100, 1)}%)
  T3: ₹{targets['target3']} (-{round((1-targets['target3']/targets['entry_price'])*100, 1)}%)
🛑 *Stop Loss:* ₹{targets['stop_loss']} (+{round((targets['stop_loss']/targets['entry_price']-1)*100, 1)}%)"""
    else:
        price_section = ""
        
    # Format reason section
    reason_section = f"\n💡 *Reason:* {news_item['reason']}" if 'reason' in news_item else ""
    
    # Format the complete message
    message = f"""
🔔 *TRADING ALERT* 🔔

*{news_item['symbol']}* ({news_item.get('sector', 'N/A')})

📰 *News:* {news_item['headline']}

📊 *Sentiment:* {sentiment_emoji}
⚡ *Impact:* {impact_emoji}
👉 *Action:* {action_emoji}
⏰ *Time:* {timestamp_str}{reason_section}{price_section}

🔗 [Read More]({news_item.get('url', '')})
"""
    return message

async def send_telegram_alert(bot, message):
    """Send alert message to Telegram"""
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message,
            parse_mode='Markdown',
            disable_web_page_preview=True
        )
        logger.info("Alert sent successfully")
        return True
    except Exception as e:
        logger.error(f"Error sending Telegram message: {str(e)}")
        return False

async def check_news_and_send_alerts(application):
    """Main function to check for news and send alerts"""
    logger.info("Checking for new stock alerts...")
    
    # Check if market is open
    if not is_market_open():
        logger.info("Market is closed. No alerts will be sent.")
        return
    
    # Get market news from Indian API
    news_items = fetch_market_news_from_indian_api()
    
    # Get institutional activity
    institutional_activity = fetch_institutional_activity()
    
    # Process actionable news
    actionable_news = []
    
    # Process news items
    for news in news_items:
        # Skip if already processed
        news_id = f"{news.get('headline', '')}_{news.get('published_at', '')}"
        if news_id in processed_news:
            continue
        
        # Add to processed news
        processed_news.add(news_id)
        
        # Analyze sentiment
        headline = news.get('headline', '')
        sentiment = analyze_sentiment(headline)
        
        # Find if any symbol is associated with this news
        for symbol in news.get('symbols', []):
            # Get stock data
            stock_data = fetch_stock_data_from_indian_api(symbol)
            
            if stock_data:
                # Check for volume spikes
                volume_change = stock_data.get('volume_change_percent', None)
                
                # Check if this stock has institutional activity
                whale_activity = None
                for activity in institutional_activity:
                    if activity.get('symbol') == symbol:
                        if activity.get('net_position', 0) > 0:
                            whale_activity = "buying"
                        elif activity.get('net_position', 0) < 0:
                            whale_activity = "selling"
                
                # Determine action
                action, reason = determine_action(sentiment, volume_change, whale_activity)
                
                # Only include BUY or SELL signals
                if action in ["BUY", "SELL"]:
                    # Calculate impact level
                    impact = determine_news_impact(headline, sentiment, volume_change)
                    
                    # Create news item
                    news_item = {
                        'symbol': symbol,
                        'sector': stock_data.get('sector', 'N/A'),
                        'headline': headline,
                        'sentiment': sentiment,
                        'impact': impact,
                        'action': action,
                        'reason': reason,
                        'url': news.get('url', '')
                    }
                    
                    # Calculate volatility for price targets
                    volatility = fetch_stock_volatility(symbol)
                    
                    # Calculate price targets
                    current_price = stock_data.get('last_price')
                    if current_price:
                        price_targets = calculate_price_targets(
                            current_price, 
                            action, 
                            volatility
                        )
                        news_item['price_targets'] = price_targets
                    
                    actionable_news.append(news_item)
    
    # Also process institutional activity without news
    for activity in institutional_activity:
        symbol = activity.get('symbol')
        
        # Skip if we already have this symbol in actionable news
        if any(news['symbol'] == symbol for news in actionable_news):
            continue
        
        if activity.get('net_position', 0) != 0:  # Significant position
            # Get stock data
            stock_data = fetch_stock_data_from_indian_api(symbol)
            
            if stock_data:
                # Determine action
                if activity.get('net_position', 0) > 0:
                    action = "BUY"
                    reason = f"Institutional buying of {activity.get('buy_quantity', 0)} shares"
                else:
                    action = "SELL"
                    reason = f"Institutional selling of {activity.get('sell_quantity', 0)} shares"
                
                # Create news item
                news_item = {
                    'symbol': symbol,
                    'sector': stock_data.get('sector', 'N/A'),
                    'headline': f"Institutional {'buying' if action == 'BUY' else 'selling'} activity detected",
                    'sentiment': "Positive" if action == "BUY" else "Negative",
                    'impact': "High",  # Institutional activity has high impact
                    'action': action,
                    'reason': reason
                }
                
                # Calculate volatility for price targets
                volatility = fetch_stock_volatility(symbol)
                
                # Calculate price targets
                current_price = stock_data.get('last_price')
                if current_price:
                    price_targets = calculate_price_targets(
                        current_price, 
                        action, 
                        volatility
                    )
                    news_item['price_targets'] = price_targets
                
                actionable_news.append(news_item)
    
    # Sort by impact level
    actionable_news.sort(key=lambda x: ["Low", "Medium", "High"].index(x['impact']), reverse=True)
    
    if actionable_news:
        logger.info(f"Found {len(actionable_news)} actionable trading signals")
        
        for news_item in actionable_news:
            alert_message = format_alert(news_item)
            await send_telegram_alert(application.bot, alert_message)
            # Add a small delay between messages to avoid rate limiting
            await asyncio.sleep(1)
    else:
        logger.info("No actionable trading signals found")

async def daily_market_outlook(application):
    """Generate and send a daily market outlook"""
    # Check if market is open today or will open today
    now = datetime.now()
    current_day = now.weekday()
    
    if current_day not in MARKET_DAYS:
        logger.info("Market closed today. No outlook will be sent.")
        return
    
    logger.info("Generating daily market outlook...")
    
    try:
        # Get market data from IndianAPI
        url = "https://indianapi.in/api/v1/market/indices"
        
        # Add your API key to headers
        api_headers = {
            'Authorization': f'Bearer {INDIAN_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(url, headers=api_headers, timeout=10)
        
        if response.status_code == 200:
            indices_data = response.json().get('data', [])
        else:
            logger.error(f"Failed to get indices data: {response.status_code}")
            indices_data = []
            
        # Get sector performance
        sector_url = "https://indianapi.in/api/v1/market/sectors"
        sector_response = requests.get(sector_url, headers=api_headers, timeout=10)
        
        if sector_response.status_code == 200:
            sector_data = sector_response.json().get('data', [])
        else:
            logger.error(f"Failed to get sector data: {sector_response.status_code}")
            sector_data = []
        
        # Get market sentiment and outlook
        sentiment_url = "https://indianapi.in/api/v1/market/sentiment"
        sentiment_response = requests.get(sentiment_url, headers=api_headers, timeout=10)
        
        if sentiment_response.status_code == 200:
            sentiment_data = sentiment_response.json()
            market_sentiment = sentiment_data.get('overall_sentiment', 'Neutral')
            market_outlook = sentiment_data.get('outlook', 'Neutral')
        else:
            logger.error(f"Failed to get sentiment data: {sentiment_response.status_code}")
            market_sentiment = "Neutral"
            market_outlook = "Neutral"
            
        # Format the message
        current_date = datetime.now().strftime("%d-%b-%Y")
        message = f"""
🔮 *DAILY MARKET OUTLOOK* 🔮

📅 *Date:* {current_date}

"""

        # Add index performance if available
        if indices_data:
            message += "📈 *Index Performance:*\n"
            for index in indices_data[:3]:  # Limit to top 3 indices
                name = index.get('name', 'Unknown')
                change = index.get('change_percent', 0)
                icon = '🟢' if change > 0 else '🔴'
                message += f"• {name}: {'+' if change > 0 else ''}{change:.2f}% {icon}\n"
            
            message += "\n"
        
        # Add sector performance if available
        if sector_data:
            # Sort sectors by performance
            sector_data.sort(key=lambda x: x.get('change_percent', 0), reverse=True)
            
            message += "📊 *Sector Performance:*\n"
            message += "*Top Performing Sectors:*\n"
            for sector in sector_data[:3]:  # Top 3 sectors
                name = sector.get('name', 'Unknown')
                change = sector.get('change_percent', 0)
                icon = '🟢' if change > 0 else '🔴'
                message += f"• {name}: {'+' if change > 0 else ''}{change:.2f}% {icon}\n"
            
            message += "\n*Underperforming Sectors:*\n"
            for sector in sector_data[-3:]:  # Bottom 3 sectors
                name = sector.get('name', 'Unknown')
                change = sector.get('change_percent', 0)
                icon = '🟢' if change > 0 else '🔴'
                message += f"• {name}: {change:.2f}% {icon}\n"
                
            message += "\n"
        
        # Add market sentiment and outlook
        message += f"🧭 *Market Sentiment:* {market_sentiment}\n"
        message += f"🔍 *Market Outlook:* {market_outlook}\n\n"
        
        # Add institutional activity summary
        inst_activity = fetch_institutional_activity()
        if inst_activity:
            # Calculate net institutional activity
            net_buy = sum(1 for item in inst_activity if item.get('net_position', 0) > 0)
            net_sell = sum(1 for item in inst_activity if item.get('net_position', 0) < 0)
            
            message += "🐋 *Institutional Activity:*\n"
            message += f"• Net Buying: {net_buy} stocks\n"
            message += f"• Net Selling: {net_sell} stocks\n\n"
            
            # Add some of the top institutional activity
            message += "*Notable Institutional Activity:*\n"
            
            # Sort by absolute net position
            inst_activity.sort(key=lambda x: abs(x.get('net_position', 0)), reverse=True)
            
            for activity in inst_activity[:3]:  # Top 3 activities
                symbol = activity.get('symbol', 'Unknown')
                position = activity.get('net_position', 0)
                icon = '🟢' if position > 0 else '🔴'
                action = "buying" if position > 0 else "selling"
                message += f"• {symbol}: Institutional {action} {icon}\n"
                
            message += "\n"
        
        # Add disclaimer
        message += "⚠️ *Disclaimer:* This outlook is for informational purposes only. Always conduct your own research before making trading decisions."
        
        # Send the outlook
        await send_telegram_alert(application.bot, message)
        logger.info("Daily market outlook sent")
        
    except Exception as e:
        logger.error(f"Error generating daily market outlook: {str(e)}")

async def run_end_of_day_summary(application):
    """Generate and send an end-of-day market summary"""
    # Check if market was open today
    now = datetime.now()
    current_day = now.weekday()
    
    if current_day not in MARKET_DAYS:
        logger.info("Market was closed today. No summary will be sent.")
        return
    
    logger.info("Generating end-of-day market summary...")
    
    try:
        # Get market data from IndianAPI
        url = "https://indianapi.in/api/v1/market/indices"
        
        # Add your API key to headers
        api_headers = {
            'Authorization': f'Bearer {INDIAN_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(url, headers=api_headers, timeout=10)
        
        if response.status_code == 200:
            indices_data = response.json().get('data', [])
        else:
            logger.error(f"Failed to get indices data: {response.status_code}")
            indices_data = []
        
        # Format the message
        current_date = datetime.now().strftime("%d-%b-%Y")
        message = f"""
📊 *END OF DAY SUMMARY* 📊

📅 *Date:* {current_date}

"""
        # Add index performance if available
        if indices_data:
            message += "📈 *Index Performance:*\n"
            for index in indices_data[:5]:  # Top 5 indices
                name = index.get('name', 'Unknown')
                close = index.get('close', 'N/A')
                change = index.get('change_percent', 0)
                icon = '🟢' if change > 0 else '🔴' if change < 0 else '⚪'
                message += f"• {name}: {close} ({'+' if change > 0 else ''}{change:.2f}%) {icon}\n"
            
            message += "\n"
        
        # Get top gainers and losers
        gainers_url = "https://indianapi.in/api/v1/market/top-gainers"
        losers_url = "https://indianapi.in/api/v1/market/top-losers"
        
        gainers_response = requests.get(gainers_url, headers=api_headers, timeout=10)
        losers_response = requests.get(losers_url, headers=api_headers, timeout=10)
        
        if gainers_response.status_code == 200:
            gainers_data = gainers_response.json().get('data', [])
            
            message += "🟢 *Top Gainers:*\n"
            for gainer in gainers_data[:5]:  # Top 5 gainers
                symbol = gainer.get('symbol', 'Unknown')
                change = gainer.get('change_percent', 0)
                price = gainer.get('last_price', 'N/A')
                message += f"• {symbol}: ₹{price} (+{change:.2f}%)\n"
            
            message += "\n"
        
        if losers_response.status_code == 200:
            losers_data = losers_response.json().get('data', [])
            
            message += "🔴 *Top Losers:*\n"
            for loser in losers_data[:5]:  # Top 5 losers
                symbol = loser.get('symbol', 'Unknown')
                change = loser.get('change_percent', 0)
                price = loser.get('last_price', 'N/A')
                message += f"• {symbol}: ₹{price} ({change:.2f}%)\n"
            
            message += "\n"
        
        # Get sector performance for the day
        sector_url = "https://indianapi.in/api/v1/market/sectors"
        sector_response = requests.get(sector_url, headers=api_headers, timeout=10)
        
        if sector_response.status_code == 200:
            sector_data = sector_response.json().get('data', [])
            
            # Sort sectors by performance
            sector_data.sort(key=lambda x: x.get('change_percent', 0), reverse=True)
            
            message += "🔍 *Sector Performance:*\n"
            
            # Top 3 sectors
            for sector in sector_data[:3]:
                name = sector.get('name', 'Unknown')
                change = sector.get('change_percent', 0)
                icon = '🟢' if change > 0 else '🔴'
                message += f"• {name}: {'+' if change > 0 else ''}{change:.2f}% {icon}\n"
            
            # Bottom 3 sectors
            for sector in sector_data[-3:]:
                name = sector.get('name', 'Unknown')
                change = sector.get('change_percent', 0)
                icon = '🟢' if change > 0 else '🔴'
                message += f"• {name}: {change:.2f}% {icon}\n"
                
            message += "\n"
        
        # Add institutional activity summary
        inst_activity = fetch_institutional_activity()
        if inst_activity:
            # Calculate net institutional activity
            net_buy = sum(1 for item in inst_activity if item.get('net_position', 0) > 0)
            net_sell = sum(1 for item in inst_activity if item.get('net_position', 0) < 0)
            
            message += "🐋 *Institutional Activity:*\n"
            message += f"• Net Buying: {net_buy} stocks\n"
            message += f"• Net Selling: {net_sell} stocks\n\n"
        
        # Get market breadth data
        breadth_url = "https://indianapi.in/api/v1/market/breadth"
        breadth_response = requests.get(breadth_url, headers=api_headers, timeout=10)
        
        if breadth_response.status_code == 200:
            breadth_data = breadth_response.json()
            advancers = breadth_data.get('advancers', 0)
            decliners = breadth_data.get('decliners', 0)
            unchanged = breadth_data.get('unchanged', 0)
            
            message += "📊 *Market Breadth:*\n"
            message += f"• Advancing Stocks: {advancers}\n"
            message += f"• Declining Stocks: {decliners}\n"
            message += f"• Unchanged: {unchanged}\n\n"
        
        # Add volume information
        volume_url = "https://indianapi.in/api/v1/market/volume"
        volume_response = requests.get(volume_url, headers=api_headers, timeout=10)
        
        if volume_response.status_code == 200:
            volume_data = volume_response.json()
            total_volume = volume_data.get('total_volume', 0)
            avg_volume = volume_data.get('average_volume', 0)
            
            # Format volume in crores
            total_volume_cr = total_volume / 10000000  # Convert to crores
            
            message += "💹 *Market Volume:*\n"
            message += f"• Total Volume: ₹{total_volume_cr:.2f} Cr\n"
            
            # Compare with average
            volume_ratio = (total_volume / avg_volume) if avg_volume > 0 else 1
            
            if volume_ratio > 1.2:
                message += f"• Volume: {volume_ratio:.2f}x higher than average 📈\n\n"
            elif volume_ratio < 0.8:
                message += f"• Volume: {volume_ratio:.2f}x lower than average 📉\n\n"
            else:
                message += f"• Volume: Near average ↔️\n\n"
        
        # Add next day outlook
        message += "🔮 *Next Day Outlook:*\n"
        
        # Get sentiment data for outlook
        sentiment_url = "https://indianapi.in/api/v1/market/sentiment"
        sentiment_response = requests.get(sentiment_url, headers=api_headers, timeout=10)
        
        if sentiment_response.status_code == 200:
            sentiment_data = sentiment_response.json()
            market_sentiment = sentiment_data.get('overall_sentiment', 'Neutral')
            market_outlook = sentiment_data.get('outlook', 'Neutral')
            
            # Add sentiment-based outlook
            if market_sentiment == "Positive":
                message += "• Market sentiment is positive, suggesting potential continuation of upward momentum.\n"
            elif market_sentiment == "Negative":
                message += "• Market sentiment is negative, suggesting caution for tomorrow's session.\n"
            else:
                message += "• Market sentiment is mixed, suggesting a range-bound session tomorrow.\n"
        else:
            # Default outlook based on today's performance
            if indices_data and indices_data[0].get('change_percent', 0) > 0:
                message += "• Markets closed positive today. Watch for follow-through buying tomorrow.\n"
            elif indices_data and indices_data[0].get('change_percent', 0) < 0:
                message += "• Markets closed negative today. Watch for potential support levels tomorrow.\n"
            else:
                message += "• Markets were indecisive today. Look for breakout signals tomorrow.\n"
        
        # Add disclaimer
        message += "\n⚠️ *Disclaimer:* This summary is for informational purposes only. Always conduct your own research before making trading decisions."
        
        # Send the summary
        await send_telegram_alert(application.bot, message)
        logger.info("End of day summary sent")
        
    except Exception as e:
        logger.error(f"Error generating end of day summary: {str(e)}")

# Telegram bot command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message when the command /start is issued."""
    welcome_message = """
🚀 *Welcome to Indian Stock Market Alert Bot* 🚀

This bot provides real-time Indian stock market alerts based on:
- Breaking news with sentiment analysis
- Institutional (whale) trading activity
- Volume anomalies and price action

*Available Commands:*
/start - Show this welcome message
/help - Get help on bot usage
/status - Check market and bot status
/stocks - List stocks being tracked
/watchlist - Manage your watchlist
/performance - View bot performance stats

The bot automatically sends alerts during market hours (9:15 AM - 3:30 PM, Mon-Fri) when significant trading opportunities are detected.

_Stay informed, trade smarter!_ 📈
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help information when the command /help is issued."""
    help_message = """
📚 *Indian Stock Market Alert Bot - Help* 📚

*Bot Overview:*
This bot analyzes Indian stocks for trading opportunities based on news sentiment, institutional activity, and technical indicators.

*Commands:*
/start - Start the bot and receive welcome message
/help - Display this help message
/status - Check market status and bot operation
/stocks [symbol] - Get details for a specific stock or list all tracked stocks
/watchlist - View your current watchlist
/watchlist add [symbol] - Add a stock to your watchlist
/watchlist remove [symbol] - Remove a stock from your watchlist
/performance - View the bot's alert performance statistics

*Alert Types:*
📰 *News-Based Alerts* - Trading signals based on market news and sentiment analysis
🐋 *Institutional Activity* - Alerts when significant institutional buying or selling is detected
📊 *Technical Alerts* - Signals based on volume spikes and price action

*Alert Format:*
Each alert includes:
- Stock symbol and sector
- News headline or event trigger
- Sentiment and impact analysis
- Recommended action (BUY/SELL)
- Entry price, targets and stop loss levels
- Reasoning behind the alert

*Market Hours:*
The bot operates during Indian market hours (9:15 AM - 3:30 PM, Mon-Fri).

*Disclaimer:*
Trading alerts are for informational purposes only. Make trading decisions based on your own research and risk tolerance.
"""
    await update.message.reply_text(help_message, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check market status and bot operation when the command /status is issued."""
    # Check if market is open
    market_status = "🟢 OPEN" if is_market_open() else "🔴 CLOSED"
    current_time = datetime.now().strftime("%d-%b-%Y %H:%M:%S")
    
    # Get market indices status
    try:
        # Endpoint for market indices
        url = "https://indianapi.in/api/v1/market/indices"
        
        # Add your API key to headers
        api_headers = {
            'Authorization': f'Bearer {INDIAN_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(url, headers=api_headers, timeout=10)
        
        if response.status_code == 200:
            indices_data = response.json().get('data', [])
            
            # Format indices information
            indices_info = ""
            for index in indices_data[:3]:  # Top 3 indices
                name = index.get('name', 'Unknown')
                change = index.get('change_percent', 0)
                icon = '🟢' if change > 0 else '🔴' if change < 0 else '⚪'
                indices_info += f"• {name}: {'+' if change > 0 else ''}{change:.2f}% {icon}\n"
        else:
            indices_info = "Unable to fetch indices data\n"
            
    except Exception as e:
        logger.error(f"Error fetching indices status: {str(e)}")
        indices_info = "Error fetching indices data\n"
    
    # Bot operational status
    bot_status = "🟢 OPERATIONAL"
    
    # Format the complete status message
    status_message = f"""
📊 *BOT STATUS* 📊

⏰ *Current Time:* {current_time}
🏛️ *Market Status:* {market_status}

📈 *Major Indices:*
{indices_info}
🤖 *Bot Status:* {bot_status}

*Next Market Open:*
"""
    
    # Calculate next market open time
    now = datetime.now()
    current_day = now.weekday()
    current_time = now.time()
    
    if current_day in MARKET_DAYS and current_time < MARKET_OPEN_TIME:
        # Market opens today
        next_open = f"Today at {MARKET_OPEN_TIME.strftime('%H:%M')}"
    elif current_day in MARKET_DAYS and current_time >= MARKET_CLOSE_TIME:
        # Market closed for today, opens tomorrow if tomorrow is a market day
        if current_day < 4:  # Not Friday
            next_open = f"Tomorrow at {MARKET_OPEN_TIME.strftime('%H:%M')}"
        else:  # Friday, next open is Monday
            next_open = f"Monday at {MARKET_OPEN_TIME.strftime('%H:%M')}"
    elif current_day in MARKET_DAYS:
        # Market is currently open
        next_open = "Market is currently open"
    else:
        # Weekend or holiday, find next market day
        days_to_add = 1
        next_day = (current_day + days_to_add) % 7
        
        while next_day not in MARKET_DAYS:
            days_to_add += 1
            next_day = (current_day + days_to_add) % 7
        
        next_market_day = {
            0: "Monday",
            1: "Tuesday",
            2: "Wednesday",
            3: "Thursday",
            4: "Friday"
        }.get(next_day)
        
        next_open = f"{next_market_day} at {MARKET_OPEN_TIME.strftime('%H:%M')}"
    
    status_message += next_open
    
    await update.message.reply_text(status_message, parse_mode='Markdown')

async def stocks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Get details for specific stocks or list tracked stocks."""
    # Check if a specific symbol was provided
    args = context.args
    
    if not args:
        # No symbol provided, list top stocks being tracked
        try:
            # Get market movers from IndianAPI
            url = "https://indianapi.in/api/v1/market/most-active"
            
            # Add your API key to headers
            api_headers = {
                'Authorization': f'Bearer {INDIAN_API_KEY}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(url, headers=api_headers, timeout=10)
            
            if response.status_code == 200:
                stocks_data = response.json().get('data', [])
                
                if not stocks_data:
                    await update.message.reply_text("No stock data available.", parse_mode='Markdown')
                    return
                
                # Format stock list message
                message = "📊 *Most Active Stocks Today* 📊\n\n"
                
                for i, stock in enumerate(stocks_data[:10], 1):  # Top 10 most active stocks
                    symbol = stock.get('symbol', 'Unknown')
                    price = stock.get('last_price', 'N/A')
                    change = stock.get('change_percent', 0)
                    volume = stock.get('volume', 0)
                    
                    # Format volume in lakhs
                    volume_lakh = volume / 100000  # Convert to lakhs
                    
                    icon = '🟢' if change > 0 else '🔴' if change < 0 else '⚪'
                    
                    message += f"{i}. *{symbol}*: ₹{price} ({'+' if change > 0 else ''}{change:.2f}%) {icon}\n"
                    message += f"   Vol: {volume_lakh:.2f} L\n"
                
                message += "\nUse /stocks [symbol] to get detailed information for a specific stock."
                
                await update.message.reply_text(message, parse_mode='Markdown')
            else:
                await update.message.reply_text(f"Error fetching stock data: {response.status_code}", parse_mode='Markdown')
        
        except Exception as e:
            logger.error(f"Error in stocks command: {str(e)}")
            await update.message.reply_text(f"Error processing request: {str(e)}", parse_mode='Markdown')
    
    else:
        # Symbol provided, get details for the specific stock
        symbol = args[0].upper()
        
        try:
            # Get stock data from IndianAPI
            stock_data = fetch_stock_data_from_indian_api(symbol)
            
            if not stock_data:
                await update.message.reply_text(f"No data found for symbol *{symbol}*. Please check the symbol and try again.", parse_mode='Markdown')
                return
            
            # Format stock detail message
            current_price = stock_data.get('last_price', 'N/A')
            change = stock_data.get('change_percent', 0)
            open_price = stock_data.get('open', 'N/A')
            high_price = stock_data.get('high', 'N/A')
            low_price = stock_data.get('low', 'N/A')
            volume = stock_data.get('volume', 0)
            volume_lakh = volume / 100000  # Convert to lakhs
            sector = stock_data.get('sector', 'N/A')
            
            # Calculate price icon
            price_icon = '🟢' if change > 0 else '🔴' if change < 0 else '⚪'
            
            # Calculate volume change
            volume_change = stock_data.get('volume_change_percent', 0)
            volume_icon = '📈' if volume_change > 20 else '📉' if volume_change < -20 else '↔️'
            
            message = f"""
📱 *{symbol} Stock Details* 📱

💰 *Price:* ₹{current_price} ({'+' if change > 0 else ''}{change:.2f}%) {price_icon}
🏢 *Sector:* {sector}

📊 *Today's Trading:*
• Open: ₹{open_price}
• High: ₹{high_price}
• Low: ₹{low_price}
• Volume: {volume_lakh:.2f} L {volume_icon}

"""
            
            # Add technical indicators if available
            if 'rsi' in stock_data or 'macd' in stock_data or 'ema_50' in stock_data:
                message += "📉 *Technical Indicators:*\n"
                
                if 'rsi' in stock_data:
                    rsi = stock_data.get('rsi')
                    rsi_status = "Overbought ⚠️" if rsi > 70 else "Oversold ⚠️" if rsi < 30 else "Neutral ↔️"
                    message += f"• RSI: {rsi:.2f} ({rsi_status})\n"
                
                if 'macd' in stock_data and 'macd_signal' in stock_data:
                    macd = stock_data.get('macd')
                    macd_signal = stock_data.get('macd_signal')
                    macd_status = "Bullish 🟢" if macd > macd_signal else "Bearish 🔴"
                    message += f"• MACD: {macd_status}\n"
                
                if 'ema_50' in stock_data and 'ema_200' in stock_data:
                    ema_50 = stock_data.get('ema_50')
                    ema_200 = stock_data.get('ema_200')
                    ema_status = "Bullish 🟢" if ema_50 > ema_200 else "Bearish 🔴"
                    message += f"• EMA: {ema_status} (50 vs 200)\n"
                
                message += "\n"
            
            # Add news for this stock if available
            news_items = fetch_market_news_from_indian_api()
            stock_news = [news for news in news_items if symbol in news.get('symbols', [])]
            
            if stock_news:
                message += "📰 *Recent News:*\n"
                
                for news in stock_news[:2]:  # Show up to 2 news items
                    headline = news.get('headline', 'N/A')
                    message += f"• {headline}\n"
                
                message += "\n"
            
            # Check for institutional activity
            inst_activity = fetch_institutional_activity()
            stock_inst_activity = [activity for activity in inst_activity if activity.get('symbol') == symbol]
            
            if stock_inst_activity:
                message += "🐋 *Institutional Activity:*\n"
                
                for activity in stock_inst_activity:
                    net_pos = activity.get('net_position', 0)
                    buy_qty = activity.get('buy_quantity', 0)
                    sell_qty = activity.get('sell_quantity', 0)
                    
                    if net_pos > 0:
                        message += f"• Net Buying: {buy_qty} shares 🟢\n"
                    else:
                        message += f"• Net Selling: {sell_qty} shares 🔴\n"
            
            await update.message.reply_text(message, parse_mode='Markdown')
        
        except Exception as e:
            logger.error(f"Error fetching stock details: {str(e)}")
            await update.message.reply_text(f"Error fetching details for {symbol}: {str(e)}", parse_mode='Markdown')

async def watchlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manage user watchlist."""
    # Check for arguments
    args = context.args
    
    if not args:
        # No arguments, show current watchlist
        # In a real implementation, this would fetch from a database
        # For this example, we'll just return a message
        message = """
👀 *Your Watchlist* 👀

Currently not implemented in this example code.
The full implementation would store user watchlists in a database.

To add stocks to watchlist: /watchlist add SYMBOL
To remove stocks: /watchlist remove SYMBOL

Example: /watchlist add RELIANCE
"""
        await update.message.reply_text(message, parse_mode='Markdown')
        return
    
    # Handle watchlist commands
    command = args[0].lower()
    
    if command == "add" and len(args) > 1:
        symbol = args[1].upper()
        # In a real implementation, add to database
        await update.message.reply_text(f"Added {symbol} to your watchlist. (Example implementation)", parse_mode='Markdown')
    
    elif command == "remove" and len(args) > 1:
        symbol = args[1].upper()
        # In a real implementation, remove from database
        await update.message.reply_text(f"Removed {symbol} from your watchlist. (Example implementation)", parse_mode='Markdown')
    
    else:
        await update.message.reply_text("Invalid watchlist command. Use /watchlist, /watchlist add SYMBOL, or /watchlist remove SYMBOL", parse_mode='Markdown')

async def performance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot performance statistics."""
    # In a real implementation, this would fetch performance data from a database
    # For this example, we'll just return sample statistics
    message = """
📊 *Bot Performance Statistics* 📊

*Last 30 Days:*
• Total Alerts Sent: 128
• Successful Signals: 72 (56.3%)
• Failed Signals: 49 (38.3%)
• Neutral/Indecisive: 7 (5.4%)

*By Alert Type:*
• News-Based: 62% success rate
• Institutional Activity: 71% success rate
• Technical Indicators: 45% success rate

*Top Performing Sectors:*
• IT: 76% success rate
• Pharma: 68% success rate
• Banking: 59% success rate

Note: Performance statistics are for demonstration purposes only.
In the full implementation, actual performance would be tracked.
"""
    await update.message.reply_text(message, parse_mode='Markdown')

# Scheduled job to check for news and send alerts
async def scheduled_job(context):
    """Run scheduled tasks"""
    job = context.job
    application = context.application
    
    current_hour = datetime.now().hour
    current_minute = datetime.now().minute
    
    # Check for news and send alerts every 15 minutes during market hours
    if is_market_open():
        await check_news_and_send_alerts(application)
    
    # Send daily market outlook at 9:00 AM on market days
    if current_hour == 9 and current_minute == 0:
        await daily_market_outlook(application)
    
    # Send end of day summary at 3:45 PM on market days
    if current_hour == 15 and current_minute == 45:
        await run_end_of_day_summary(application)

def main():
    """Start the bot."""
    # Create the Application
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("stocks", stocks_command))
    application.add_handler(CommandHandler("watchlist", watchlist_command))
    application.add_handler(CommandHandler("performance", performance_command))

    # Schedule job to run every 5 minutes
    job_queue = application.job_queue
    job_queue.run_repeating(scheduled_job, interval=300, first=10)

    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()