import os, asyncio, threading, logging
from urllib.parse import quote
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from apps.classplus import ClassplusApp
from core.database import Database

# Logging configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
MONGO_URI = os.environ.get("MONGO_URI", "")

app_registry = {"cp": ClassplusApp()}
db = Database(MONGO_URI)

web = Flask(__name__)
@web.route('/')
def index():
    return "Extractor Bot Running"
def run_web():
    web.run(host='0.0.0.0', port=7860)

# ---------- Grid UI Flow ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Same UI Grid as shown in your video
    keyboard = [
        [InlineKeyboardButton("Adda247", callback_data="none"), InlineKeyboardButton("AppX", callback_data="none"), InlineKeyboardButton("ClassPlus", callback_data="btn_cp")],
        [InlineKeyboardButton("Edukemy", callback_data="none"), InlineKeyboardButton("Graphy", callback_data="none"), InlineKeyboardButton("IAS Hub", callback_data="none")],
        [InlineKeyboardButton("Khan GS", callback_data="none"), InlineKeyboardButton("LeanPrep", callback_data="none"), InlineKeyboardButton("OliveBoard", callback_data="none")],
        [InlineKeyboardButton("Physics Wallah", callback_data="none"), InlineKeyboardButton("StudyIQ", callback_data="none"), InlineKeyboardButton("Tarun Grover", callback_data="none")],
        [InlineKeyboardButton("TestBook", callback_data="none"), InlineKeyboardButton("TopRankers", callback_data="none"), InlineKeyboardButton("Utkarsh", callback_data="none")],
        [InlineKeyboardButton("Law Prep", callback_data="none"), InlineKeyboardButton("Virtuous", callback_data="none"), InlineKeyboardButton("TLS", callback_data="none")],
        [InlineKeyboardButton("Bot Plans", callback_data="none")],
        [InlineKeyboardButton("Without ID", callback_data="none")],
        [InlineKeyboardButton("Developer", url="https://t.me/itsh4ro5")] # Yahan apna username daal sakte ho
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    welcome_text = "⚡ **Select Platform**\n\nChoose an option below"
    
    if update.message:
        await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.message.edit_text(welcome_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "btn_cp":
        await query.message.reply_text("Send org_code*mobile or token")
        context.user_data['action'] = 'cp_login_creds'
    elif query.data == "none":
        await query.answer("Working on it... Not implemented yet.", show_alert=True)

# ---------- Login & OTP Flow ----------
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    action = context.user_data.get('action')
    text = update.message.text.strip()
    user_id = update.effective_user.id
    
    if action == 'cp_login_creds':
        if '*' in text:
            try:
                org_code, mobile = text.split('*')
                app = app_registry.get("cp")
                otp_info = await app.login_otp(org_code, mobile)
                context.user_data['otp_info'] = otp_info
                context.user_data['action'] = 'cp_login_otp'
                await update.message.reply_text("Send OTP")
            except Exception as e:
                await update.message.reply_text(f"❌ Error: {e}")
                context.user_data['action'] = None
        else:
            token = text
            app = app_registry.get("cp")
            try:
                result = await app.login_token(token)
                db.save_session(user_id, "cp", {"token": token, "user": result['user']})
                await update.message.reply_text(f"✅ Login successful!")
                context.user_data['action'] = None
            except Exception as e:
                await update.message.reply_text(f"❌ Error: {e}")
                context.user_data['action'] = None

    elif action == 'cp_login_otp':
        otp = text
        otp_info = context.user_data.get('otp_info')
        app = app_registry.get("cp")
        msg = await update.message.reply_text("⏳ Verifying...")
        try:
            result = await app.verify_otp(
                org_id=otp_info['org_id'],
                mobile=otp_info['mobile'],
                session_id=otp_info['session_id'],
                otp=otp,
                fingerprint_id=otp_info['fingerprint_id']
            )
            db.save_session(user_id, "cp", {"token": result['token'], "user": result['user']})
            context.user_data['action'] = None
            
            # Login hote hi courses list fetch karna
            courses_list = await app.get_courses(result['token'])
            if courses_list:
                c_msg = "✅ **Login successful! Your Courses:**\n\n"
                for c in courses_list:
                    c_msg += f"🆔 `{c['id']}` - {c['name']}\n"
                c_msg += "\nType `/extract cp <courseId>` to get content."
                await msg.edit_text(c_msg, parse_mode='Markdown')
            else:
                await msg.edit_text("❌ NO COURSES FOUND")
        except Exception as e:
            await msg.edit_text(f"❌ OTP verification failed: {e}")
            context.user_data['action'] = None

# Function me 'app' pass karna padega taaki API call ho sake
async def generate_content_txt(items, token, app):
    lines = ["📚 COURSE CONTENT:\n"]
    for item in items:
        name = str(item['name']).replace("|", "_").replace(":", "-").strip()
        folder = str(item.get('folder', '')).replace("/", " → ").strip()
        
        if item['type'] == 'video':
            try:
                # Classplus API se directly pura m3u8 link nikalna (Jisme token already hota hai)
                link = await app.get_signed_url(token, item['contentHashId'])
            except Exception as e:
                link = f"ERROR Fetching Link: {e}"
            
            if folder:
                lines.append(f"[{folder} ] {name} : {link}")
            else:
                lines.append(f"[{name}] : {link}")
        else:
            link = item.get('url', '')
            if folder:
                lines.append(f"[{folder}  → PDF ] {name} : {link}")
            else:
                lines.append(f"[{name} → PDF ] : {link}")
    return '\n'.join(lines)

# ---------- Extractor ----------
async def extract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.split()
    if len(args) < 3:
        await update.message.reply_text("Usage: /extract cp <courseId>")
        return
    app_name = args[1].lower()
    course_id = args[2]
    
    app = app_registry.get(app_name)
    user_id = update.effective_user.id
    session = db.get_session(user_id, app_name)
    
    if not session or not session.get('token'):
        await update.message.reply_text("Please login first.")
        return
        
    token = session['token']
    msg = await update.message.reply_text("⏳ Extracting course content... (This might take a while)")
    
    try:
        items = await app.extract_course(token, course_id)
        # Yahan 'app' ko pass kiya taaki upar wale function me API call ho sake
        txt = await generate_content_txt(items, token, app) 
        
        filename = f"{course_id}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(txt)
            
        await update.message.reply_document(document=open(filename, 'rb'))
        await msg.edit_text(f"✅ Extracted {len(items)} items. File sent.")
        os.remove(filename)
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")
def main():
    threading.Thread(target=run_web, daemon=True).start()
    
    # Ye proxy URL lagana zaruri hai Telegram block bypass karne ke liye
    CLOUDFLARE_URL = "https://proud-night-5540.itsh4r06.workers.dev/bot" 
    
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .base_url(CLOUDFLARE_URL) # <--- YE LINE MISSING THI
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("extract", extract))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("Bot polling...")
    app.run_polling()
