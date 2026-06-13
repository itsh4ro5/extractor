import os, asyncio, threading, logging
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import pyromod.listen  # Ye module chat.ask() ko enable karta hai

from apps.classplus import ClassplusApp
from core.database import Database

# ---------- Logging Configuration ----------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

# ---------- ENV Variables (HG Secrets) ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
MONGO_URI = os.environ.get("MONGO_URI", "")

app_registry = {"cp": ClassplusApp()}
db = Database(MONGO_URI)

# ---------- Web Server (Hugging Face) ----------
web = Flask(__name__)
@web.route('/')
def index():
    return "Pyrogram 2GB DRM Bot Running"
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
        [InlineKeyboardButton("Login (ClassPlus)", callback_data="btn_cp")],
        [InlineKeyboardButton("Developer", url="https://t.me/itsh4ro5")] 
    ])
    welcome_text = (
        "⚡ **Welcome to 2GB Pro Extractor Bot**\n\n"
        "Options:\n"
        "1. Click the button below to login.\n"
        "2. Use `/extract cp <course_id>` to get TXT.\n"
        "3. Use `/drm` to bulk download & upload HD videos to channel."
    )
    await message.reply(welcome_text, reply_markup=keyboard)

# ---------- Interactive Login Flow ----------
@app.on_callback_query(filters.regex("btn_cp"))
async def cp_login(client, callback_query):
    await callback_query.answer()
    chat = callback_query.message.chat
    user_id = callback_query.from_user.id
    
    # Pyromod magic: Ask directly in chat
    res = await chat.ask("🔑 Send `org_code*mobile` (For OTP) OR send your Auth Token:")
    text = res.text.strip()
    cp_app = app_registry["cp"]

    if '*' in text:
        try:
            org_code, mobile = text.split('*')
            otp_info = await cp_app.login_otp(org_code, mobile)
            
            otp_res = await chat.ask("📱 Send the OTP received on mobile:")
            otp = otp_res.text.strip()
            
            msg = await chat.send_message("⏳ Verifying...")
            
            result = await cp_app.verify_otp(
                org_id=otp_info['org_id'], mobile=otp_info['mobile'],
                session_id=otp_info['session_id'], otp=otp,
                fingerprint_id=otp_info['fingerprint_id']
            )
            db.save_session(user_id, "cp", {"token": result['token'], "user": result['user']})
            await msg.edit_text("✅ **Login successful!** You can now use `/extract cp <id>`.")
        except Exception as e:
            await chat.send_message(f"❌ OTP Login failed: {e}")
    else:
        token = text
        try:
            result = await cp_app.login_token(token)
            db.save_session(user_id, "cp", {"token": token, "user": result['user']})
            await chat.send_message("✅ **Token Login successful!**")
        except Exception as e:
            await chat.send_message(f"❌ Error: {e}")

# ---------- TXT File Extractor ----------
@app.on_message(filters.command("extract"))
async def extract_cmd(client, message):
    args = message.text.split()
    if len(args) < 3:
        return await message.reply("Usage: `/extract cp <courseId>`")
    
    app_name, course_id = args[1].lower(), args[2]
    cp_app = app_registry.get(app_name)
    user_id = message.from_user.id
    session = db.get_session(user_id, app_name)
    
    if not session or not session.get('token'):
        return await message.reply("❌ Please login first.")
        
    token = session['token']
    msg = await message.reply("⏳ Extracting content... Please wait.")
    
    try:
        items = await cp_app.extract_course(token, course_id)
        lines = ["📚 COURSE CONTENT:\n"]
        for item in items:
            name = str(item['name']).replace("|", "_").replace(":", "-").strip()
            if item['type'] == 'video':
                link = await cp_app.get_signed_url(token, item['contentHashId'])
                lines.append(f"[{name}] : {link}")
            else:
                lines.append(f"[{name} → PDF] : {item.get('url', '')}")
                
        txt = '\n'.join(lines)
        filename = f"{course_id}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(txt)
            
        await message.reply_document(document=filename, caption=f"✅ Extracted {len(items)} items.")
        await msg.delete()
        os.remove(filename)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

# ==========================================
# 🚀 2GB HD DRM UPLOADER FLOW (TXT -> CHANNEL)
# ==========================================
@app.on_message(filters.command("drm"))
async def drm_cmd(client, message):
    chat = message.chat
    
    try:
        # Step 1: Get TXT File
        txt_msg = await chat.ask("📄 **Step 1:** Please send the extracted `.txt` file.")
        if not txt_msg.document or not txt_msg.document.file_name.endswith('.txt'):
            return await chat.send_message("❌ Please send a valid .txt file. Run /drm again.")
            
        file_path = await txt_msg.download()
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.readlines()
        os.remove(file_path)
        
        parsed_links = []
        for line in content:
            if " : http" in line:
                parts = line.split(" : http", 1)
                name = parts[0].strip().replace("[", "").replace("]", "")
                url = "http" + parts[1].strip()
                is_pdf = "PDF" in name
                parsed_links.append({"name": name, "url": url, "is_pdf": is_pdf})
                
        if not parsed_links:
            return await chat.send_message("❌ No valid links found in the TXT file.")
            
        # Step 2: Get Index
        idx_msg = await chat.ask(f"✅ Found **{len(parsed_links)}** items.\n\n🔢 **Step 2:** Enter Starting Index Number (e.g., `1`):")
        start_idx = int(idx_msg.text.strip()) - 1
        
        # Step 3: Get Quality
        qual_msg = await chat.ask("⚙️ **Step 3:** Enter video quality (e.g., `480`, `720`, `1080`):")
        quality = qual_msg.text.strip().replace('p', '')
        
        # Step 4: Get Name
        name_msg = await chat.ask("👤 **Step 4:** Enter Extractor/Uploader Name (For caption):")
        ext_name = name_msg.text.strip()
        
        # Step 5: Get Chat ID
        chat_msg = await chat.ask("📢 **Step 5:** Enter Target Channel's Chat ID (e.g., `-100123456789`):\n*(Bot must be admin!)*")
        target_chat_id = int(chat_msg.text.strip())
        
        await chat.send_message("🚀 **All set!** The bulk download & 2GB upload process has started in the background.")
        
        # Background process start
        asyncio.create_task(process_drm_upload(client, chat.id, parsed_links, start_idx, quality, ext_name, target_chat_id))
    
    except Exception as e:
        await chat.send_message(f"❌ DRM Setup Cancelled or Failed: {e}")

async def process_drm_upload(client, user_chat_id, links, start_idx, quality, ext_name, target_chat_id):
    for i in range(start_idx, len(links)):
        item = links[i]
        item_name = item['name']
        url = item['url']
        caption = f"🎥 **{item_name}**\n\n📤 **Extracted by:** {ext_name}"
        
        status_msg = await client.send_message(user_chat_id, f"📥 Downloading ({i+1}/{len(links)}): {item_name}")
        
        try:
            if item['is_pdf']:
                filename = f"Doc_{i}.pdf"
                import aiohttp
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(url) as r:
                        with open(filename, 'wb') as f: f.write(await r.read())
                
                await status_msg.edit_text(f"📤 Uploading PDF to channel: {item_name}")
                await client.send_document(target_chat_id, document=filename, caption=caption)
                os.remove(filename)
                
            else:
                filename = f"Vid_{i}.mp4"
                fmt = f"bestvideo[height<={quality}]+bestaudio/best"
                cmd = ["yt-dlp", "--no-warnings", "-f", fmt, "--merge-output-format", "mp4", "-o", filename, url]
                
                process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await process.communicate()
                
                if process.returncode == 0 and os.path.exists(filename):
                    await status_msg.edit_text(f"📤 Uploading HD Video to channel: {item_name}...")
                    await client.send_video(target_chat_id, video=filename, caption=caption, supports_streaming=True)
                    os.remove(filename)
                else:
                    await client.send_message(user_chat_id, f"❌ Download failed for: {item_name}")
                    
            await status_msg.delete()
            
        except Exception as e:
            await client.send_message(user_chat_id, f"❌ Error on {item_name}: {e}")
            if os.path.exists(f"Vid_{i}.mp4"): os.remove(f"Vid_{i}.mp4")
            if os.path.exists(f"Doc_{i}.pdf"): os.remove(f"Doc_{i}.pdf")
            
    await client.send_message(user_chat_id, "🎉 **DRM Upload Task Completed Successfully!**")

# ---------- MAIN EXECUTION ----------
def main():
    # Web server start
    threading.Thread(target=run_web, daemon=True).start()
    print("Starting Pyrogram Bot...")
    # App run (handles event loop internally)
    app.run()

if __name__ == "__main__":
    main()
