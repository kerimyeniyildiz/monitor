import os
import sys
import time
from datetime import datetime

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from xml.etree import ElementTree

# Load environment variables from a local .env file if it exists.
load_dotenv()

API_KEY = os.getenv("API_KEY") or os.getenv("X_API_KEY")
QUERY = os.getenv("QUERY", "Kırklareli")
QUERY_TYPE = os.getenv("QUERY_TYPE", "Latest")
TWEET_LIMIT = int(os.getenv("TWEET_LIMIT", "10"))
TWEET_POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "300"))  # 5 minutes default
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SENT_URLS_FILE = os.getenv("SENT_URLS_FILE", "sent_urls.txt")
HTTP_TIMEOUT = float(os.getenv("HTTP_TIMEOUT_SECONDS", "30"))
HTTP_MAX_RETRIES = int(os.getenv("HTTP_MAX_RETRIES", "3"))
HTTP_RETRY_BACKOFF = float(os.getenv("HTTP_RETRY_BACKOFF", "2"))
SITEMAP_LIST_FILE = os.getenv("SITEMAP_LIST_FILE", "sitemap.txt")
SITEMAP_LIST_URL = os.getenv("SITEMAP_LIST_URL")  # harici sitemap listesi (satır başına URL)
SITEMAP_CHECK_SECONDS = int(os.getenv("SITEMAP_CHECK_SECONDS", "600"))  # 10 minutes
SITEMAP_REFRESH_SECONDS = int(os.getenv("SITEMAP_REFRESH_SECONDS", "86400"))  # 24 hours
NEWS_SENT_FILE = os.getenv("NEWS_SENT_FILE", "sent_news.txt")

API_URL = "https://api.twitterapi.io/twitter/tweet/advanced_search"
TELEGRAM_SEND_URL = (
    f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage" if TELEGRAM_TOKEN else None
)


def ensure_api_key() -> None:
    """Fail fast if the API key is missing."""
    if not API_KEY:
        sys.exit("API_KEY (x-api-key) bulunamadı. Lütfen .env içine ekleyin veya env değişkeni olarak geçin.")


def create_session() -> requests.Session:
    """HTTP session with retry policy for transient errors and timeouts."""
    session = requests.Session()
    retry = Retry(
        total=HTTP_MAX_RETRIES,
        backoff_factor=HTTP_RETRY_BACKOFF,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "POST"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def fetch_latest_tweets() -> list[dict]:
    """Run advanced search for the configured query."""
    headers = {"x-api-key": API_KEY}
    params = {"query": QUERY, "queryType": QUERY_TYPE}

    response = SESSION.get(API_URL, headers=headers, params=params, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    payload = response.json()
    return payload.get("tweets", [])


def load_sent_urls() -> set[str]:
    """Load previously sent tweet URLs from disk to avoid duplicate Telegram messages."""
    if not os.path.exists(SENT_URLS_FILE):
        return set()
    with open(SENT_URLS_FILE, encoding="utf-8") as file:
        return {line.strip() for line in file if line.strip()}


def persist_sent_url(url: str) -> None:
    """Append a sent tweet URL to disk."""
    with open(SENT_URLS_FILE, "a", encoding="utf-8") as file:
        file.write(url + "\n")


def load_sent_news() -> set[str]:
    """Load previously sent news URLs from disk."""
    if not os.path.exists(NEWS_SENT_FILE):
        return set()
    with open(NEWS_SENT_FILE, encoding="utf-8") as file:
        return {line.strip() for line in file if line.strip()}


def persist_sent_news(url: str) -> None:
    """Append a sent news URL to disk."""
    with open(NEWS_SENT_FILE, "a", encoding="utf-8") as file:
        file.write(url + "\n")


def load_sitemap_sources() -> list[str]:
    """Read sitemap sources from remote URL (preferred) or local file."""
    if SITEMAP_LIST_URL:
        try:
            response = SESSION.get(SITEMAP_LIST_URL, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            lines = response.text.splitlines()
            return [line.strip() for line in lines if line.strip()]
        except Exception as err:
            print(f"{datetime.now().isoformat(timespec='seconds')} Sitemap listesi uzaktan alınamadı ({SITEMAP_LIST_URL}): {err}")
            return []

    if not os.path.exists(SITEMAP_LIST_FILE):
        print(
            f"{datetime.now().isoformat(timespec='seconds')} Uyarı: {SITEMAP_LIST_FILE} bulunamadı ve SITEMAP_LIST_URL tanımlı değil."
        )
        return []
    with open(SITEMAP_LIST_FILE, encoding="utf-8") as file:
        return [line.strip() for line in file if line.strip()]


def fetch_sitemap_urls(sitemap_url: str) -> list[str]:
    """Fetch and parse URLs from a sitemap.xml file."""
    response = SESSION.get(sitemap_url, timeout=HTTP_TIMEOUT)
    response.raise_for_status()
    try:
        tree = ElementTree.fromstring(response.content)
    except ElementTree.ParseError as err:
        print(f"{datetime.now().isoformat(timespec='seconds')} Sitemap parse hatası ({sitemap_url}): {err}")
        return []

    urls = []
    for loc in tree.iter():
        if loc.tag.endswith("loc") and loc.text:
            urls.append(loc.text.strip())
    return urls


def build_fallback_url(tweet_id: str | None) -> str:
    """Construct a fallback URL if API response lacks one."""
    if not tweet_id:
        return ""
    return f"https://x.com/i/web/status/{tweet_id}"


def send_telegram_message(text: str) -> bool:
    """Send a Telegram message if credentials are present; return True on success."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID or not TELEGRAM_SEND_URL:
        return False

    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    try:
        response = SESSION.post(TELEGRAM_SEND_URL, json=payload, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        return True
    except Exception as err:
        print(f"{datetime.now().isoformat(timespec='seconds')} Telegram gönderim hatası: {err}")
        return False


def main() -> None:
    ensure_api_key()
    seen_ids: set[str] = set()
    sent_urls = load_sent_urls()
    sent_news = load_sent_news()

    # Timers
    next_tweet_check = 0.0
    next_sitemap_check = 0.0
    next_sitemap_refresh = 0.0
    sitemap_sources: list[str] = []

    print(
        f"{datetime.now().isoformat(timespec='seconds')} -> '{QUERY}' sorgusu (queryType={QUERY_TYPE}) takip ediliyor; her {TWEET_POLL_INTERVAL} saniyede bir sorgu."
    )
    print(
        f"{datetime.now().isoformat(timespec='seconds')} -> Sitemaps kaynağı ({SITEMAP_LIST_URL or SITEMAP_LIST_FILE}) {SITEMAP_CHECK_SECONDS} saniyede bir; listeyi {SITEMAP_REFRESH_SECONDS} saniyede bir yenile."
    )

    while True:
        now = time.time()

        # Refresh sitemap list daily (or configured period)
        if now >= next_sitemap_refresh:
            sitemap_sources = load_sitemap_sources()
            next_sitemap_refresh = now + SITEMAP_REFRESH_SECONDS

        # Tweet check
        if now >= next_tweet_check:
            try:
                tweets = fetch_latest_tweets()
            except requests.HTTPError as http_err:
                print(f"{datetime.now().isoformat(timespec='seconds')} HTTP hatası: {http_err}")
            except Exception as err:
                print(f"{datetime.now().isoformat(timespec='seconds')} Beklenmeyen hata (tweet): {err}")
            else:
                matches: list[tuple[dict, str]] = []
                subset = tweets[:TWEET_LIMIT] if TWEET_LIMIT > 0 else tweets
                for tweet in subset:
                    tweet_id = tweet.get("id")
                    url = tweet.get("url") or build_fallback_url(tweet_id)

                    # Skip tweets we have already seen to avoid duplicate logs.
                    if tweet_id and tweet_id in seen_ids:
                        continue

                    if tweet_id:
                        seen_ids.add(tweet_id)

                    # Skip tweets that were already pushed to Telegram in previous runs.
                    if url and url in sent_urls:
                        continue

                    matches.append((tweet, url))

                if matches:
                    print(
                        f"{datetime.now().isoformat(timespec='seconds')} Yeni tweet eşleşmeleri bulundu ({len(matches)} adet):"
                    )
                    for match, url in reversed(matches):
                        author = match.get("author") or {}
                        author_name = author.get("userName") or author.get("name") or "?"
                        created_at = match.get("createdAt", "?")
                        text = match.get("text") or ""
                        print(f"- [{created_at}] {author_name} #{match.get('id')}: {text}")

                        message = (
                            f"Yeni tweet bulundu:\n"
                            f"{author_name} [{created_at}]\n"
                            f"{text}\n"
                            f"{url}"
                        )
                        sent = send_telegram_message(message)
                        if sent and url:
                            sent_urls.add(url)
                            persist_sent_url(url)
                else:
                    print(f"{datetime.now().isoformat(timespec='seconds')} Yeni tweet eşleşmesi yok.")

            next_tweet_check = now + TWEET_POLL_INTERVAL

        # Sitemap/news check
        if now >= next_sitemap_check and sitemap_sources:
            for sitemap_url in sitemap_sources:
                try:
                    urls = fetch_sitemap_urls(sitemap_url)
                except requests.HTTPError as http_err:
                    print(f"{datetime.now().isoformat(timespec='seconds')} Sitemap HTTP hatası ({sitemap_url}): {http_err}")
                    continue
                except Exception as err:
                    print(f"{datetime.now().isoformat(timespec='seconds')} Beklenmeyen hata (sitemap {sitemap_url}): {err}")
                    continue

                new_links = []
                for url in urls:
                    if url in sent_news:
                        continue
                    new_links.append(url)

                if new_links:
                    print(
                        f"{datetime.now().isoformat(timespec='seconds')} Yeni haber linkleri bulundu ({len(new_links)} adet) - {sitemap_url}"
                    )
                    for link in new_links:
                        message = f"Yeni haber: {link}"
                        sent = send_telegram_message(message)
                        if sent:
                            sent_news.add(link)
                            persist_sent_news(link)
                else:
                    print(f"{datetime.now().isoformat(timespec='seconds')} Yeni haber yok ({sitemap_url}).")

            next_sitemap_check = now + SITEMAP_CHECK_SECONDS
        elif now >= next_sitemap_check and not sitemap_sources:
            print(f"{datetime.now().isoformat(timespec='seconds')} Sitemap listesi boş; {SITEMAP_LIST_FILE} kontrol edin.")
            next_sitemap_check = now + SITEMAP_CHECK_SECONDS

        # Sleep until the next scheduled action, but cap to avoid long sleeps.
        sleep_targets = [next_tweet_check, next_sitemap_check]
        sleep_time = min(target - time.time() for target in sleep_targets if target > time.time())
        time.sleep(max(1, min(sleep_time, 60)))


if __name__ == "__main__":
    SESSION = create_session()
    main()
