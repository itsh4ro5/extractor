import os, asyncio, threading, logging
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

# Registry for all supported platforms
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

# ---------- Init Pyrogram Bot ----------
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
# 🔑 3. LOGIN FLOWS (Save to MongoDB)
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
            await client.send_message(chat.id, f"❌ CP Login failed: {e}")
    else:
        db.save_session(user_id, "cp", {"token": text, "user": "TokenUser"})
        await client.send_message(chat.id, "✅ **ClassPlus Token Saved!**")

@app.on_callback_query(filters.regex("login_pw"))
async def pw_login(client, callback_query):
    await callback_query.answer()
    chat = callback_query.message.chat
    user_id = callback_query.from_user.id

    ask_text = (
        "🔑 **PhysicsWallah Token Update**\n\n"
        "PW ka session 24 ghante me expire ho jata hai. Naya session yahan daalein.\n"
        "**Format:** `JWT_TOKEN * SESSION_COOKIE`\n\n"
        "*(Apna naya JWT token aur Session cookie ke beech me ek `*` lagakar bhejein)*"
    )
    res = await chat.ask(ask_text)
    text = res.text.strip()

    if '*' in text:
        try:
            jwt, cookie = text.split('*', 1)
            db.save_session(user_id, "pw", {"jwt": jwt.strip(), "cookie": cookie.strip()})
            await client.send_message(chat.id, "✅ **PW Tokens Successfully Updated in Database!**")
        except Exception as e:
            await client.send_message(chat.id, f"❌ Update failed: {e}")
    else:
        await client.send_message(chat.id, "❌ **Galat Format!** Kripya `JWT * COOKIE` format me bhejein.")


# ==========================================
# 🚀 4. EXTRACTION FLOWS (Read from MongoDB)
# ==========================================
@app.on_callback_query(filters.regex("flow_cp"))
async def cp_flow(client, callback_query):
    await callback_query.answer()
    chat = callback_query.message.chat
    user_id = callback_query.from_user.id
    cp_app = app_registry["cp"]

    session = db.get_session(user_id, "cp")
    if not session or not session.get('token'):
        return await client.send_message(chat.id, "❌ **Pehle Login kijiye!** 'Login (ClassPlus)' button dabayein.")

    token = session['token']
    msg = await client.send_message(chat.id, "⏳ Fetching purchased batches...")
    
    try:
        courses = await cp_app.get_courses(token)
        if not courses:
            return await msg.edit_text("❌ Aapke account me koi purchased batch nahi mila.")

        c_text = "".join([f"📌 **{c.get('name', 'Course')}**\n🆔 ID: `{c.get('id', '')}`\n\n" for c in courses])
        await msg.delete()
        
        batch_res = await chat.ask(f"✅ **Your Batches:**\n{c_text}👇 **Jis batch ka TXT chahiye, uski `ID` bhejein:**")
        course_id = batch_res.text.strip()
        
        extract_msg = await client.send_message(chat.id, f"⏳ Extracting Course ID `{course_id}`...")
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
        filename = f"{course_id}_CP.txt"
        
        with open(filename, 'w', encoding='utf-8') as f: f.write(txt)
        await client.send_document(chat.id, document=filename, caption=f"✅ Extracted {len(items)} items.")
        await extract_msg.delete()
        os.remove(filename)

    except Exception as e:
        await client.send_message(chat.id, f"❌ Error Occurred: {e}")


@app.on_callback_query(filters.regex("flow_pw"))
async def pw_flow(client, callback_query):
    await callback_query.answer()
    chat = callback_query.message.chat
    user_id = callback_query.from_user.id
    
    # 👤 Username capture karna (Header me daalne ke liye)
    user_name = f"@{callback_query.from_user.username}" if callback_query.from_user.username else callback_query.from_user.first_name
    
    pw_app = app_registry["pw"]

    # PW ke Tokens Database se nikalna
    session_data = db.get_session(user_id, "pw")
    if not session_data or not session_data.get('jwt') or not session_data.get('cookie'):
        return await client.send_message(chat.id, "❌ **Pehle Login kijiye!** 'Login (PW)' button dabakar naye tokens update karein.")

    jwt_token = session_data['jwt']
    session_cookie = session_data['cookie']

    res = await chat.ask("📚 **PhysicsWallah Extraction**\nKripya PW ka Batch URL ya ID bhejein:")
    target_id = res.text.strip()

    # ⚙️ Kya Extract karna hai?
    choice_msg = await chat.ask(
        "⚙️ **Kya Extract karna hai?**\n\n"
        "1️⃣ Main Content\n"
        "2️⃣ Khazana\n"
        "3️⃣ Both (Main + Khazana)\n\n"
        "👉 *Type 1, 2, or 3:*"
    )
    choice = choice_msg.text.strip()
    if choice not in ['1', '2', '3']: 
        choice = '3'

    msg = await client.send_message(chat.id, "⏳ Initializing Fast Scanner Engine...")

    try:
        # Pura data pw.py ko bhej rahe hain (user_id for stop flag and user_name for TXT header)
        file_name, error = await pw_app.extract(target_id, msg, jwt_token, session_cookie, choice, user_name, user_id)
        
        if file_name and os.path.exists(file_name):
            await msg.edit_text("✅ Encryption & Extraction Complete!")
            # Final Header caption ke sath upload
            await client.send_document(
                chat_id=chat.id, 
                document=file_name, 
                caption=f"🔒 **GHOST Encrypted Index File**\n📂 **Batch:** `{file_name.replace('.txt', '')}`"
            )
            os.remove(file_name)
        else:
            await msg.edit_text(f"❌ PW Extraction Failed:\n`{error}`")
            
    except Exception as e:
        await msg.edit_text(f"❌ Fatal PW Error:\n`{e}`")

# ---------- MAIN EXECUTION ----------
def main():
    threading.Thread(target=run_web, daemon=True).start()
    print("🔥 Web Server Started! Ready for UptimeRobot.")
    print("🤖 Starting GHOST Extractor Pyrogram Bot (Live Status, Control & Debugging)...")
    app.run()

if __name__ == "__main__":
    main()
