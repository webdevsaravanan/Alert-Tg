import requests
import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET

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

TELEGRAM_TOKEN     = "5484293358:AAEYKtkbRMHL7hH1uwitn7wWFt66QAeELuw"
TELEGRAM_LOG_TOKEN = "5555421412:AAENkGkuh_mCiwutN4Sm4UUDWDQItV-x-Hk"
TELEGRAM_CHAT_ID   = "885204688"
CACHE_FILE         = "last_movies.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Magnet Link Extractor ────────────────────────────────
def extract_magnet_links(description: str) -> list:
    """
    Extract all magnet links from a description/HTML string.
    Returns a list of dicts: [{"url": "magnet:?...", "name": "filename"}, ...]

    Handles HTML-encoded ampersands (&amp;) automatically.
    The display name is taken from the magnet's dn= parameter, URL-decoded
    and cleaned up (site watermark + file extension removed).
    """
    # Decode common HTML entities so &amp; → & before regex matching
    desc = (description
            .replace("&amp;", "&")
            .replace("&lt;",  "<")
            .replace("&gt;",  ">")
            .replace("&quot;", '"'))

    # Match every magnet URI – stops at whitespace, quotes or HTML tags
    raw_magnets = re.findall(r'magnet:\?[^\s"\'<>\]]+', desc)

    results = []
    seen    = set()

    for magnet in raw_magnets:
        if magnet in seen:
            continue
        seen.add(magnet)

        # Pull the dn= (display name) parameter from the magnet URI
        dn_match = re.search(r'[?&]dn=([^&]+)', magnet)
        if dn_match:
            raw_name = dn_match.group(1)
            # URL-decode %20 etc.; replace + with space
            name = urllib.parse.unquote(raw_name.replace("+", " ")).strip()
            # Strip "www.sitename.xyz - " watermark prefix
            name = re.sub(r'^www\.\S+?\s+-\s+', '', name)
            # Remove trailing file extension for a cleaner button label
            name = re.sub(r'\.(mkv|mp4|avi|ts|m2ts)$', '', name, flags=re.IGNORECASE)
        else:
            name = f"Magnet #{len(results) + 1}"

        results.append({"url": magnet, "name": name})

    return results


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

        if link:
            magnets = extract_magnet_links(desc)
            if magnets:
                print(f"   🧲 {len(magnets)} magnet(s) found for: {title[:60]}")

            movies[link] = {
                "title":   title,
                "url":     link,
                "date":    date,
                "desc":    desc[:200] if desc else "",
                "feed":    label,
                "emoji":   feed["emoji"],
                "magnets": magnets,       # ← NEW: list of {url, name}
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
def build_inline_keyboard(magnets: list) -> dict | None:
    """
    Build a Telegram InlineKeyboardMarkup from the list of magnet dicts.

    ⚠️  Telegram Bot API does NOT support magnet: URIs as button URLs.
        We wrap each magnet via https://magnet.link/ which is a well-known
        open redirect that accepts a `magnet` query parameter and hands
        the link off to the user's torrent client.

        Button label is capped at 50 chars to stay within Telegram limits.
        Each magnet gets its own row so labels never collide.
    """
    if not magnets:
        return None

    rows = []
    for m in magnets:
        label = m["name"]
        # Truncate long names
        if len(label) > 50:
            label = label[:47] + "…"

        # Wrap magnet URI so Telegram accepts it as a valid https URL
        redirect_url = (
            "https://magnet.link/?"
            + urllib.parse.urlencode({"magnet": m["url"]})
        )

        rows.append([{"text": f"🧲 {label}", "url": redirect_url}])

    return {"inline_keyboard": rows}


def _post_telegram(token: str, chat_id: str, message: str,
                   reply_markup: dict | None = None):
    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id":                  chat_id,
        "text":                     message,
        "parse_mode":               "HTML",
        "disable_web_page_preview": False,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        print(f"📨 Telegram sent: {message[:60]}...")
    except Exception as e:
        print(f"❌ Telegram error: {e}")


def send_telegram(message: str, magnets: list | None = None):
    keyboard = build_inline_keyboard(magnets) if magnets else None
    _post_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, message,
                   reply_markup=keyboard)

def send_telegram_log(message: str):
    _post_telegram(TELEGRAM_LOG_TOKEN, TELEGRAM_CHAT_ID, message)


# ── Main ──────────────────────────────────────────────────
def main():
    print("🔍 Checking RSS feeds for new movies...")
    send_telegram_log("🤖 Movie monitor GitHub Action run started \nRepo:Alert-Tg")

    cached      = load_cache()
    all_current = {}
    total_new   = 0

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
                magnets = info.get("magnets", [])

                # Show magnet count in the message body
                magnet_line = (
                    f"\n🧲 <b>{len(magnets)} download link(s) below ↓</b>"
                    if magnets else ""
                )

                msg = (
                    f"{info['emoji']} <b>New Movie Added!</b>\n\n"
                    f"📂 <i>{info['feed']}</i>\n\n"
                    f"📌 <b>{info['title']}</b>\n"
                    f"📅 {info['date']}\n"
                    f"🔗 <a href='{info['url']}'>View Post</a>"
                    f"{magnet_line}"
                )

                # Pass magnets → inline keyboard buttons appear below message
                send_telegram(msg, magnets=magnets)

    if total_new == 0:
        print("✅ No new movies found across all feeds.")

    # Merge old cache with everything seen this run and persist
    merged = {**cached, **all_current}
    save_cache(merged)
    print(f"💾 Cache updated with {len(merged)} total movies.")


if __name__ == "__main__":
    main()
