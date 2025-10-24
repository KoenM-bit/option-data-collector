#!/usr/bin/env python3
"""
Main Sentiment Tracker - New Structured Version
Entry point for AD.AS sentiment analysis.
"""

from src.services.sentiment_service import SentimentService


def main():
    """Main execution - same logic as original sentiment_tracker.py"""
    sentiment_service = SentimentService()

    print(f"📊 AD.AS Sentiment Tracker v2.0")
    print(f"🎯 Target: {sentiment_service.ticker}")
    print("-" * 40)

    sentiment_service.collect_and_store_sentiment()


if __name__ == "__main__":
    main()
