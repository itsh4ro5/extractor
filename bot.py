import os, asyncio, threading, logging, traceback
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import pyromod.listen

# --- Import Apps ---
from apps.classplus import ClassplusApp
from apps.pw import PWExtractor 
from core.database import Database

# ---------- Logging Configuration ----------
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# ---------- ENV Variables ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
MONGO_URI = os.environ.get("MONGO_URI", "")

app_registry = {
    "cp": ClassplusApp(),
    "pw": PWExtractor()
}

db = Database(MONGO_URI)

# ==========================================
# 🌐 WEB SERVER (For 24/7 UptimeRobot Ping)
# ==========================================
web = Flask(__name__)
@web.route('/')
def index():
    return "🚀 GHOST Extractor Bot is Alive & Running 24/7!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web.run(host='0.0.0.0', port=port)

app = Client("extractor_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ==========================================
# 🟢 1. MAIN MENU (START COMMAND)
# ==========================================
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Login (ClassPlus)", callback_data="login_cp"),
         InlineKeyboardButton("🔑 Login (PW)", callback_data="login_pw")],
        [InlineKeyboardButton("🎓 Extract ClassPlus", callback_data="flow_cp")],
        [InlineKeyboardButton("📚 Extract PhysicsWallah", callback_data="flow_pw")],
        [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/itsh4ro5")]
    ])
    welcome_text = (
        "⚡ **Welcome to GHOST Extractor Bot** ⚡\n\n"
        "**Supported Platforms:** `cp`, `pw`\n\n"
        "👉 Pehle apna platform Login karein (agar tokens expire ho gaye hain).\n"
        "👉 Fir niche diye Extract buttons ka use karke file nikalein.\n\n"
        "🛑 **Emergency:** Running extraction rokne ke liye `/stop_extract` type karein."
    )
    await message.reply(welcome_text, reply_markup=keyboard)


# ==========================================
# 🛑 2. EMERGENCY STOP EXTRACTION COMMAND
# ==========================================
@app.on_message(filters.command("stop_extract"))
async def stop_extract_cmd(client, message):
    user_id = message.from_user.id
    pw_app = app_registry.get("pw")
    if pw_app:
        pw_app.set_stop(user_id)
        await message.reply("🛑 **Extraction stopping signal sent!** Current process khatam hote hi data save ho jayega.")
    else:
        await message.reply("⚠️ PW Extractor active nahi hai.")


# ==========================================
# 🔑 3. LOGIN FLOWS
# ==========================================
@app.on_callback_query(filters.regex("login_cp"))
async def cp_login(client, callback_query):
    await callback_query.answer()
    chat = callback_query.message.chat
    user_id = callback_query.from_user.id
    cp_app = app_registry["cp"]

    res = await chat.ask("🔑 **ClassPlus Login**\nSend `org_code*mobile` (For OTP) OR send your Auth Token:")
    text = res.text.strip()
    
    if '*' in text:
        try:
            org_code, mobile = text.split('*')
            otp_info = await cp_app.login_otp(org_code, mobile)
            otp_res = await chat.ask("📱 OTP bheja gaya hai. Kripya enter karein:")
            result = await cp_app.verify_otp(
                org_id=otp_info['org_id'], mobile=otp_info['mobile'],
                session_id=otp_info['session_id'], otp=otp_res.text.strip(),
                fingerprint_id=otp_info['fingerprint_id']
            )
            db.save_session(user_id, "cp", {"token": result['token'], "user": result['user']})
            await client.send_message(chat.id, "✅ **ClassPlus Login successful!**")
        except Exception as e:
            err_log = traceback.format_exc()
            await client.send_message(chat.id, f"❌ **CP Login failed! Error Log:**\n\n
http://googleusercontent.com/immersive_entry_chip/0
http://googleusercontent.com/immersive_entry_chip/1
http://googleusercontent.com/immersive_entry_chip/2
http://googleusercontent.com/immersive_entry_chip/3

Ab aapki TXT file ekdum saaf rahegi (sirf aur sirf encypted links ke saath), aur jo details hain (Batch ID, Video Count etc.) wo seedha Telegram file ke niche caption ban kar aayenge! 💥
