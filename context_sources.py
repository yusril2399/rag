from youtube_transcript_api import YouTubeTranscriptApi
import wikipedia
import feedparser
import requests
import logging
from bs4 import BeautifulSoup
import time
import re
import datetime
from sentence_transformers import SentenceTransformer, util
import torch
import os
from newspaper import Article
from concurrent.futures import ThreadPoolExecutor

RSS_FEEDS = {
    
    # === National Geographic ===
    "NatGeo - Latest Stories": "https://www.nationalgeographic.com/pages/topic/latest-stories/rss.xml",
    "NatGeo - Science": "https://www.nationalgeographic.com/pages/topic/science/rss.xml",
    "NatGeo - History & Culture": "https://www.nationalgeographic.com/pages/topic/history/rss.xml",
    "NatGeo - Travel": "https://www.nationalgeographic.com/pages/topic/travel/rss.xml",
    "NatGeo - Animals": "https://www.nationalgeographic.com/pages/topic/animals/rss.xml",
    # General World News
    "BBC": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "The Guardian": "https://www.theguardian.com/world/rss",
    "NYT World": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml",

    # Tech & Science
    "ArsTechnica": "https://feeds.arstechnica.com/arstechnica/index",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Wired": "https://www.wired.com/feed/rss",

    # Business & Finance
    "Bloomberg": "https://www.bloomberg.com/feed/podcast/etf-report.xml",
    "Financial Times": "https://www.ft.com/?format=rss",

    # Entertainment
    "Variety": "https://variety.com/feed/",
    "Hollywood Reporter": "https://www.hollywoodreporter.com/t/rss/",
    "BBC Entertainment": "http://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",

    # Sports
    "ESPN": "https://www.espn.com/espn/rss/news",
    "BBC Sport": "http://feeds.bbci.co.uk/sport/rss.xml?edition=uk",

    # Japan-focused
    "NEWSJAPAN4": "https://newsonjapan.com/html/newsdesk/Society_News/rss/index.xml",
    "NEWSJAPAN5": "https://newsonjapan.com/html/newsdesk/Technology_News/rss/index.xml",
    "NEWSJAPAN6": "https://newsonjapan.com/html/newsdesk/Education_News/rss/index.xml",
    "NEWSJAPAN7": "https://newsonjapan.com/rss/top.xml",
    "japantimes": "https://www.japantimes.co.jp/feed/",
    "japantoday": "https://japantoday.com/feed/atom",
    "NYK japan": "https://www.nytimes.com/svc/collections/v1/publish/http://www.nytimes.com/topic/destination/japan/rss.xml",
    "livedoor" : "https://news.livedoor.com/topics/rss/top.xml",
    "bridge": "https://thebridge.jp/en/feed",
    "japan inside" : "https://thebridge.jp/en/feed",
    "SNA JAPAN":"https://shingetsunewsagency.com/feed/",
    "japan running":"http://japanrunningnews.blogspot.com/feeds/posts/default?alt=rss",
    "JIN": "https://www.japanindustrynews.com/feed/",

    # NPR & DW
    "NPR": "https://feeds.npr.org/1001/rss.xml",
    "DW": "https://rss.dw.com/rdf/rss-en-all",

    # === 🔥 Viral & Trending Sources ===
    "Mashable Hot": "https://mashable.com/feeds/rss/all",
    "TMZ": "https://www.tmz.com/rss.xml",
    "Know Your Meme": "https://knowyourmeme.com/newsfeed.rss",
    "SoraNews24": "https://soranews24.com/feed/"


}

def clean_wikipedia_text(text: str) -> str:
    text = re.sub(r"==+\\s*(.*?)\\s*==+", r"\1", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"\\n+", " ", text)
    text = re.sub(r"\\s{2,}", " ", text)
    return text.strip()

def is_valid_summary(text: str) -> bool:
    return not any(x in text.lower() for x in [
        "summary length", "viewer discussion", "edit this page", "propose editing",
        "duplicate", "link at top", "characters words", "discussion propose"
    ])

def is_recent(summary: str, year_threshold=2025):
    for y in range(2000, year_threshold):
        if str(y) in summary:
            return False
    return True

def is_news_title(title: str):
    banned_keywords = ["trailer", "tv series", "movie", "film", "cast", "actor", "documentary"]
    return not any(kw in title.lower() for kw in banned_keywords)

def fetch_wikipedia_summary(topic, sentences=5):
    try:
        summary = wikipedia.summary(topic, sentences=sentences)
        if "==" in summary:  # ada heading section
            logging.warning(f"[Wikipedia] Page '{topic}' contains section headers — likely full page.")
            return "[Wikipedia] ⚠️ Skipped — page too long or contains section headers."
        if any(x in summary.lower() for x in [
            "has removed this page", "problems displaying this page",
            "log in to", "subscribe now", "contact wiki@", "premium access"
        ]):
            return "[Wikipedia] ⚠️ Invalid or removed page — skipped."
        return summary
    except Exception as e:
        try:
            alt = wikipedia.search(topic)
            if alt:
                summary = wikipedia.summary(alt[0], sentences=sentences)
                if "==" in summary:
                    logging.warning(f"[Wikipedia] Alt page '{alt[0]}' contains section headers — likely full page.")
                    return "[Wikipedia] ⚠️ Skipped — alt page too long."
                return summary
            return f"[Wikipedia] No match found for: {topic}"
        except Exception as e:
            return f"[Wikipedia] Error: {e}"

def fetch_youtube_transcript(video_id):
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id)
        logging.info(f"[YouTube] Transcript fetched for video ID: {video_id}")
        return " ".join([seg["text"] for seg in transcript])
    except Exception as e:
        logging.warning(f"[YouTube] Error for video ID '{video_id}': {e}")
        return f"[YouTube] Error: {e}"

def fetch_rss_articles(feed_url, topic=None, max_articles=3):
    try:
        import feedparser
        import logging
        feed = feedparser.parse(feed_url)
        articles = []
        for entry in feed.entries:
            title = getattr(entry, "title", "No Title")
            summary = getattr(entry, "summary", "") or getattr(entry, "description", "") or "No summary available"
            link = getattr(entry, "link", "")

            articles.append({
                "title": title,
                "summary": summary.strip(),
                "link": link
            })
            if len(articles) >= max_articles:
                break
        logging.info(f"[RSS] {len(articles)} articles fetched from feed: {feed_url}")
        return articles
    except Exception as e:
        logging.warning(f"[RSS] Error fetching feed {feed_url}: {e}")
        return [{"title": "RSS Error", "summary": str(e), "link": ""}]

def fetch_twitter_posts(bearer_token, query, max_results=10):
    url = "https://api.twitter.com/2/tweets/search/recent"
    headers = {"Authorization": f"Bearer {bearer_token}"}
    params = {
        "query": query,
        "max_results": max_results,
        "tweet.fields": "text,author_id"
    }
    for attempt in range(3):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code == 200:
                tweets = response.json().get("data", [])
                logging.info(f"[Twitter] Retrieved {len(tweets)} tweets for query: {query}")
                return [t["text"] for t in tweets]
            elif response.status_code == 403:
                logging.error("[Twitter] 403 Forbidden - Check access rights.")
                return ["[Twitter] 403 Forbidden."]
            elif response.status_code == 429:
                logging.error("[Twitter] 429 Rate Limit Exceeded.")
                return ["[Twitter] 429 Rate Limit."]
            else:
                logging.error(f"[Twitter] Error {response.status_code}: {response.text}")
                return [f"[Twitter] Error: {response.status_code}"]
        except Exception as e:
            logging.warning(f"[Twitter] Attempt {attempt+1} failed: {e}")
            time.sleep(2)
    return ["[Twitter] Failed to fetch tweets after retries."]

def is_relevant_article(topic, article, model, threshold=0.75):
    try:
        combined = f"{article['title']} {article['summary']}"
        topic_emb = model.encode(topic, convert_to_tensor=True)
        text_emb = model.encode(combined, convert_to_tensor=True)
        score = float(util.cos_sim(topic_emb, text_emb))
        logging.info(f"[SIM] score={score:.3f} | {article['title']}")
        return score > threshold
    except Exception as e:
        logging.warning(f"[FILTER] Error scoring article: {e}")
        return False

def fetch_rss_articles_all_sources(topic):
    results = []
    for name, url in RSS_FEEDS.items():
        results += fetch_rss_articles(url, topic=topic)
    return results

def get_full_article_content(url, max_len=1000):
    try:
        article = Article(url)
        article.download()
        article.parse()
        text = article.text.strip()
        text = " ".join(text.split())
        return text[:max_len] if len(text) >= 100 else ""
    except Exception as e:
        logging.warning(f"[SCRAPE FALLBACK] Failed to fetch full article ({url}), using snippet instead. Reason: {e}")
        return ""  # akan digantikan snippet di bawah

def fetch_search_results(query, max_results=3, full_text=False):
    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": "3b010519d677aa945e39acad7ed4fc5e87157071",
        "Content-Type": "application/json"
    }
    payload = {"q": query}
    blacklist = ["search", "result", "reset", "cancel", "filter", "wiki", "recent changes", "navigation"]

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        results = response.json().get("organic", [])

        snippets = []
        for r in results:
            title = r.get("title", "").strip()
            link = r.get("link", "").strip()
            snippet = r.get("snippet", "").strip()

            if not title or not link or any(bad in title.lower() for bad in blacklist):
                continue

            content = ""
            if full_text:
                content = get_full_article_content(link)
                if len(content.split()) < 30:
                    if len(snippet.split()) >= 30:
                        logging.warning(f"[SCRAPE FALLBACK] Failed to fetch full article ({link}), using snippet instead.")
                        content = snippet
                    else:
                        continue  # skip if both full article and snippet too short
            else:
                content = snippet

            if len(content.split()) < 30:
                continue

            snippets.append(f"[{title}]\n{content}")
            if len(snippets) >= max_results:
                break

        logging.info(f"[SEARCH] {len(snippets)} results fetched for query: {query}")
        return snippets

    except Exception as e:
        logging.warning(f"[SEARCH ERROR] {e}")
        return []

def deduplicate_context(context_list, min_words=30):
    seen = set()
    cleaned = []
    for c in context_list:
        text = c.strip()
        if len(text.split()) < min_words:
            continue
        norm = " ".join(text.lower().split())  # normalize case & space
        if norm in seen:
            continue
        seen.add(norm)
        cleaned.append(text)
    return cleaned

def fetch_context_sources_scored(
    topic: str,
    youtube_video_id: str = None,
    rss_key: str = None,
    bearer_token: str = None,
    max_tokens: int = 512,
    top_k_contexts: int = 10,
    similarity_threshold: float = 0.75
):
    logging.info(f"[CTX-SCORED] Building scored context for: {topic}")
    topic = " ".join(topic.strip().split()[:6])
    embed_model = SentenceTransformer("all-MiniLM-L12-v2")
    DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    topic_emb = embed_model.encode(topic, convert_to_tensor=True)

    candidates = []

    # === Parallel fetch Wikipedia, Search, RSS ===
    with ThreadPoolExecutor() as executor:
        future_wiki = executor.submit(fetch_wikipedia_summary, topic)
        future_search = executor.submit(fetch_search_results, topic, full_text=True)
        future_rss = executor.submit(fetch_rss_articles_all_sources, topic)

        wiki = future_wiki.result()
        search_results = future_search.result()
        rss_articles = future_rss.result()

    # === Wikipedia
    if is_valid_summary(wiki):
        cleaned = clean_wikipedia_text(wiki)
        if len(cleaned.split()) > 30:
            candidates.append(("WIKIPEDIA", cleaned))

    # === Search Results
    for s in search_results:
        if len(s.split()) > 30:
            candidates.append(("SEARCH", s))

    # === RSS
    for article in rss_articles:
        if is_news_title(article["title"]) and is_recent(article["summary"]):
            combined = f"{article['title']}. {article['summary']}"
            if len(combined.split()) > 30:
                candidates.append((f"RSS: {article['title']}", combined))

    # === Twitter
    if bearer_token:
        tweets = fetch_twitter_posts(bearer_token, topic)
        for t in tweets:
            if len(t.split()) > 20:
                candidates.append(("TWITTER", t))

    # === COSINE SCORING + Deduplication
    scored = []
    for label, text in candidates:
        if not text.strip() or len(text.split()) < 30:
            continue
        try:
            text_emb = embed_model.encode(text, convert_to_tensor=True)
            score = float(util.cos_sim(topic_emb, text_emb))
            if score >= similarity_threshold:
                scored.append((label, text, score))
        except Exception as e:
            logging.warning(f"[CTX-SCORE] Error scoring {label}: {e}")

    raw_texts = [f"[{label}]\n{text}" for label, text, _ in scored]
    deduped_texts = deduplicate_context(raw_texts, min_words=30)

    scored_clean = []
    for entry in deduped_texts:
        label = entry.split("]")[0][1:]
        text = entry.split("\n", 1)[-1]
        try:
            score = float(util.cos_sim(topic_emb, embed_model.encode(text, convert_to_tensor=True)))
            scored_clean.append((label, text, score))
        except:
            continue

    if not scored_clean:
        logging.warning("[CTX-SCORED] No relevant context found above threshold.")
        return ""

    # === Compose Final Context
    sorted_contexts = sorted(scored_clean, key=lambda x: x[2], reverse=True)[:top_k_contexts]
    final_context = []
    total_words = 0

    for label, text, score in sorted_contexts:
        words = text.split()
        if total_words + len(words) > max_tokens:
            continue
        final_context.append(f"[{label}]\n{text}")
        total_words += len(words)

    result = "\n\n".join(final_context)
    logging.info(f"[CTX-SCORED] Final context tokens: {len(result.split())}")
    logging.info(f"[CTX-SCORED] Preview:\n{result[:500]}")
    return result

__all__ = [
    #"fetch_context_sources",
    "fetch_wikipedia_summary",
    "fetch_youtube_transcript",
    "fetch_rss_articles",
    "fetch_twitter_posts",
    "fetch_context_sources_scored",
    "fetch_search_results",
    "deduplicate_context"
]