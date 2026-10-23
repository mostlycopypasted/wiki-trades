#!/usr/bin/env python3
"""
Market sentiment scan for any instrument: pulls Google News RSS headlines
per instrument, scores each headline with VADER, and prints a per-instrument
Positive/Negative/Neutral breakdown plus an overall combined summary across
all instruments scanned. Falls back to general market-news RSS feeds
(investinglive.com, investing.com), keyword-matched, when an instrument's
primary Google News coverage is thin. Appends each run to that day's report
at wiki/reports/market-sentiment/YYYY-MM-DD-market-sentiment.md.

x86 fork (2026-08-11): identical to market_sentiment.py (the Apple Silicon
original) except for the environment it expects. PyPI stopped shipping torch
wheels beyond 2.2.2 for Intel/x86_64 macOS, so this machine's transformers
and numpy are pinned down to match (transformers==4.44.2, numpy<2.0) instead
of the newer versions the Apple Silicon original assumes. Keep the two files
in sync for any real logic changes; only the pinned-dependency assumption
differs.

Usage:
    python3 scripts/market_sentiment_x86.py
    python3 scripts/market_sentiment_x86.py --instruments XAUUSD,BTCUSD
    python3 scripts/market_sentiment_x86.py --instruments NVDA --search-term "Nvidia stock"
    python3 scripts/market_sentiment_x86.py --num-articles 5
"""

import argparse
import re
import sys
import feedparser
from textblob import TextBlob
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch
import numpy as np

from report_toc import upsert_toc

finbert_model = AutoModelForSequenceClassification.from_pretrained("yiyanghkust/finbert-tone")
finbert_tokenizer = AutoTokenizer.from_pretrained("yiyanghkust/finbert-tone")

labels = ['Positive', 'Negative', 'Neutral']

# Ticker -> (display name, news-search term). The search term is kept
# distinct from the display name where the bare name is too ambiguous for
# Google News (e.g. "oil" alone pulls in cooking/palm-oil coverage).
INSTRUMENTS = {
    "XAUUSD": ("Gold", "gold"),
    "XAGUSD": ("Silver", "silver"),
    "USOUSD": ("Crude Oil", "crude oil"),
    "BTCUSD": ("Bitcoin", "bitcoin"),
    "ETHUSD": ("Ethereum", "ethereum"),
    "NDQ100": ("Nasdaq 100", "Nasdaq 100"),
    "QQQ": ("Nasdaq 100 ETF (QQQ)", "Nasdaq 100 ETF"),
    "SPY": ("S&P 500 ETF (SPY)", "S&P 500 ETF"),
    "DXY": ("US Dollar Index (DXY)", "US Dollar Index"),
    "US30": ("Dow Jones (US30)", "Dow Jones"),
    "US2000": ("Russell 2000 (US2000)", "Russell 2000"),
    "JPN225": ("Nikkei 225 (JPN225)", "Nikkei 225"),
    # Magnificent Seven
    "AAPL": ("Apple (AAPL)", "Apple stock"),
    "MSFT": ("Microsoft (MSFT)", "Microsoft stock"),
    "GOOGL": ("Alphabet / Google (GOOGL)", "Google stock"),
    "AMZN": ("Amazon (AMZN)", "Amazon stock"),
    "NVDA": ("Nvidia (NVDA)", "Nvidia stock"),
    "META": ("Meta Platforms (META)", "Meta Platforms stock"),
    "TSLA": ("Tesla (TSLA)", "Tesla stock"),
}

QUERY_SUFFIXES = ["market", "price", "news", "trends", "analysis", "forecast", "investment"]

# Small set of currency codes used to guess a sensible search term for an ad
# hoc 6-letter forex ticker that isn't already curated in INSTRUMENTS.
CURRENCY_CODES = {"USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF", "CNY", "SGD", "HKD"}

# General market-news RSS feeds used to supplement an instrument's coverage
# when its primary Google News results are thin — keyword-matched against
# title text since these feeds aren't per-instrument searchable.
FALLBACK_FEEDS = [
    "https://investinglive.com/feed/",
    "https://www.investing.com/rss/investing_news.rss",
]
FALLBACK_THRESHOLD = 5

# Only this many headlines (picked by |polarity|, most sentiment-informative
# first) are printed/written per instrument — scoring still uses every
# fetched article, this just keeps the report from ballooning into a wall of
# Google News redirect links.
HEADLINES_DISPLAY_LIMIT = 5

WIKI_ROOT = Path(__file__).resolve().parent.parent
REPORT_DIR = WIKI_ROOT / "wiki" / "reports" / "market-sentiment"

analyzer = SentimentIntensityAnalyzer()
_fallback_cache = None


def fetch_news(query, num_articles=10):
    rss_url = f"https://news.google.com/rss/search?q={quote(query)}"
    feed = feedparser.parse(rss_url)
    news_items = feed.entries[:num_articles]

    articles = []
    for item in news_items:
        articles.append({
            "title": item.title,
            "link": item.link,
            "published": item.published,
        })

    return articles


def _load_fallback_items():
    global _fallback_cache
    if _fallback_cache is None:
        items = []
        for url in FALLBACK_FEEDS:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                items.append({
                    "title": getattr(entry, "title", ""),
                    "link": getattr(entry, "link", ""),
                    "published": getattr(entry, "published", ""),
                })
        _fallback_cache = items
    return _fallback_cache


def fetch_fallback_news(search_term, limit=10):
    # Word-boundary match, not plain substring — "gold" as a bare substring
    # would false-positive inside "Goldman Sachs" headlines.
    pattern = re.compile(r"\b" + re.escape(search_term.lower()) + r"\b")
    matches = []
    for item in _load_fallback_items():
        if pattern.search(item["title"].lower()):
            matches.append(item)
            if len(matches) >= limit:
                break
    return matches


def guess_instrument(ticker):
    """Best-effort (display_name, search_term) for a ticker not in INSTRUMENTS."""
    if len(ticker) == 6:
        base, quote_ccy = ticker[:3], ticker[3:]
        if base in CURRENCY_CODES and quote_ccy in CURRENCY_CODES:
            return ticker, f"{base} {quote_ccy} exchange rate"
    return ticker, ticker


def analyze_sentiment(text):

    scores = analyzer.polarity_scores(text)
    polarity = scores['compound']

    # analysis = TextBlob(text)
    # polarity = analysis.sentiment.polarity

    if polarity > 0.05:
        sentiment = 'Positive'
    elif polarity < -0.05:
        sentiment = 'Negative'
    else:
        sentiment = 'Neutral'

    return polarity, sentiment

# def analyze_sentiment(text):
#     if not text.strip():
#         return 0.0, 'Neutral'

#     inputs = finbert_tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
#     with torch.no_grad():
#         outputs = finbert_model(**inputs)

#     logits = outputs.logits
#     probabilities = torch.softmax(logits, dim=1).numpy()[0]
#     max_index = np.argmax(probabilities)
#     sentiment = labels[max_index]
#     confidence = probabilities[max_index]

#     return confidence, sentiment


def summarize_sentiments(articles, label):
    summary = {
        "Positive": 0,
        "Negative": 0,
        "Neutral": 0
    }

    for article in articles:
        _, sentiment = analyze_sentiment(article['title'])
        summary[sentiment] += 1

    total = len(articles)
    lines = [f"\n## {label}"]
    if total == 0:
        lines.append("No articles found.")
        return summary, "\n".join(lines)

    lines.append(f"Total articles analyzed: {total}")
    for sentiment, count in summary.items():
        percent = (count / total) * 100
        lines.append(f"{sentiment}: {count} ({percent:.2f}%)")

    return summary, "\n".join(lines)


def scan_instrument(ticker, display_name, search_term, num_articles_per_query):
    queries = [f"{search_term} {suffix}" for suffix in QUERY_SUFFIXES]

    articles = []
    seen_links = set()
    for query in queries:
        print(f"Fetching news articles for '{query}'...", file=sys.stderr)
        for article in fetch_news(query, num_articles_per_query):
            if article['link'] in seen_links:
                continue
            seen_links.add(article['link'])
            articles.append(article)

    fallback_used = 0
    if len(articles) < FALLBACK_THRESHOLD:
        print(f"Only {len(articles)} article(s) from Google News for '{search_term}' — supplementing from fallback RSS sources...", file=sys.stderr)
        for article in fetch_fallback_news(search_term, num_articles_per_query):
            if article['link'] in seen_links:
                continue
            seen_links.add(article['link'])
            articles.append(article)
            fallback_used += 1

    scored = [(a,) + analyze_sentiment(a['title']) for a in articles]
    top_headlines = sorted(scored, key=lambda x: abs(x[1]), reverse=True)[:HEADLINES_DISPLAY_LIMIT]

    lines = [f"\n# {display_name} ([[{ticker}]])"]
    if fallback_used:
        lines.append(f"_Supplemented with {fallback_used} article(s) from fallback RSS sources (investinglive.com, investing.com) — primary Google News coverage was thin._")
    if len(articles) > len(top_headlines):
        lines.append(f"Top {len(top_headlines)} of {len(articles)} article(s) by sentiment magnitude:")
    for idx, (article, polarity, sentiment) in enumerate(top_headlines, 1):
        lines.append(f"{idx}. {article['title']}")
        lines.append(f"   {article['link']}")
        lines.append(f"   Published: {article['published']} | Sentiment: {sentiment} (Polarity: {polarity:.2f})")

    summary, summary_text = summarize_sentiments(articles, f"{display_name} ([[{ticker}]]) Summary")
    lines.append(summary_text)

    total = len(articles)
    pos_pct = summary["Positive"] / total * 100 if total else 0.0
    neg_pct = summary["Negative"] / total * 100 if total else 0.0
    neu_pct = summary["Neutral"] / total * 100 if total else 0.0
    table_row = f"| {display_name} ([[{ticker}]]) | {total} | {pos_pct:.2f}% | {neg_pct:.2f}% | {neu_pct:.2f}% | _pending_ |"

    return articles, "\n".join(lines), table_row


def write_report(report_text, tickers, table_rows):
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M SGT")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_DIR / f"{date_str}-market-sentiment.md"

    if set(tickers) == set(INSTRUMENTS):
        scope = f"Full Watchlist ({len(tickers)} instruments)"
    else:
        # Plain text, no [[ ]] -- this goes straight into a "## " heading
        # below, and a [[TICKER]] wikilink nested inside a heading breaks
        # the TOC entry's own [[#heading]] link parsing (multiple `]]`
        # before the real close). Bracketed mentions are fine elsewhere.
        scope = ", ".join(tickers)

    table = "\n".join([
        "| Instrument | Articles | Positive | Negative | Neutral | Summary |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
        *table_rows,
    ])

    run_section = f"""## 🕒 Run — {time_str} — {scope}

{table}

> _Replace each `_pending_` cell above with a ~200-word prose summary of that instrument's news flow — single line, no `|` or line breaks inside the cell — before considering this run complete._

<details>
<summary>Headline detail (top {HEADLINES_DISPLAY_LIMIT} per instrument by sentiment magnitude)</summary>

{report_text.strip()}

</details>

---
"""

    if report_path.exists():
        existing = report_path.read_text(encoding="utf-8")
        new_full_text = existing.rstrip("\n") + "\n\n" + run_section
    else:
        frontmatter = f"""---
kind: report
tags: [trading-instrument, reference]
date: {date_str}
---

# Market Sentiment — {date_str}

News-based sentiment scans (Google News RSS + VADER, falling back to investinglive.com/investing.com RSS when coverage is thin) for {date_str}. Same-day reruns append a new run section below rather than overwrite.

---

"""
        new_full_text = frontmatter + run_section

    # TOC must be rebuilt from ALL headings now present (old + this run's),
    # not just this run's -- upsert_toc() strips any stale TOC block and
    # regenerates it fresh every invocation, so it never falls behind
    # across same-day reruns.
    new_full_text = upsert_toc(new_full_text)
    report_path.write_text(new_full_text, encoding="utf-8")

    return report_path


def main():
    parser = argparse.ArgumentParser(description="Market sentiment scan for any instrument (Google News RSS + VADER, with RSS fallback)")
    parser.add_argument("--instruments", default=",".join(INSTRUMENTS),
                         help=f"Comma-separated tickers. Known tickers use curated search terms ({list(INSTRUMENTS)}); any other ticker is accepted ad hoc (default: all known)")
    parser.add_argument("--num-articles", type=int, default=10,
                         help="Articles fetched per query, per instrument (default: 10)")
    parser.add_argument("--search-term", default=None,
                         help="Override the news-search term for a single ad hoc ticker (ignored/invalid when --instruments has more than one ticker)")
    args = parser.parse_args()

    tickers = [t.strip().upper() for t in args.instruments.split(",") if t.strip()]

    if args.search_term and len(tickers) != 1:
        parser.error("--search-term can only be used with a single ticker in --instruments")

    all_articles = []
    sections = []
    table_rows = []
    for ticker in tickers:
        if ticker in INSTRUMENTS:
            display_name, search_term = INSTRUMENTS[ticker]
        elif args.search_term:
            display_name, search_term = ticker, args.search_term
        else:
            display_name, search_term = guess_instrument(ticker)
        articles, section_text, table_row = scan_instrument(ticker, display_name, search_term, args.num_articles)
        all_articles.extend(articles)
        sections.append(section_text)
        table_rows.append(table_row)

    _, overall_text = summarize_sentiments(all_articles, "Overall Summary (All Instruments)")
    sections.append(overall_text)

    report_text = "\n".join(sections)
    print(report_text)
    report_path = write_report(report_text, tickers, table_rows)
    print(f"\n📝 Report updated: {report_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
