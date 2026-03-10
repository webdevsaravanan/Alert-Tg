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
{
        "url": "https://www.1tamilmv.army/index.php?/forums/forum/19-web-series-tv-shows.xml/",
        "label": "🎥 WEB-SERIES / TV SHOWS",
        "emoji": "🟠"
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
    """Extract the first ipsImage src from the description HTML."""
    if not desc_html:
        return None

    pattern = r'<img[^>]+class=["\'][^"\']*ipsImage[^"\']*["\'][^>]+src=["\']([^"\']+)["\']'
    match = re.search(pattern, desc_html, re.IGNORECASE)
    if match:
        return match.group(1)

    pattern_alt = r'<img[^>]+src=["\']([^"\']+)["\'][^>]+class=["\'][^"\']*ipsImage[^"\']*["\']'
    match = re.search(pattern_alt, desc_html, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


# ── Magnet Link Extractor ────────────────────────────────
def extract_magnet_links(description: str) -> list:
    """
    Extract all magnet links from a description/HTML string.
    Returns a list of dicts: [{"url": "magnet:?...", "name": "filename"}, ...]
    Handles HTML-encoded ampersands (&amp;) automatically.
    """
    desc = (description
            .replace("&amp;", "&")
            .replace("&lt;",  "<")
            .replace("&gt;",  ">")
            .replace("&quot;", '"'))

    raw_magnets = re.findall(r'magnet:\?[^\s"\'<>\]]+', desc)

    results = []
    seen    = set()

    for magnet in raw_magnets:
        if magnet in seen:
            continue
        seen.add(magnet)

        dn_match = re.search(r'[?&]dn=([^&]+)', magnet)
        if dn_match:
            raw_name = dn_match.group(1)
            name = urllib.parse.unquote(raw_name.replace("+", " ")).strip()
            name = re.sub(r'^www\.\S+?\s+-\s+', '', name)
            name = re.sub(r'\.(mkv|mp4|avi|ts|m2ts)$', '', name, flags=re.IGNORECASE)
        else:
            name = f"Magnet #{len(results) + 1}"

        results.append({"url": magnet, "name": name})

    return results


# ── Magnet Size Filter ───────────────────────────────────
def extract_size_gb(name: str) -> float | None:
    """
    Parse file size from a magnet name string.
    Handles: 700MB, 400MB, 2.5GB, 1.4GB, 6GB, 4.7GB, etc.
    Returns size in GB as float, or None if not found.
    """
    match = re.search(r'([\d.]+)\s*(MB|GB)', name, re.IGNORECASE)
    if not match:
        return None
    value = float(match.group(1))
    unit  = match.group(2).upper()
    return value / 1024 if unit == "MB" else value


def pick_best_magnet(magnets: list) -> list:
    """
    From all magnets that carry a size in their name:
      1. Keep only those with size < 4.5 GB
      2. Return the single entry with the HIGHEST size among those

    This selects the best quality file that is still a reasonable download
    (e.g. picks 2.5 GB over 700 MB / 400 MB, but skips 6 GB / 4.7 GB).
    If no magnet has a parseable size under 4.5 GB, returns empty list.
    """
    sized = []
    for m in magnets:
        size = extract_size_gb(m["name"])
        if size is not None and size < 4.5:
            sized.append((size, m))

    if not sized:
        return []

    best = max(sized, key=lambda x: x[0])
    return [best[1]]


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

        image_url    = extract_image_url(desc)
        all_magnets  = extract_magnet_links(desc)
        best_magnets = pick_best_magnet(all_magnets)   # ← filtered list (0 or 1 item)

        if all_magnets:
            print(f"   🧲 {len(all_magnets)} total → {len(best_magnets)} selected for: {title[:55]}")

        if link:
            movies[link] = {
                "title":     title,
                "url":       link,
                "date":      date,
                "desc":      desc[:200] if desc else "",
                "feed":      label,
                "emoji":     feed["emoji"],
                "image_url": image_url,
                "magnets":   best_magnets,   # only the best one (or empty)
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


# ── Inline Keyboard Builder ───────────────────────────────
def build_inline_keyboard(magnets: list) -> dict | None:
    """
    Build a Telegram InlineKeyboardMarkup from the list of magnet dicts.

    Telegram does not accept magnet: URIs as button URLs, so each link is
    wrapped via https://magnet.link/?magnet=... (open redirect to torrent client).
    Button labels are capped at 50 chars.
    """
    if not magnets:
        return None

    rows = []
    for m in magnets:
        # Use the file size as the button label (e.g. "1.9GB", "700MB").
        # Fall back to a short slice of the full name if no size is found.
        size_match = re.search(r'([\d.]+\s*(?:MB|GB))', m["name"], re.IGNORECASE)
        label = size_match.group(1).strip() if size_match else m["name"][:30]

        # Append the magnet URI raw — no extra encoding.
        # The magnet already has its own percent-encoding (e.g. %20, %5B);
        # running urlencode() on top would double-encode it and break clients.
        redirect_url = "https://seedrproxy.mvcollection.workers.dev/magnet?link=" + m["url"]
        rows.append([{"text": f"🧲 {label}", "url": redirect_url}])

    return {"inline_keyboard": rows}


# ── Telegram Senders ─────────────────────────────────────
def _post_telegram(token: str, chat_id: str, message: str,
                   reply_markup: dict | None = None):
    """Send a plain text/HTML message."""
    # Telegram sendMessage: text max 4096 chars
    if len(message) > 4096:
        message = message[:4090] + "…"

    url     = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id":                  chat_id,
        "text":                     message,
        "parse_mode":               "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        print(f"📨 Telegram message sent: {message[:60]}...")
    except Exception as e:
        print(f"❌ Telegram sendMessage error: {e} | response: {r.text[:300]}")


def _post_telegram_photo(token: str, chat_id: str, image_url: str,
                         caption: str, reply_markup: dict | None = None) -> bool:
    """Send a photo with caption and optional inline keyboard via sendPhoto."""
    # Telegram sendPhoto: caption max 1024 chars
    if len(caption) > 1024:
        caption = caption[:1020] + "…"

    url     = f"https://api.telegram.org/bot{token}/sendPhoto"
    payload = {
        "chat_id":    chat_id,
        "photo":      image_url,
        "caption":    caption,
        "parse_mode": "HTML",
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)

    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        print(f"📸 Telegram photo sent: {caption[:60]}...")
        return True
    except Exception as e:
        print(f"⚠️  Telegram sendPhoto error (falling back to text): {e} | response: {r.text[:300]}")
        return False


def send_movie_alert(token: str, chat_id: str, info: dict):
    """
    Send a movie alert:
      • Photo + caption  (if poster image is available)
      • Inline keyboard buttons, one per selected magnet
      • Falls back to plain text if the photo send fails
    """
    magnets  = info.get("magnets", [])
    keyboard = build_inline_keyboard(magnets)

    magnet_line = (
        f"\n🧲 <b>Download link below ↓</b>"
        if magnets else "\n⚠️ No download link found yet"
    )

    # Escape & in title/url for valid HTML
    safe_title = info['title'].replace('&', '&amp;')
    safe_url   = info['url'].replace('&', '&amp;')

    caption = (
        f"{info['emoji']} <b>New Movie Added!</b>\n\n"
        f"📂 <i>{info['feed']}</i>\n\n"
        f"📌 <b>{safe_title}</b>\n"
        f"📅 {info['date']}\n"
        f"🔗 <a href='{safe_url}'>View Post</a>"
        f"{magnet_line}"
    )

    image_url = info.get("image_url")

    if image_url:
        success = _post_telegram_photo(token, chat_id, image_url, caption,
                                       reply_markup=keyboard)
        if not success:
            _post_telegram(token, chat_id, caption, reply_markup=keyboard)
    else:
        print(f"🖼️  No image found for: {info['title']}")
        _post_telegram(token, chat_id, caption, reply_markup=keyboard)


def send_telegram(message: str):
    _post_telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, message)

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
                send_movie_alert(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, info)

    if total_new == 0:
        print("✅ No new movies found across all feeds.")

    merged = {**cached, **all_current}
    save_cache(merged)
    print(f"💾 Cache updated with {len(merged)} total movies.")


if __name__ == "__main__":
    main()
