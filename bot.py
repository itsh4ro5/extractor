import os, asyncio, threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from apps.classplus import ClassplusApp
from core.database import Database

# ---------- ENV ----------
BOT_TOKEN = os.environ["BOT_TOKEN"]
MONGO_URI = os.environ["MONGO_URI"]

app_registry = {"cp": ClassplusApp()}
db = Database(MONGO_URI)

# Conversation states
WAIT_OTP = 1

# ---------- Flask ----------
web = Flask(__name__)
@web.route('/')
def index():
    return "Extractor Bot Running"
def run_web():
    web.run(host='0.0.0.0', port=7860)

# ---------- Bot Commands ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Classplus Extractor!\n\n"
        "🔐 **Login methods:**\n"
        "1. OTP: `/login cp iqvqn 6205734170`\n"
        "2. Token: `/login cp <your_token>`\n\n"
        "📚 `/courses cp` - list purchased courses\n"
        "📄 `/extract cp <courseId>` - extract content to text file"
    , parse_mode='Markdown')

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.split()
    if len(args) < 2:
        await update.message.reply_text("Usage:\n/`login cp <orgCode> <mobile>` for OTP\n/`login cp <token>` for direct token")
        return
    app_name = args[1].lower()
    app = app_registry.get(app_name)
    if not app:
        await update.message.reply_text("Unknown app")
        return
    user_id = update.effective_user.id

    if len(args) == 4:   # OTP login: /login cp iqvqn 6205734170
        org_code = args[2]
        mobile = args[3]
        try:
            otp_info = await app.login_otp(org_code, mobile)
            context.user_data['otp_info'] = otp_info
            context.user_data['app_name'] = app_name
            await update.message.reply_text("📱 OTP sent! Please send the OTP here.")
            return WAIT_OTP
        except Exception as e:
            await update.message.reply_text(f"❌ OTP send failed: {e}")
            return ConversationHandler.END

    elif len(args) == 3:   # Token login: /login cp eyJ...
        token = args[2]
        try:
            result = await app.login_token(token)
            db.save_session(user_id, app_name, {"token": token, "user": result['user']})
            await update.message.reply_text(f"✅ Token login successful!\nOrg: {result['user'].get('orgCode', 'N/A')}")
        except Exception as e:
            await update.message.reply_text(f"❌ Token login failed: {e}")
        return ConversationHandler.END

    else:
        await update.message.reply_text("Invalid arguments.")
        return ConversationHandler.END

async def otp_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    otp = update.message.text.strip()
    user_id = update.effective_user.id
    otp_info = context.user_data.get('otp_info')
    app_name = context.user_data.get('app_name')
    if not otp_info:
        await update.message.reply_text("Session expired. Start login again.")
        return ConversationHandler.END
    app = app_registry.get(app_name)
    try:
        result = await app.verify_otp(
            org_id=otp_info['org_id'],
            mobile=otp_info['mobile'],
            session_id=otp_info['session_id'],
            otp=otp,
            fingerprint_id=otp_info['fingerprint_id']
        )
        db.save_session(user_id, app_name, {"token": result['token'], "user": result['user']})
        await update.message.reply_text(f"✅ OTP verified! Login successful.\nOrg: {otp_info.get('org_name', 'N/A')}")
    except Exception as e:
        await update.message.reply_text(f"❌ OTP verification failed: {e}")
    finally:
        context.user_data.pop('otp_info', None)
        context.user_data.pop('app_name', None)
    return ConversationHandler.END

async def courses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.split()
    if len(args) < 2:
        await update.message.reply_text("Usage: /courses <app>")
        return
    app_name = args[1].lower()
    app = app_registry.get(app_name)
    if not app:
        await update.message.reply_text("Unknown app")
        return
    user_id = update.effective_user.id
    session = db.get_session(user_id, app_name)
    if not session or not session.get('token'):
        await update.message.reply_text("Please login first with /login")
        return
    token = session['token']
    try:
        courses_list = await app.get_courses(token)
        if not courses_list:
            await update.message.reply_text("No purchased courses found.")
            return
        msg = "📋 **Purchased Courses:**\n\n"
        for c in courses_list:
            msg += f"`{c['id']}` - {c['name']} (₹{c['finalPrice']})\n"
        await update.message.reply_text(msg, parse_mode='Markdown')
        context.user_data['courses'] = courses_list
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def extract(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.split()
    if len(args) < 3:
        await update.message.reply_text("Usage: /extract <app> <courseId>")
        return
    app_name = args[1].lower()
    course_id = args[2]
    app = app_registry.get(app_name)
    if not app:
        await update.message.reply_text("Unknown app")
        return
    user_id = update.effective_user.id
    session = db.get_session(user_id, app_name)
    if not session or not session.get('token'):
        await update.message.reply_text("Login first.")
        return
    token = session['token']
    msg = await update.message.reply_text("⏳ Extracting course content...")
    try:
        items = await app.extract_course(token, course_id)
        # Get course info for header
        courses = context.user_data.get('courses') or await app.get_courses(token)
        course_info = next((c for c in courses if str(c['id']) == course_id), None)
        if not course_info:
            # try to get from session's user orgCode
            org_code = session.get('user', {}).get('orgCode', '')
            course_info = {'id': course_id, 'name': 'Unknown', 'finalPrice': '?', 'resources': {'videos': 0, 'files': 0, 'tests': 0}, 'orgCode': org_code}
        txt = await generate_content_txt(course_info, items, token, app)
        filename = f"course_{course_id}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(txt)
        await update.message.reply_document(document=open(filename, 'rb'))
        db.add_task(user_id, "extract", {"app": app_name, "course_id": course_id, "items_count": len(items)})
        await msg.edit_text(f"✅ Extracted {len(items)} items. File sent.")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

async def generate_content_txt(course_info, items, token, app):
    lines = [
        f"{course_info.get('orgName', 'Nimbus Learning')} ClassPlus - {course_info['name']}",
        f"🆔 Batch ID : {course_info['id']}",
        f"💸 Price : ₹{course_info['finalPrice']}",
        f"🎬 Videos: {course_info['resources']['videos']}  |  📁 Docs: {course_info['resources']['files']}",
        f"🏢 ORG : {course_info.get('orgCode', 'N/A')}",
        f"📝 TESTS : {course_info['resources']['tests']}",
        "=" * 50,
        f"{'Type':<8} {'Folder':<30} {'Name':<30} Link"
    ]
    for item in items:
        if item['type'] == 'video':
            try:
                link = await app.get_signed_url(token, item['contentHashId'])
            except:
                link = f"ERROR: contentHashId={item['contentHashId']}"
        else:
            link = item['url']
        lines.append(f"{item['type']:<8} {item['folder']:<30} {item['name']:<30} {link}")
    return '\n'.join(lines)

# ---------- MAIN ----------
async def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()

    # Conversation handler for OTP
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('login', login)],
        states={WAIT_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, otp_input)]},
        fallbacks=[]
    )
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("courses", courses))
    app.add_handler(CommandHandler("extract", extract))

    print("Bot polling...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
