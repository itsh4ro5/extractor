import os, asyncio, threading, logging
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import pyromod.listen

# --- Import Apps ---
from apps.classplus import ClassplusApp
# Yahan PW ko import kiya gaya hai (jo humne pehle banaya tha)
from apps.pw import PWExtractor 
from core.database import Database

# ---------- Logging Configuration ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# ---------- ENV Variables ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
MONGO_URI = os.environ.get("MONGO_URI", "")

# Registry for all supported platforms
app_registry = {
    "cp": ClassplusApp(),
    "pw": PWExtractor()
}
db = Database(MONGO_URI)

# ---------- Web Server (Hugging Face / Render) ----------
web = Flask(__name__)
@web.route('/')
def index():
    return "GHOST Extractor Bot is Running Successfully!"
def run_web():
    web.run(host='0.0.0.0', port=7860)

# ---------- Init Pyrogram Bot ----------
app = Client(
    "extractor_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ---------- Start Command ----------
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Login (ClassPlus)", callback_data="btn_cp")],
        [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/itsh4ro5")] 
    ])
    welcome_text = (
        "⚡ **Welcome to GHOST Extractor Bot** ⚡\n\n"
        "**Supported Platforms:**\n"
        "🟢 `cp` - Classplus\n"
        "🟢 `pw` - PhysicsWallah / RareStudy\n\n"
        "**How to use:**\n"
        "1. Click the button below to login (Only for Classplus).\n"
        "2. To extract Classplus: `/extract cp <course_id>`\n"
        "3. To extract PW (Encrypted): `/extract pw <batch_url>`"
    )
    await message.reply(welcome_text, reply_markup=keyboard)

# ---------- Interactive Login Flow (Classplus) ----------
@app.on_callback_query(filters.regex("btn_cp"))
async def cp_login(client, callback_query):
    await callback_query.answer()
    chat = callback_query.message.chat
    user_id = callback_query.from_user.id
    
    res = await chat.ask("🔑 Send `org_code*mobile` (For OTP) OR send your Auth Token:")
    text = res.text.strip()
    cp_app = app_registry["cp"]

    if '*' in text:
        try:
            org_code, mobile = text.split('*')
            otp_info = await cp_app.login_otp(org_code, mobile)
            
            otp_res = await chat.ask("📱 Send the OTP received on mobile:")
            otp = otp_res.text.strip()
            
            msg = await client.send_message(chat.id, "⏳ Verifying...")
            
            result = await cp_app.verify_otp(
                org_id=otp_info['org_id'], mobile=otp_info['mobile'],
                session_id=otp_info['session_id'], otp=otp,
                fingerprint_id=otp_info['fingerprint_id']
            )
            db.save_session(user_id, "cp", {"token": result['token'], "user": result['user']})
            await msg.edit_text("✅ **Login successful!** You can now use `/extract cp <id>`.")
        except Exception as e:
            await client.send_message(chat.id, f"❌ OTP Login failed: {e}")
    else:
        token = text
        try:
            result = await cp_app.login_token(token)
            db.save_session(user_id, "cp", {"token": token, "user": result['user']})
            await client.send_message(chat.id, "✅ **Token Login successful!**")
        except Exception as e:
            await client.send_message(chat.id, f"❌ Error: {e}")

# ---------- Universal TXT File Extractor ----------
@app.on_message(filters.command("extract"))
async def extract_cmd(client, message):
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        return await message.reply("⚠️ **Usage:**\n👉 `/extract cp <courseId>`\n👉 `/extract pw <pw_batch_url>`")
    
    app_name, target_id = args[1].lower(), args[2].strip()
    
    if app_name not in app_registry:
        return await message.reply("❌ Invalid platform! Supported: `cp`, `pw`")
        
    user_id = message.from_user.id
    msg = await message.reply(f"⏳ Initializing Extractor for `{app_name.upper()}`... Please wait.")

    # ==============================
    # 1. CLASSPLUS EXTRACTION LOGIC
    # ==============================
    if app_name == "cp":
        cp_app = app_registry["cp"]
        session = db.get_session(user_id, "cp")
        if not session or not session.get('token'):
            return await msg.edit_text("❌ Please login to Classplus first using /start.")
            
        try:
            token = session['token']
            items = await cp_app.extract_course(token, target_id)
            lines = ["📚 COURSE CONTENT:\n"]
            for item in items:
                name = str(item['name']).replace("|", "_").replace(":", "-").strip()
                if item['type'] == 'video':
                    link = await cp_app.get_signed_url(token, item['contentHashId'])
                    lines.append(f"[{name}] : {link}")
                else:
                    lines.append(f"[{name} → PDF] : {item.get('url', '')}")
                    
            txt = '\n'.join(lines)
            filename = f"{target_id}_CP.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(txt)
                
            await message.reply_document(document=filename, caption=f"✅ Extracted {len(items)} items from Classplus.")
            await msg.delete()
            os.remove(filename)
        except Exception as e:
            await msg.edit_text(f"❌ Classplus Error: {e}")

    # ==============================
    # 2. PHYSICSWALLAH EXTRACTION LOGIC
    # ==============================
    elif app_name == "pw":
        pw_app = app_registry["pw"]
        
        # PW module directly takes URL and returns the text file name
        # Note: We pass 'msg' so it can edit the status live.
        try:
            file_name, error = await pw_app.extract(target_id, msg)
            if file_name and os.path.exists(file_name):
                await msg.edit_text("✅ Encryption & Extraction Complete! Uploading file...")
                await message.reply_document(document=file_name, caption="🔒 GHOST Encrypted Index File (PW)")
                os.remove(file_name)
            else:
                await msg.edit_text(f"❌ PW Extraction Failed: {error}")
        except Exception as e:
            await msg.edit_text(f"❌ Fatal PW Error: {e}")

# ---------- MAIN EXECUTION ----------
def main():
    threading.Thread(target=run_web, daemon=True).start()
    print("Starting GHOST Extractor Pyrogram Bot...")
    app.run()

if __name__ == "__main__":
    main()
