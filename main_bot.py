"""
MCU Main Bot
─────────────────────────────────────────
• User-facing bot for MCU movies & series
• Captures every user into Firestore mcu_users
• Serves files via Telegram file_id from Firestore mcu_files
• Keepalive /health endpoint for Render + UptimeRobot
"""

import asyncio
import logging
import os
import threading
from datetime import datetime, timezone

import uvicorn
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramForbiddenError, TelegramNotFound
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from dotenv import load_dotenv
from fastapi import FastAPI
from google.cloud import firestore

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────
MAIN_BOT_TOKEN = os.environ["MAIN_BOT_TOKEN"]
ADMIN_ID       = int(os.environ["ADMIN_ID"])
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")  # e.g. "your_username"
FIRESTORE_PROJ = os.environ["FIRESTORE_PROJECT"]
PORT           = int(os.environ.get("PORT", 10000))

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("main_bot")

# ── FastAPI keepalive ───────────────────────────────────────────────────────
web = FastAPI()

@web.get("/")
@web.get("/health")
async def health():
    return {"status": "alive", "bot": "MCU Main Bot"}

# ── Firestore ──────────────────────────────────────────────────────────────
db = firestore.Client(project=FIRESTORE_PROJ)

# ── Bot & Dispatcher ───────────────────────────────────────────────────────
bot = Bot(
    token=MAIN_BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher(storage=MemoryStorage())


# ══════════════════════════════════════════════════════════════════════════
# FIRESTORE — USER CAPTURE
# ══════════════════════════════════════════════════════════════════════════
# Collection : mcu_users
# Document ID: str(user_id)
# {
#   user_id, username, first_name, is_active,
#   joined_at, last_seen, message_count
# }

def upsert_user(user):
    """Save or update user in Firestore. Called on every interaction."""
    ref = db.collection("mcu_users").document(str(user.id))
    doc = ref.get()
    now = datetime.now(timezone.utc)
    if not doc.exists:
        ref.set({
            "user_id":       user.id,
            "username":      user.username,
            "first_name":    user.first_name,
            "is_active":     True,
            "is_vip":        False,
            "joined_at":     now,
            "last_seen":     now,
            "message_count": 1,
        })
        log.info(f"New user: {user.id} @{user.username}")
    else:
        ref.update({
            "last_seen":     now,
            "username":      user.username,
            "is_active":     True,
            "message_count": firestore.Increment(1),
        })


# ══════════════════════════════════════════════════════════════════════════
# FIRESTORE — CONTENT QUERIES
# ══════════════════════════════════════════════════════════════════════════
#
# Firestore structure expected:
#
# Collection: mcu_movies
#   Document ID: e.g. "iron_man"
#   {
#     "title":        "Iron Man",
#     "order":        1,
#     "category":     "mcu",          ← "mcu" or "other"
#     "poster_file_id": "AgACAgI...",
#     "caption":      "Iron Man (2008)\n🎬 Phase 1",
#     "files": [
#       {"label": "English 1080p", "file_id": "BQACAgI..."},
#       {"label": "Arabic 720p",   "file_id": "BQACAgI..."}
#     ]
#   }
#
# Collection: mcu_series
#   Document ID: e.g. "wandavision"
#   {
#     "title":          "WandaVision",
#     "order":          1,
#     "poster_file_id": "AgACAgI...",
#     "seasons": {
#       "1": {
#         "label":        "Season 1",
#         "poster_file_id": "AgACAgI...",
#         "episodes": [
#           {"label": "E01 - Filmed Before a Live Studio Audience", "file_id": "BQACAgI..."},
#           {"label": "E02 - Don't Touch That Dial",                "file_id": "BQACAgI..."}
#         ]
#       }
#     }
#   }

def get_movies(category: str) -> list[dict]:
    """Get all movies by category: 'mcu' or 'other'. Sorted by order."""
    docs = (
        db.collection("mcu_movies")
        .where("category", "==", category)
        .order_by("order")
        .stream()
    )
    return [{"id": d.id, **d.to_dict()} for d in docs]


def get_movie(doc_id: str) -> dict | None:
    doc = db.collection("mcu_movies").document(doc_id).get()
    return {"id": doc.id, **doc.to_dict()} if doc.exists else None


def get_series_list() -> list[dict]:
    docs = db.collection("mcu_series").order_by("order").stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]


def get_series(doc_id: str) -> dict | None:
    doc = db.collection("mcu_series").document(doc_id).get()
    return {"id": doc.id, **doc.to_dict()} if doc.exists else None


# ══════════════════════════════════════════════════════════════════════════
# KEYBOARD HELPERS
# ══════════════════════════════════════════════════════════════════════════

def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🍿 MCU Movies",   callback_data="cat:mcu")],
        [InlineKeyboardButton(text="📺 Series",        callback_data="cat:series")],
        [InlineKeyboardButton(text="🎞 Other Movies",  callback_data="cat:other")],
        [InlineKeyboardButton(text="➕ More",           callback_data="more")],
    ])


def movies_keyboard(movies: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=m["title"], callback_data=f"movie:{m['id']}")]
        for m in movies
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def series_keyboard(series_list: list[dict]) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=s["title"], callback_data=f"series:{s['id']}")]
        for s in series_list
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def seasons_keyboard(series_id: str, seasons: dict) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(
            text=season_data["label"],
            callback_data=f"season:{series_id}:{season_num}"
        )]
        for season_num, season_data in sorted(seasons.items(), key=lambda x: int(x[0]))
    ]
    buttons.append([InlineKeyboardButton(text="🔙 Back", callback_data="cat:series")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def more_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📩 Contact Admin", url=f"https://t.me/{ADMIN_USERNAME}")],
        [InlineKeyboardButton(text="🤖 More Bots",     callback_data="more_bots")],
        [InlineKeyboardButton(text="🔙 Back",           callback_data="home")],
    ])


# ══════════════════════════════════════════════════════════════════════════
# WELCOME MESSAGE
# ══════════════════════════════════════════════════════════════════════════

WELCOME_TEXT = (
    "🎬 <b>Welcome to the MCU Bot!</b>\n\n"
    "Your one-stop destination for Marvel Cinematic Universe movies and series.\n\n"
    "Use the buttons below to browse content 👇"
)


# ══════════════════════════════════════════════════════════════════════════
# HANDLERS — COMMANDS
# ══════════════════════════════════════════════════════════════════════════

@dp.message(Command("start"))
async def cmd_start(message: Message):
    upsert_user(message.from_user)
    await message.answer(WELCOME_TEXT, reply_markup=home_keyboard())


# ══════════════════════════════════════════════════════════════════════════
# HANDLERS — HOME & MORE
# ══════════════════════════════════════════════════════════════════════════

@dp.callback_query(F.data == "home")
async def cb_home(call: CallbackQuery):
    upsert_user(call.from_user)
    await call.message.delete()
    await call.message.answer(WELCOME_TEXT, reply_markup=home_keyboard())
    await call.answer()


@dp.callback_query(F.data == "more")
async def cb_more(call: CallbackQuery):
    upsert_user(call.from_user)
    await call.message.delete()
    await call.message.answer(
        "➕ <b>More</b>\n\nWhat would you like to do?",
        reply_markup=more_keyboard()
    )
    await call.answer()


@dp.callback_query(F.data == "more_bots")
async def cb_more_bots(call: CallbackQuery):
    upsert_user(call.from_user)
    # Add your other bot links here
    await call.answer("More bots coming soon!", show_alert=True)


# ══════════════════════════════════════════════════════════════════════════
# HANDLERS — MOVIE CATEGORIES
# ══════════════════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("cat:"))
async def cb_category(call: CallbackQuery):
    upsert_user(call.from_user)
    category = call.data.split(":")[1]

    if category == "series":
        series_list = get_series_list()
        if not series_list:
            await call.answer("No series available yet!", show_alert=True)
            return
        await call.message.delete()
        await call.message.answer(
            "📺 <b>Select a Series</b>",
            reply_markup=series_keyboard(series_list)
        )
    else:
        # mcu or other
        movies = get_movies(category)
        if not movies:
            await call.answer("No movies available yet!", show_alert=True)
            return
        label = "🍿 <b>MCU Movies</b>" if category == "mcu" else "🎞 <b>Other Movies</b>"
        await call.message.delete()
        await call.message.answer(
            f"{label}\n\n✅ Select a movie:",
            reply_markup=movies_keyboard(movies)
        )
    await call.answer()


# ══════════════════════════════════════════════════════════════════════════
# HANDLERS — MOVIE DETAIL
# ══════════════════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("movie:"))
async def cb_movie(call: CallbackQuery):
    upsert_user(call.from_user)
    movie_id = call.data.split(":")[1]
    movie    = get_movie(movie_id)

    if not movie:
        await call.answer("Movie not found!", show_alert=True)
        return

    await call.message.delete()

    # Send poster
    await call.message.answer_photo(
        photo=movie["poster_file_id"],
        caption=movie.get("caption", movie["title"]),
    )

    # Send each file
    for f in movie.get("files", []):
        await call.message.answer_document(
            document=f["file_id"],
            caption=f"📥 {f['label']}",
        )

    # Back button
    category = movie.get("category", "mcu")
    await call.message.answer(
        "Use the button below to go back 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔙 Back to Movies",
                callback_data=f"cat:{category}"
            )]
        ])
    )
    await call.answer()


# ══════════════════════════════════════════════════════════════════════════
# HANDLERS — SERIES
# ══════════════════════════════════════════════════════════════════════════

@dp.callback_query(F.data.startswith("series:"))
async def cb_series(call: CallbackQuery):
    upsert_user(call.from_user)
    series_id = call.data.split(":")[1]
    series    = get_series(series_id)

    if not series:
        await call.answer("Series not found!", show_alert=True)
        return

    seasons = series.get("seasons", {})
    if not seasons:
        await call.answer("No seasons available yet!", show_alert=True)
        return

    await call.message.delete()

    # Send series poster
    await call.message.answer_photo(
        photo=series["poster_file_id"],
        caption=f"📺 <b>{series['title']}</b>\n\n✅ Select a season:",
        reply_markup=seasons_keyboard(series_id, seasons)
    )
    await call.answer()


@dp.callback_query(F.data.startswith("season:"))
async def cb_season(call: CallbackQuery):
    upsert_user(call.from_user)
    _, series_id, season_num = call.data.split(":")
    series = get_series(series_id)

    if not series:
        await call.answer("Series not found!", show_alert=True)
        return

    season = series.get("seasons", {}).get(season_num)
    if not season:
        await call.answer("Season not found!", show_alert=True)
        return

    await call.message.delete()

    # Send season poster
    await call.message.answer_photo(
        photo=season["poster_file_id"],
        caption=(
            f"📺 <b>{series['title']}</b>\n"
            f"🎬 <b>{season['label']}</b>\n\n"
            f"Episodes below 👇"
        ),
    )

    # Send all episode files
    for ep in season.get("episodes", []):
        await call.message.answer_document(
            document=ep["file_id"],
            caption=f"▶️ {ep['label']}",
        )

    # Back button
    await call.message.answer(
        "Use the button below to go back 👇",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🔙 Back to Seasons",
                callback_data=f"series:{series_id}"
            )],
            [InlineKeyboardButton(
                text="🏠 Home",
                callback_data="home"
            )],
        ])
    )
    await call.answer()


# ══════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════

async def start_bot():
    log.info("Main bot polling started...")
    await dp.start_polling(bot)


def run_web():
    log.info(f"Web server starting on port {PORT}...")
    uvicorn.run(web, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    thread = threading.Thread(target=run_web, daemon=True)
    thread.start()
    asyncio.run(start_bot())
