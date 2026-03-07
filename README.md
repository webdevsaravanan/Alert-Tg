# 🎬 Movie Forum Alert Bot

Monitors the Tamil MV forum and sends Telegram alerts when new movies are added.

## Setup

### 1. Telegram Bot
- Chat with @BotFather → `/newbot` → copy your **Bot Token**
- Message your bot, then visit:  
  `https://api.telegram.org/bot<TOKEN>/getUpdates`  
  Copy your **Chat ID**

### 2. GitHub Secrets
Go to **Settings → Secrets and variables → Actions** and add:
| Secret | Value |
|--------|-------|
| `TELEGRAM_BOT_TOKEN` | Your bot token |
| `TELEGRAM_CHAT_ID` | Your chat ID |

### 3. Push this repo to GitHub
The workflow runs every 30 minutes automatically.

### 4. First Manual Run
Go to **Actions → Movie Forum Monitor → Run workflow** to test.

## Debugging
If no movies are found, uncomment the debug line in `scraper.py`:
```python
# print(response.text[:5000])
```
Then inspect the HTML and update the CSS selectors accordingly.

## Files
- `scraper.py` — main scraper + Telegram sender
- `requirements.txt` — Python dependencies
- `last_movies.json` — auto-updated cache of seen movies
- `.github/workflows/check_movies.yml` — GitHub Actions schedule
