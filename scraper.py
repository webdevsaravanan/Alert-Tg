import requests
import json
import os
import xml.etree.ElementTree as ET

# ── Config ──────────────────────────────────────────────
RSS_URL = "https://www.1tamilmv.army/index.php?/forums/forum/11-web-hd-itunes-hd-bluray.xml/"
TELEGRAM_TOKEN = "5484293358:AAEYKtkbRMHL7hH1uwitn7wWFt66QAeELuw"
TELEGRAM_CHAT_ID = "885204688"
CACHE_FILE = "last_movies.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── RSS Fetcher ──────────────────────────────────────────
def fetch_rss():
    try:
        response = requests.get(RSS_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Failed to fetch RSS: {e}")
        return {}

    try:
        root = ET.fromstring(response.content)
    except ET.ParseError as e:
        print(f"❌ Failed to parse RSS XML: {e}")
        print(response.text[:2000])
        return {}

    movies = {}
    channel = root.find("channel")
    if channel is None:
        print("❌ No <channel> found in RSS feed.")
        return {}

    items = channel.findall("item")
    print(f"✅ Found {len(items)} items in RSS feed")

    for item in items:
        title = item.findtext("title", "").strip()
        link  = item.findtext("link",  "").strip()
        date  = item.findtext("pubDate", "").strip()
        desc  = item.findtext("description", "").strip()

        if link:
            movies[link] = {
                "title": title,
                "url":   link,
                "date":  date,
                "desc":  desc[:200] if desc else ""
            }

    return movies

# ── Load / Save cache ────────────────────────────────────
def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(data):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Telegram ─────────────────────────────────────────────
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        print(f"📨 Telegram sent: {message[:60]}...")
    except Exception as e:
        print(f"❌ Telegram error: {e}")

def send_telegram_log(message):
    url = f"https://api.telegram.org/bot5555421412:AAENkGkuh_mCiwutN4Sm4UUDWDQItV-x-Hk/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        print(f"📨 Telegram sent: {message[:60]}...")
    except Exception as e:
        print(f"❌ Telegram error: {e}")

# ── Main ──────────────────────────────────────────────────
def main():
    print("🔍 Checking RSS feed for new movies...")
    send_telegram_log("Movie monitor GitHub action run log")
    current = fetch_rss()
    cached  = load_cache()

    new_movies = {
        url: info
        for url, info in current.items()
        if url not in cached
    }

    if not new_movies:
        print("✅ No new movies found.")
    else:
        print(f"🎉 {len(new_movies)} new movie(s) found!")
        for url, info in new_movies.items():
            msg = (
                f"🎬 <b>New Movie Added!</b>\n\n"
                f"📌 <b>{info['title']}</b>\n"
                f"📅 {info['date']}\n"
                f"🔗 <a href='{info['url']}'>View Post</a>"
            )
            send_telegram(msg)

    # Merge and save
    merged = {**cached, **current}
    save_cache(merged)
    print(f"💾 Cache updated with {len(merged)} total movies.")

if __name__ == "__main__":
    main()
