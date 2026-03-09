import requests
import json
import os
import xml.etree.ElementTree as ET
import re

# ── Config ──────────────────────────────────────────────
RSS_FEEDS = [
    {
        "url": "https://www.1tamilmv.army/index.php?/forums/forum/11-web-hd-itunes-hd-bluray.xml/",
        "label": "🎬 Web-HD / iTunes / BluRay",
        "emoji": "🔵"
    },
    {
        "url": "https://www.1tamilmv.army/index.php?/forums/forum/10-predvd-dvdscr-cam-tc.xml/",
        "label": "🎥 PreDVD / DVDSCR / CAM / TC",
        "emoji": "🟡"
    },
]

TELEGRAM_TOKEN     = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_LOG_TOKEN = os.environ["TELEGRAM_LOG_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
CACHE_FILE         = "last_movies.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Image Extractor ──────────────────────────────────────
def extract_image_url(desc_html: str) -> str | None:
    """
    Extract the first ipsImage src from the description HTML.
    Handles both plain src and src inside CDATA/encoded HTML.
    """
    if not desc_html:
        return None

    # Match <img ... class="ipsImage" ... src="URL"> in any attribute order
    pattern = r'<img[^>]+class=["\'][^"\']*ipsImage[^"\']*["\'][^>]+src=["\']([^"\']+)["\']'
    match = re.search(pattern, desc_html, re.IGNORECASE)
    if match:
        return match.group(1)

    # Fallback: match src first, class second
    pattern_alt = r'<img[^>]+src=["\']([^"\']+)["\'][^>]+class=["\'][^"\']*ipsImage[^"\']*["\']'
    match = re.search(pattern_alt, desc_html, re.IGNORECASE)
    if match:
        return match.group(1)

    return None

# ── RSS Fetcher ──────────────────────────────────────────
def fetch_rss(feed: dict) -> dict:
    url   = feed["url"]
    label = feed["label"]

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Failed to fetch RSS [{label}]: {e}")
        return {}

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        print(f"❌ Failed to parse RSS XML [{label}]: {e}")
        print(response.text[:2000])
        return {}

    movies  = {}
    channel = root.find("channel")
    if channel is None:
        print(f"❌ No <channel> found in RSS feed [{label}].")
        return {}

    items = channel.findall("item")
    print(f"✅ [{label}] Found {len(items)} items in RSS feed")

    for item in items:
        title = item.findtext("title",       "").strip()
        link  = item.findtext("link",        "").strip()
        date  = item.findtext("pubDate",     "").strip()
        desc  = item.findtext("description", "").strip()

        # Also check for encoded description (common in RSS)
        if not desc:
            ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
            encoded = item.find("content:encoded", ns)
            if encoded is not None and encoded.text:
                desc = encoded.text.strip()

        image_url = extract_image_url(desc)

        if link:
            movies[link] = {
                "title":     title,
                "url":       link,
                "date":      date,
                "desc":      desc[:200] if desc else "",
                "feed":      label,
                "emoji":     feed["emoji"],
                "image_url": image_url,
            }

    return movies

# ── Load / Save cache ────────────────────────────────────
def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(data: dict):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Telegram ─────────────────────────────────────────────
def _post_telegram(token: str, chat_id: str, message: str):
    """Send a plain text/HTML message (no image)."""
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id":                  chat_id,
        "text":                     message,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True,
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        print(f"📨 Telegram message sent: {message[:60]}...")
    except Exception as e:
        print(f"❌ Telegram sendMessage error: {e}")

def _post_telegram_photo(token: str, chat_id: str, image_url: str, caption: str):
    """Send a photo with caption via sendPhoto."""
    url     = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {
        "chat_id":    chat_id,
        "photo":      image_url,
        "caption":    caption,
        "parse_mode": "HTML",
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        print(f"📸 Telegram photo sent: {caption[:60]}...")
        return True
    except Exception as e:
        print(f"⚠️  Telegram sendPhoto error (falling back to text): {e}")
        return False

def send_movie_alert(token: str, chat_id: str, info: dict):
    """
    Send movie alert with poster image if available,
    otherwise fall back to a plain text message.
    """
    caption = (
        f"{info['emoji']} <b>New Movie Added!</b>\n\n"
        f"📂 <i>{info['feed']}</i>\n\n"
        f"📌 <b>{info['title']}</b>\n"
        f"📅 {info['date']}\n"
        f"🔗 <a href='{info['url']}'>View Post</a>"
    )

    image_url = info.get("image_url")

    if image_url:
        success = _post_telegram_photo(token, chat_id, image_url, caption)
        if not success:
            # Fallback to plain message if photo fails
            _post_telegram(token, chat_id, caption)
    else:
        print(f"🖼️  No image found for: {info['title']}")
        _post_telegram(token, chat_id, caption)

def send_telegram(message: str):
    _post_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, message)

def send_telegram_log(message: str):
    _post_telegram(TELEGRAM_LOG_TOKEN, TELEGRAM_CHAT_ID, message)

# ── Main ──────────────────────────────────────────────────
def main():
    print("🔍 Checking RSS feeds for new movies...")
    send_telegram_log("🤖 Movie monitor GitHub Action run started \nRepo:Alert-Tg")

    cached = load_cache()
    all_current: dict = {}
    total_new = 0

    for feed in RSS_FEEDS:
        current = fetch_rss(feed)
        all_current.update(current)

        new_movies = {
            url: info
            for url, info in current.items()
            if url not in cached
        }

        if not new_movies:
            print(f"✅ [{feed['label']}] No new movies found.")
        else:
            print(f"🎉 [{feed['label']}] {len(new_movies)} new movie(s) found!")
            total_new += len(new_movies)

            for url, info in new_movies.items():
                send_movie_alert(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, info)

    if total_new == 0:
        print("✅ No new movies found across all feeds.")

    # Merge cached + all current and save
    merged = {**cached, **all_current}
    save_cache(merged)
    print(f"💾 Cache updated with {len(merged)} total movies.")

if __name__ == "__main__":
    main()
