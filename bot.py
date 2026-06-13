import os, asyncio, threading, logging, subprocess
from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import pyromod.listen

from apps.classplus import ClassplusApp
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

app_registry = {"cp": ClassplusApp()}
db = Database(MONGO_URI)

# ---------- Task Tracking Variables ----------
stop_flags = {}
active_processes = {}

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

# ---------- Helper: Get Video Duration ----------
def get_video_info(file_path):
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1", file_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return int(float(result.stdout.strip()))
    except Exception:
        return 0

# ---------- Stop Command ----------
@app.on_message(filters.command("stop"))
async def stop_cmd(client, message):
    user_id = message.from_user.id
    
    if user_id in stop_flags and not stop_flags[user_id]:
        stop_flags[user_id] = True 
        
        process = active_processes.get(user_id)
        if process:
            try:
                process.kill()
            except Exception:
                pass
                
        await message.reply("🛑 **Stop command received!** Current task aur aage ke downloads rok diye gaye hain.")
    else:
        await message.reply("⚠️ Koi active task nahi chal raha hai jise roka jaye.")

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
    user_id = message.from_user.id
    
    try:
        txt_msg = await chat.ask("📄 **Step 1:** Please send the extracted `.txt` file.")
        if not txt_msg.document or not txt_msg.document.file_name.endswith('.txt'):
            return await client.send_message(chat.id, "❌ Please send a valid .txt file. Run /drm again.")
            
        file_name = txt_msg.document.file_name
        batch_name = file_name.rsplit('.', 1)[0].strip() 
            
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
            return await client.send_message(chat.id, "❌ No valid links found in the TXT file.")
            
        idx_msg = await chat.ask(f"✅ Found **{len(parsed_links)}** items in `{batch_name}`.\n\n🔢 **Step 2:** Enter Starting Index Number (e.g., `1`):")
        start_idx = int(idx_msg.text.strip()) - 1
        
        qual_msg = await chat.ask("⚙️ **Step 3:** Enter video quality (e.g., `480`, `720`, `1080`):")
        quality = qual_msg.text.strip().replace('p', '')
        
        name_msg = await chat.ask("👤 **Step 4:** Enter Extractor/Uploader Name (For caption):")
        ext_name = name_msg.text.strip()
        
        chat_msg = await chat.ask("📢 **Step 5:** Enter Target Channel's Chat ID (e.g., `-100123456789`):\n*(Bot must be admin!)*")
        target_chat_id = int(chat_msg.text.strip())
        
        await client.send_message(chat.id, "🚀 **All set!** Process started. Agar kabhi task rokna ho toh `/stop` bhejein.")
        
        stop_flags[user_id] = False 
        
        asyncio.create_task(process_drm_upload(client, chat.id, user_id, parsed_links, start_idx, quality, ext_name, target_chat_id, batch_name))
    
    except Exception as e:
        await client.send_message(chat.id, f"❌ DRM Setup Cancelled or Failed: {e}")

async def process_drm_upload(client, user_chat_id, user_id, links, start_idx, quality, ext_name, target_chat_id, batch_name):
    for i in range(start_idx, len(links)):
        if stop_flags.get(user_id, False):
            await client.send_message(user_chat_id, "🛑 Uploading loop has been successfully stopped.")
            break
            
        item = links[i]
        topic = "General"
        title = item['name'] 
        
        if "]" in item['name']:
            parts = item['name'].split("]", 1)
            topic = parts[0].replace("[", "").strip()
            title = parts[1].strip()

        caption = (
            f"**Index:** {i+1}\n\n"
            f"**Title:** `{title}`\n\n"
            f"**Topic:** {topic}\n\n"
            f"**Batch:** {batch_name}\n\n"
            f"**Extracted by:** {ext_name}"
        )
        
        url = item['url']
        status_msg = await client.send_message(user_chat_id, f"📥 Downloading ({i+1}/{len(links)}): {title}")
        
        try:
            if item['is_pdf']:
                filename = f"Doc_{i}.pdf"
                import aiohttp
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(url) as r:
                        with open(filename, 'wb') as f: f.write(await r.read())
                
                if not stop_flags.get(user_id, False):
                    await status_msg.edit_text(f"📤 Uploading PDF: {title}")
                    upload_name = f"{title}.pdf"
                    os.rename(filename, upload_name)
                    
                    await client.send_document(target_chat_id, document=upload_name, caption=caption)
                    os.remove(upload_name)
                else:
                    os.remove(filename)
                
            else:
                filename = f"Vid_{i}.mp4"
                fmt = f"bestvideo[height<={quality}]+bestaudio/best/best"
                
                # FIXED: Added Headers to Bypass 403 Forbidden Error
                cmd = [
                    "yt-dlp", "--no-warnings", 
                    "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "--add-header", "Origin:https://web.classplusapp.com",
                    "--add-header", "Referer:https://web.classplusapp.com/",
                    "-f", fmt, 
                    "--merge-output-format", "mp4", 
                    "-o", filename, 
                    url
                ]
                
                process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                active_processes[user_id] = process 
                
                stdout, stderr = await process.communicate()
                active_processes[user_id] = None 
                
                if stop_flags.get(user_id, False):
                    if os.path.exists(filename): os.remove(filename)
                    await status_msg.delete()
                    continue
                
                if process.returncode == 0 and os.path.exists(filename):
                    await status_msg.edit_text(f"📤 Uploading HD Video: {title}...")
                    
                    duration = get_video_info(filename)
                    
                    thumb_name = f"Thumb_{i}.jpg"
                    os.system(f"ffmpeg -hide_banner -loglevel error -i '{filename}' -ss 00:00:02 -vframes 1 '{thumb_name}' -y")
                    actual_thumb = thumb_name if os.path.exists(thumb_name) else None
                    
                    upload_name = f"{title}.mp4"
                    os.rename(filename, upload_name)
                    
                    await client.send_video(
                        chat_id=target_chat_id, 
                        video=upload_name, 
                        caption=caption, 
                        duration=duration,          
                        thumb=actual_thumb,         
                        supports_streaming=True
                    )
                    
                    os.remove(upload_name)
                    if actual_thumb: os.remove(actual_thumb)
                else:
                    error_text = stderr.decode()[:200] if stderr else "Unknown Error"
                    await client.send_message(user_chat_id, f"❌ Download failed for: {title}\n**Reason:** `{error_text}`")
                    
            await status_msg.delete()
            
        except Exception as e:
            await client.send_message(user_chat_id, f"❌ Error on {title}: {e}")
            for f in [f"Vid_{i}.mp4", f"Doc_{i}.pdf", f"{title}.mp4", f"{title}.pdf", f"Thumb_{i}.jpg"]:
                if os.path.exists(f): os.remove(f)
            
    if not stop_flags.get(user_id, False):
        await client.send_message(user_chat_id, "🎉 **DRM Upload Task Completed Successfully!**")
    
    stop_flags[user_id] = False
    active_processes[user_id] = None
# ---------- MAIN EXECUTION ----------
def main():
    threading.Thread(target=run_web, daemon=True).start()
    print("Starting Pyrogram Bot...")
    app.run()

if __name__ == "__main__":
    main()
