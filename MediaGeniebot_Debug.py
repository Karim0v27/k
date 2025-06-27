
import logging
import os
import requests
import aiohttp
import yt_dlp

from aiohttp import web
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)

TOKEN = os.getenv("BOT_TOKEN")
OMDB_API_KEY = "73603e14"
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "")

if not TOKEN:
    raise Exception("❌ BOT_TOKEN не задан!")

logging.basicConfig(level=logging.INFO)

def translate_to_en(text):
    try:
        response = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "auto", "tl": "en", "dt": "t", "q": text},
            timeout=5
        )
        return response.json()[0][0][0]
    except Exception as e:
        logging.error(f"❌ Ошибка перевода: {e}")
        return text

def download_audio(query):
    output_dir = "downloads"
    os.makedirs(output_dir, exist_ok=True)
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'quiet': True,
        'noplaylist': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=True)['entries'][0]
            title = info['title']
            path = os.path.join(output_dir, f"{title}.mp3")
            return path if os.path.exists(path) else None
    except Exception as e:
        logging.error(f"❌ Ошибка загрузки: {e}")
        return None

async def music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("🎵 Введите название песни:
/music название")
        return
    await update.message.reply_text("⏳ Загружаю музыку...")
    file_path = download_audio(query)
    if file_path:
        with open(file_path, "rb") as audio:
            await update.message.reply_audio(audio)
        os.remove(file_path)
    else:
        await update.message.reply_text("❌ Не удалось загрузить.")

def get_movie_info(title):
    try:
        title_en = translate_to_en(title)
        res = requests.get("http://www.omdbapi.com/", params={
            "t": title_en, "apikey": OMDB_API_KEY, "plot": "short"
        })
        data = res.json()
        if data.get("Response") == "True":
            return (
                f"🎬 *{data['Title']}* ({data['Year']})\n"
                f"⭐ IMDb: {data.get('imdbRating')}\n"
                f"📖 {data.get('Plot')}\n"
                f"[IMDb](https://www.imdb.com/title/{data['imdbID']})",
                data.get("Poster")
            )
    except Exception as e:
        logging.error(f"OMDb ошибка: {e}")
    return None, None

async def movie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("🎬 Введите название фильма:
/movie название")
        return
    await update.message.reply_text("🔍 Ищу фильм...")
    info, poster = get_movie_info(query)
    if info:
        if poster and poster != "N/A":
            await update.message.reply_photo(poster, caption=info, parse_mode="Markdown")
        else:
            await update.message.reply_text(info, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Фильм не найден.")

async def get_anime_info(title):
    title_en = translate_to_en(title)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.jikan.moe/v4/anime?q={title_en}&limit=1") as r:
                data = await r.json()
                if data["data"]:
                    anime = data["data"][0]
                    return (
                        f"🎌 *{anime['title']}*\n"
                        f"⭐ {anime.get('score')}\n"
                        f"📖 {anime.get('synopsis')}\n"
                        f"[MyAnimeList]({anime['url']})",
                        anime["images"]["jpg"]["image_url"]
                    )
    except Exception as e:
        logging.error(f"Jikan ошибка: {e}")
    return None, None

async def anime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text("🎌 Введите название аниме:
/anime название")
        return
    await update.message.reply_text("🔍 Ищу аниме...")
    info, image = await get_anime_info(query)
    if info:
        if image:
            await update.message.reply_photo(photo=image, caption=info, parse_mode="Markdown")
        else:
            await update.message.reply_text(info, parse_mode="Markdown")
    else:
        await update.message.reply_text("❌ Аниме не найдено.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Я мультимедийный бот:\n"
        "/music <песня>\n/movie <фильм>\n/anime <аниме>",
        reply_markup=ReplyKeyboardMarkup([["🎵 Музыка"]], resize_keyboard=True)
    )

async def handle_music_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🎧 Напиши /music <название>")

async def telegram_webhook_handler(request):
    data = await request.json()
    update = Update.de_json(data, app.bot)
    await app.update_queue.put(update)
    logging.info("📩 Получено сообщение")
    return web.Response()

async def on_startup(app_aiohttp):
    if not RENDER_URL:
        logging.error("❌ RENDER_EXTERNAL_URL не указан")
        return
    webhook_url = RENDER_URL + "/webhook"
    await app.bot.set_webhook(webhook_url)
    logging.info(f"✅ Webhook установлен: {webhook_url}")

def main():
    global app
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("music", music))
    app.add_handler(CommandHandler("movie", movie))
    app.add_handler(CommandHandler("anime", anime))
    app.add_handler(MessageHandler(filters.Regex("🎵 Музыка"), handle_music_button))

    aio = web.Application()
    aio.router.add_post("/webhook", telegram_webhook_handler)
    aio.on_startup.append(on_startup)

    port = int(os.environ.get("PORT", 10000))
    web.run_app(aio, host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
