import os
import asyncio
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from apps.classplus import ClassplusApp
from core.database import Database

# ---------- ENV ----------
BOT_TOKEN = os.environ["BOT_TOKEN"]
MONGO_URI = os.environ["MONGO_URI"]

app_registry = {
    "cp": ClassplusApp()   # और ऐप्स जोड़ें: "tb": TestbookApp()
}

db = Database(MONGO_URI)

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
        "👋 Welcome to Multi‑App Extractor!\n\n"
        "📌 Login:\n"
        "`/login <app> <token>`  (e.g. `/login cp eyJ...`)\n"
        "`/login <app> <orgCode> <mobile>` (OTP, currently unsupported)\n\n"
        "📚 List courses:\n"
        "`/courses <app>`\n\n"
        "📄 Extract course:\n"
        "`/extract <app> <courseId>`"
    , parse_mode='Markdown')

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = update.message.text.split()
    if len(args) < 3:
        await update.message.reply_text("Usage: /login <app> <token>")
        return
    app_name = args[1].lower()
    app = app_registry.get(app_name)
    if not app:
        await update.message.reply_text(f"❌ Unknown app '{app_name}'")
        return
    if len(args) == 3:  # token login
        token = args[2]
        try:
            result = await app.login_token(token)
            user_id = update.effective_user.id
            db.save_session(user_id, app_name, {"token": token, "user": result['user']})
            await update.message.reply_text(f"✅ Login Successful for {app_name}\nORG: {result['user'].get('orgCode', 'N/A')}")
        except Exception as e:
            await update.message.reply_text(f"❌ Login failed: {e}")
    else:
        # OTP login (not implemented due to API changes)
        await update.message.reply_text("OTP login is currently unavailable. Use token login.")

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
        msg = "📋 **Purchased Courses:**\n"
        for c in courses_list:
            msg += f"• `{c['id']}` - {c['name']} (₹{c['finalPrice']})\n"
        await update.message.reply_text(msg, parse_mode='Markdown')
        # store courses for later use (in memory)
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
        # Generate text file
        course_info = next((c for c in context.user_data.get('courses', []) if str(c['id']) == course_id), None)
        if not course_info:
            # fetch again
            courses = await app.get_courses(token)
            course_info = next((c for c in courses if str(c['id']) == course_id), None)
        txt = generate_content_txt(course_info, items, token, app)
        filename = f"course_{course_id}.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(txt)
        await update.message.reply_document(document=open(filename, 'rb'))
        db.add_task(user_id, "extract", {"app": app_name, "course_id": course_id, "items_count": len(items)})
        await msg.edit_text(f"✅ Extracted {len(items)} items. File sent.")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

def generate_content_txt(course_info, items, token, app):
    name = course_info['name']
    org = app.login_token.__self__ if hasattr(app, 'login_token') else "N/A"  # quick hack
    # हम orgCode को session से निकालेंगे
    lines = [
        f"{course_info.get('orgName', 'Nimbus Learning')} ClassPlus - {name}",
        f"🆔 Batch ID : {course_info['id']}",
        f"💸 Price : ₹{course_info['finalPrice']}",
        f"🎬 Videos: {course_info['resources']['videos']}  |  📁 Docs: {course_info['resources']['files']}",
        f"🏢 ORG : {course_info.get('orgCode', 'N/A')}",
        f"📝 TESTS : {course_info['resources']['tests']}",
        "=" * 50,
        f"{'Type':<8} {'Folder':<30} {'Name':<30} Link"
    ]
    # Need orgCode from session
    # Instead, we'll pass it as parameter
    for item in items:
        if item['type'] == 'video':
            link = asyncio.run(app.get_signed_url(token, item['contentHashId']))  # sync call
        else:
            link = item['url']
        lines.append(f"{item['type']:<8} {item['folder']:<30} {item['name']:<30} {link}")
    return "\n".join(lines)

# ---------- Main ----------
async def main():
    threading.Thread(target=run_web, daemon=True).start()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("login", login))
    app.add_handler(CommandHandler("courses", courses))
    app.add_handler(CommandHandler("extract", extract))
    print("Bot polling...")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
