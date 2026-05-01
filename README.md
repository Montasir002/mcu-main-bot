# mcu-main-bot
🎬 User-facing MCU Telegram Bot — browse &amp; download Marvel movies, series and episodes
# 🎬 MCU Bot — Main Bot

The user-facing Telegram bot for the MCU ecosystem. Lets users browse and download MCU movies, other movies, and series directly through Telegram.

---

## ✨ Features

- 🍿 **MCU Movies** — Browse and download Marvel Cinematic Universe films by phase
- 🎞 **Other Movies** — Browse and download non-MCU movies
- 📺 **Series** — Browse series, select a season, and download individual episodes
- 👤 **User Capture** — Every interaction automatically saves the user to Firestore
- 📁 **File ID System** — All files served via Telegram file IDs, zero re-uploading
- 🟢 **Always Online** — Built-in health endpoint keeps the server alive 24/7

---

## 🗂 Bot Structure

```
/start
├── 🍿 MCU Movies   → Select Movie → Poster + Download File(s)
├── 📺 Series       → Select Series → Select Season → Poster + Episodes
├── 🎞 Other Movies → Select Movie → Poster + Download File(s)
└── ➕ More
      ├── 📩 Contact Admin
      └── 🤖 More Bots
```

---

## 🛠 Tech Stack

- Python 3.11
- aiogram 3.x
- Google Cloud Firestore
- FastAPI + Uvicorn
- Hosted on Render (free tier)
- Kept alive by UptimeRobot

---

## 🔥 Firestore Structure

**Collection: `mcu_movies`**
```json
{
  "title": "Iron Man",
  "order": 1,
  "category": "mcu",
  "poster_file_id": "AgACAgI...",
  "caption": "Iron Man (2008) 🎬 Phase 1",
  "files": [
    {"label": "English 1080p", "file_id": "BQACAgI..."},
    {"label": "Arabic 720p",   "file_id": "BQACAgI..."}
  ]
}
```

**Collection: `mcu_series`**
```json
{
  "title": "WandaVision",
  "order": 1,
  "poster_file_id": "AgACAgI...",
  "seasons": {
    "1": {
      "label": "Season 1",
      "poster_file_id": "AgACAgI...",
      "episodes": [
        {"label": "E01 - Filmed Before a Live Studio Audience", "file_id": "BQACAgI..."}
      ]
    }
  }
}
```

---

## ⚙️ Environment Variables

| Variable | Description |
|---|---|
| `MAIN_BOT_TOKEN` | Main bot token from @BotFather |
| `ADMIN_ID` | Your personal Telegram user ID |
| `ADMIN_USERNAME` | Your Telegram username (without @) |
| `FIRESTORE_PROJECT` | Firebase project ID |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to service account JSON |

---

> This is a private passion project. Not affiliated with Marvel or Disney.
