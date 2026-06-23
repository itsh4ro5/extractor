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
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.ERROR)

# ---------- ENV Variables ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
MONGO_URI = os.environ.get("MONGO_URI", "")

# Registry
app_registry = {
    "cp": ClassplusApp(),
    "pw": PWExtractor()
}

# (Optional) DB for saving sessions, par ab nayi flow me iski utni zaroorat nahi hai
db = Database(MONGO_URI) if MONGO_URI else None

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
app = Client(
    "extractor_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# ==========================================
# 🟢 1. MAIN MENU (START COMMAND)
# ==========================================
@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎓 ClassPlus (Extract TXT)", callback_data="flow_cp")],
        [InlineKeyboardButton("📚 PhysicsWallah (Extract TXT)", callback_data="flow_pw")],
        [InlineKeyboardButton("👨‍💻 Developer", url="https://t.me/itsh4ro5")] 
    ])
    welcome_text = (
        "⚡ **Welcome to GHOST Extractor Bot** ⚡\n\n"
        "Ye bot aapko kisi bhi supported platform se videos aur notes ka **Encrypted TXT** nikal kar dega.\n\n"
        "👇 **Niche diye gaye buttons se apna platform chunein:**"
    )
    await message.reply(welcome_text, reply_markup=keyboard)


# ==========================================
# 🎓 2. CLASSPLUS INTERACTIVE FLOW
# ==========================================
@app.on_callback_query(filters.regex("flow_cp"))
async def cp_flow(client, callback_query):
    await callback_query.answer()
    chat = callback_query.message.chat
    cp_app = app_registry["cp"]

    # STEP 1: Ask for Credentials
    ask_text = (
        "🔑 **ClassPlus Login**\n\n"
        "Aap 2 tarikon se login kar sakte hain:\n"
        "1️⃣ **Naya Login:** Apna `org_code*mobile_number` bhejein.\n"
        "2️⃣ **Direct Login:** Apna pehle se maujood `Auth Token` bhejein.\n\n"
        "👉 *Kripya apna input niche type karein:*"
    )
    res = await chat.ask(ask_text)
    text = res.text.strip()
    
    token = None
    msg = await client.send_message(chat.id, "⏳ Verifying...")

    # STEP 2: Process Login
    try:
        if '*' in text:
            # Method 1: OTP Login
            org_code, mobile = text.split('*')
            otp_info = await cp_app.login_otp(org_code, mobile)
            
            await msg.delete()
            otp_res = await chat.ask(f"📱 OTP bheja gaya hai **{mobile}** par. Kripya OTP enter karein:")
            otp = otp_res.text.strip()
            
            msg = await client.send_message(chat.id, "⏳ Logging in...")
            result = await cp_app.verify_otp(
                org_id=otp_info['org_id'], mobile=otp_info['mobile'],
                session_id=otp_info['session_id'], otp=otp,
                fingerprint_id=otp_info['fingerprint_id']
            )
            token = result['token']
        else:
            # Method 2: Token Login
            token = text
            # Optional: Add a simple verification call here if your classplus.py supports it
            # result = await cp_app.login_token(token) 

        # STEP 3: Fetch Purchased Courses
        await msg.edit_text("✅ Login Successful! Fecthing your purchased batches...")
        courses = await cp_app.get_courses(token)
        
        if not courses:
            return await msg.edit_text("❌ Aapke account me koi purchased batch nahi mila.")

        course_list_text = ""
        for c in courses:
            # Adjusting keys based on typical Classplus API response
            c_name = c.get('name') or c.get('courseName', 'Unknown Course')
            c_id = c.get('id') or c.get('courseId', 'Unknown ID')
            course_list_text += f"📌 **{c_name}**\n🆔 ID: `{c_id}`\n\n"

        # Show Token and Courses
        dashboard_text = (
            f"✅ **CLASSPLUS DASHBOARD**\n\n"
            f"🔑 **Your Auth Token (Save it for future use):**\n`{token}`\n\n"
            f"📦 **Purchased Batches:**\n{course_list_text}"
            f"👇 **Ab jis batch ka TXT chahiye, uski `ID` niche type karke bhejein:**"
        )
        
        await msg.delete()
        batch_res = await chat.ask(dashboard_text)
        course_id = batch_res.text.strip()
        
        # STEP 4: Extract and Send TXT
        extract_msg = await client.send_message(chat.id, f"⏳ Extracting Course ID `{course_id}`... Please wait.")
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
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(txt)
            
        await client.send_document(chat.id, document=filename, caption=f"✅ Extracted {len(items)} items from Classplus.")
        await extract_msg.delete()
        os.remove(filename)

    except Exception as e:
        await msg.edit_text(f"❌ Error Occurred: {e}")


# ==========================================
# 📚 3. PHYSICSWALLAH INTERACTIVE FLOW
# ==========================================
@app.on_callback_query(filters.regex("flow_pw"))
async def pw_flow(client, callback_query):
    await callback_query.answer()
    chat = callback_query.message.chat
    pw_app = app_registry["pw"]

    # STEP 1: Ask for Batch URL / ID
    ask_text = (
        "📚 **PhysicsWallah Extraction**\n\n"
        "Kripya PW ka Batch URL ya 24-character ki Batch ID bhejein:\n"
        "*(Example: `https://www.pw.live/batches/...`)*"
    )
    res = await chat.ask(ask_text)
    target_id = res.text.strip()

    msg = await client.send_message(chat.id, "⏳ Scanning PW Links & Encrypting... Please wait.")

    # STEP 2: Extract and Send TXT
    try:
        file_name, error = await pw_app.extract(target_id, msg)
        
        if file_name and os.path.exists(file_name):
            await msg.edit_text("✅ Encryption & Extraction Complete! Uploading file...")
            await client.send_document(chat.id, document=file_name, caption="🔒 GHOST Encrypted Index File (PW)")
            os.remove(file_name)
        else:
            await msg.edit_text(f"❌ PW Extraction Failed: {error}")
            
    except Exception as e:
        await msg.edit_text(f"❌ Fatal PW Error: {e}")

# ---------- MAIN EXECUTION ----------
def main():
    threading.Thread(target=run_web, daemon=True).start()
    print("🔥 Web Server Started! Ready for UptimeRobot.")
    print("🤖 Starting GHOST Extractor Pyrogram Bot (Interactive Flow)...")
    app.run()

if __name__ == "__main__":
    main()
