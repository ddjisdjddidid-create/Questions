import os
import json
import logging
import base64
import re
from io import BytesIO
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler, ContextTypes, filters
from groq import Groq
import aiohttp
from aiohttp import web
import asyncio
import fitz

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
REQUIRED_CHANNEL = "@TepthonHelp"
DEVELOPER_USERNAME = "Dev_Mido"
DEVELOPER_ID = None
SUPPORT_GROUP = "@TepthonHelp"

MEMBER_FILE = "member.json"
MEMORY_FILE = "memory.json"
BANNED_FILE = "banned.json"

groq_client = Groq(api_key=GROQ_API_KEY)

def load_json(filename):
    try:
        if os.path.exists(filename):
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    return {}

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_members():
    return load_json(MEMBER_FILE)

def save_members(data):
    save_json(MEMBER_FILE, data)

def load_memory():
    return load_json(MEMORY_FILE)

def save_memory(data):
    save_json(MEMORY_FILE, data)

def load_banned():
    data = load_json(BANNED_FILE)
    if isinstance(data, list):
        return data
    return []

def save_banned(data):
    save_json(BANNED_FILE, data)

def add_member(user_id, username, first_name):
    members = load_members()
    user_key = str(user_id)
    is_new = user_key not in members
    members[user_key] = {
        "username": username,
        "first_name": first_name,
        "joined": members.get(user_key, {}).get("joined", datetime.now().isoformat()),
        "last_active": datetime.now().isoformat(),
        "questions_count": members.get(user_key, {}).get("questions_count", 0)
    }
    save_members(members)
    return is_new

def increment_questions(user_id):
    members = load_members()
    user_key = str(user_id)
    if user_key in members:
        members[user_key]["questions_count"] = members[user_key].get("questions_count", 0) + 1
        save_members(members)

def get_user_memory(user_id):
    memory = load_memory()
    user_key = str(user_id)
    return memory.get(user_key, [])

def add_to_memory(user_id, role, content):
    memory = load_memory()
    user_key = str(user_id)
    if user_key not in memory:
        memory[user_key] = []
    memory[user_key].append({"role": role, "content": content})
    if len(memory[user_key]) > 20:
        memory[user_key] = memory[user_key][-20:]
    save_memory(memory)

def is_banned(user_id):
    banned = load_banned()
    return user_id in banned

def ban_user(user_id):
    banned = load_banned()
    if user_id not in banned:
        banned.append(user_id)
        save_banned(banned)

def unban_user(user_id):
    banned = load_banned()
    if user_id in banned:
        banned.remove(user_id)
        save_banned(banned)

def clean_markdown(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*[-*]\s+', '- ', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    return text.strip()

async def check_subscription(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id=REQUIRED_CHANNEL, user_id=user_id)
        return member.status in ['member', 'administrator', 'creator']
    except Exception as e:
        logger.error(f"Error checking subscription: {e}")
        return False

async def notify_developer(context: ContextTypes.DEFAULT_TYPE, user):
    try:
        members = load_members()
        total = len(members)
        msg = f"مستخدم جديد دخل البوت\n\nالاسم: {user.first_name}\nاليوزر: @{user.username if user.username else 'بدون'}\nالايدي: {user.id}\n\nاجمالي المستخدمين: {total}"
        dev_chat = await context.bot.get_chat(f"@{DEVELOPER_USERNAME}")
        await context.bot.send_message(chat_id=dev_chat.id, text=msg)
    except Exception as e:
        logger.error(f"Error notifying developer: {e}")

def get_subscription_keyboard():
    keyboard = [
        [InlineKeyboardButton("اشترك بالقناة", url=f"https://t.me/{REQUIRED_CHANNEL[1:]}")],
        [InlineKeyboardButton("تحقق من الاشتراك", callback_data="check_subscription")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("حل بالنصوص 📝", callback_data="solve_text")],
        [InlineKeyboardButton("حل سؤال بالصورة", callback_data="solve_image")],
        [InlineKeyboardButton("تواصل مع المطور", url=f"https://t.me/{DEVELOPER_USERNAME}"),
         InlineKeyboardButton("جروب الدعم", url=f"https://t.me/{SUPPORT_GROUP[1:]}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_rating_keyboard():
    keyboard = [
        [InlineKeyboardButton("👍", callback_data="rate_like"),
         InlineKeyboardButton("👎", callback_data="rate_dislike")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_developer_panel():
    keyboard = [
        [InlineKeyboardButton("احصائيات البوت", callback_data="dev_stats")],
        [InlineKeyboardButton("اذاعة للكل", callback_data="dev_broadcast")],
        [InlineKeyboardButton("حظر مستخدم", callback_data="dev_ban"),
         InlineKeyboardButton("الغاء حظر", callback_data="dev_unban")],
        [InlineKeyboardButton("ايقاف البوت", callback_data="dev_stop"),
         InlineKeyboardButton("تشغيل البوت", callback_data="dev_start")],
        [InlineKeyboardButton("اغلاق", callback_data="dev_close")]
    ]
    return InlineKeyboardMarkup(keyboard)

bot_active = True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if is_banned(user.id):
        await update.message.reply_text("انت محظور من استخدام البوت")
        return
    
    is_new = add_member(user.id, user.username, user.first_name)
    
    if is_new:
        await notify_developer(context, user)
    
    if not await check_subscription(user.id, context):
        await update.message.reply_text(
            f"يا صاحبي لازم تشترك بالقناة اول شي عشان تقدر تستخدم البوت\n\nاشترك هون: {REQUIRED_CHANNEL}",
            reply_markup=get_subscription_keyboard()
        )
        return
    
    welcome_msg = f"""اهلا وسهلا فيك يا {user.first_name} 

انا بوت مساعد الطلاب ، ابعثلي صورة السؤال وبحلهولك 📝.

من لم ينفعه العلم لم يأمن ضرر الجهل

اختار اللي بدك اياه من تحت :"""
    
    await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard())

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    query = update.callback_query
    await query.answer()
    user = query.from_user
    
    if is_banned(user.id):
        await query.answer("انت محظور", show_alert=True)
        return
    
    if query.data == "check_subscription":
        if await check_subscription(user.id, context):
            welcome_msg = f"""اهلا وسهلا فيك يا {user.first_name} 

انا بوت مساعد الطلاب ، ابعثلي صورة السؤال وبحلهولك 📝.

من لم ينفعه العلم لم يأمن ضرر الجهل

اختار اللي بدك اياه من تحت :"""
            await query.edit_message_text(welcome_msg, reply_markup=get_main_keyboard())
        else:
            await query.edit_message_text(
                f"لسه ما اشتركت يا صاحبي\n\nاشترك بالقناة: {REQUIRED_CHANNEL}",
                reply_markup=get_subscription_keyboard()
            )
    
    elif query.data == "solve_text":
        if not await check_subscription(user.id, context):
            await query.edit_message_text(
                f"لازم تشترك اول\n\nاشترك هون: {REQUIRED_CHANNEL}",
                reply_markup=get_subscription_keyboard()
            )
            return
        context.user_data['mode'] = 'text'
        await query.edit_message_text(
            "تمام، اكتبلي السؤال وان شاء الله بحلهولك",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع", callback_data="back_main")]])
        )
    
    elif query.data == "solve_image":
        if not await check_subscription(user.id, context):
            await query.edit_message_text(
                f"لازم تشترك اول\n\nاشترك هون: {REQUIRED_CHANNEL}",
                reply_markup=get_subscription_keyboard()
            )
            return
        context.user_data['mode'] = 'image'
        await query.edit_message_text(
            "تمام، ابعتلي صورة السؤال وان شاء الله بحلهولك",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع", callback_data="back_main")]])
        )
    
    elif query.data == "back_main":
        welcome_msg = f"""اهلا وسهلا فيك يا {user.first_name} 

انا بوت مساعد الطلاب ، ابعثلي صورة السؤال وبحلهولك 📝.

من لم ينفعه العلم لم يأمن ضرر الجهل

اختار اللي بدك اياه من تحت :"""
        await query.edit_message_text(welcome_msg, reply_markup=get_main_keyboard())
        context.user_data['mode'] = None
        context.user_data['waiting_broadcast'] = False
        context.user_data['waiting_ban'] = False
        context.user_data['waiting_unban'] = False
    
    elif query.data == "rate_like":
        await query.answer("شكرا على تقييمك", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=None)
    
    elif query.data == "rate_dislike":
        await query.answer("شكرا على ملاحظتك، سنحاول التحسين", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=None)
    
    elif query.data == "dev_stats":
        if user.username != DEVELOPER_USERNAME:
            await query.answer("مش مسموحلك", show_alert=True)
            return
        members = load_members()
        banned = load_banned()
        total_questions = sum(m.get("questions_count", 0) for m in members.values())
        stats_text = f"""احصائيات البوت:

عدد المستخدمين: {len(members)}
عدد المحظورين: {len(banned)}
عدد الاسئلة المحلولة: {total_questions}
حالة البوت: {'شغال' if bot_active else 'واقف'}"""
        await query.edit_message_text(stats_text, reply_markup=get_developer_panel())
    
    elif query.data == "dev_broadcast":
        if user.username != DEVELOPER_USERNAME:
            await query.answer("مش مسموحلك", show_alert=True)
            return
        context.user_data['waiting_broadcast'] = True
        await query.edit_message_text(
            "ابعتلي الرسالة اللي بدك تذيعها للكل",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("الغاء", callback_data="back_main")]])
        )
    
    elif query.data == "dev_ban":
        if user.username != DEVELOPER_USERNAME:
            await query.answer("مش مسموحلك", show_alert=True)
            return
        context.user_data['waiting_ban'] = True
        await query.edit_message_text(
            "ابعتلي ايدي المستخدم اللي بدك تحظره",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("الغاء", callback_data="back_main")]])
        )
    
    elif query.data == "dev_unban":
        if user.username != DEVELOPER_USERNAME:
            await query.answer("مش مسموحلك", show_alert=True)
            return
        context.user_data['waiting_unban'] = True
        banned = load_banned()
        if banned:
            banned_list = "\n".join([str(b) for b in banned])
            await query.edit_message_text(
                f"المحظورين:\n{banned_list}\n\nابعتلي ايدي المستخدم لالغاء حظره",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("الغاء", callback_data="back_main")]])
            )
        else:
            await query.edit_message_text(
                "لا يوجد محظورين",
                reply_markup=get_developer_panel()
            )
    
    elif query.data == "dev_stop":
        if user.username != DEVELOPER_USERNAME:
            await query.answer("مش مسموحلك", show_alert=True)
            return
        bot_active = False
        await query.edit_message_text("تم ايقاف البوت", reply_markup=get_developer_panel())
    
    elif query.data == "dev_start":
        if user.username != DEVELOPER_USERNAME:
            await query.answer("مش مسموحلك", show_alert=True)
            return
        bot_active = True
        await query.edit_message_text("تم تشغيل البوت", reply_markup=get_developer_panel())
    
    elif query.data == "dev_close":
        await query.delete_message()

async def handle_control_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.username != DEVELOPER_USERNAME:
        return
    
    await update.message.reply_text(
        "لوحة تحكم المطور",
        reply_markup=get_developer_panel()
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    user = update.effective_user
    
    if is_banned(user.id):
        await update.message.reply_text("انت محظور من استخدام البوت")
        return
    
    if not bot_active:
        await update.message.reply_text("البوت واقف هلق، جرب بعدين")
        return
    
    if not await check_subscription(user.id, context):
        await update.message.reply_text(
            f"لازم تشترك بالقناة اول شي\n\nاشترك هون: {REQUIRED_CHANNEL}",
            reply_markup=get_subscription_keyboard()
        )
        return
    
    add_member(user.id, user.username, user.first_name)
    processing_msg = await update.message.reply_text("عم بحل السؤال...")
    
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        photo_bytes = BytesIO()
        await file.download_to_memory(photo_bytes)
        photo_bytes.seek(0)
        
        image_base64 = base64.b64encode(photo_bytes.read()).decode('utf-8')
        
        user_memory = get_user_memory(user.id)
        messages = []
        for mem in user_memory[-10:]:
            messages.append(mem)
        
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": "انت مدرس خبير. حل هذا السؤال بالتفصيل وبطريقة سهلة الفهم. اكتب الاجابة بالعربي بدون اي تنسيق او نجوم او علامات. لو في اختيارات اختار الصح وقول ليه."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}}
            ]
        })
        
        response = groq_client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=messages,
            max_tokens=2000
        )
        
        answer = response.choices[0].message.content
        answer = clean_markdown(answer)
        
        add_to_memory(user.id, "user", "سؤال بالصورة")
        add_to_memory(user.id, "assistant", answer)
        increment_questions(user.id)
        
        await processing_msg.edit_text(f"الحل:\n\n{answer}", reply_markup=get_rating_keyboard())
        
    except Exception as e:
        logger.error(f"Error processing image: {e}")
        await processing_msg.edit_text("صار في مشكلة بحل السؤال، جرب كمان مرة او ابعثلي صورة اوضح")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    user = update.effective_user
    
    if is_banned(user.id):
        await update.message.reply_text("انت محظور من استخدام البوت")
        return
    
    if not bot_active:
        await update.message.reply_text("البوت واقف هلق، جرب بعدين")
        return
    
    if not await check_subscription(user.id, context):
        await update.message.reply_text(
            f"لازم تشترك بالقناة اول شي\n\nاشترك هون: {REQUIRED_CHANNEL}",
            reply_markup=get_subscription_keyboard()
        )
        return
    
    document = update.message.document
    if not document.file_name.lower().endswith('.pdf'):
        await update.message.reply_text("ابعتلي ملف PDF فقط")
        return
    
    add_member(user.id, user.username, user.first_name)
    processing_msg = await update.message.reply_text("عم بقرأ الملف وبحل السؤال...")
    
    try:
        file = await context.bot.get_file(document.file_id)
        pdf_bytes = BytesIO()
        await file.download_to_memory(pdf_bytes)
        pdf_bytes.seek(0)
        
        pdf_document = fitz.open(stream=pdf_bytes.read(), filetype="pdf")
        text = ""
        for page in pdf_document:
            text += page.get_text()
        pdf_document.close()
        
        if len(text) > 5000:
            text = text[:5000] + "..."
        
        user_memory = get_user_memory(user.id)
        messages = []
        for mem in user_memory[-10:]:
            messages.append(mem)
        
        messages.append({
            "role": "user",
            "content": f"انت مدرس خبير. حل الاسئلة في هذا النص بالتفصيل وبطريقة سهلة الفهم. اكتب الاجابة بالعربي بدون اي تنسيق او نجوم او علامات:\n\n{text}"
        })
        
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            max_tokens=3000
        )
        
        answer = response.choices[0].message.content
        answer = clean_markdown(answer)
        
        add_to_memory(user.id, "user", f"سؤال من PDF: {text[:200]}...")
        add_to_memory(user.id, "assistant", answer)
        increment_questions(user.id)
        
        if len(answer) > 4000:
            parts = [answer[i:i+4000] for i in range(0, len(answer), 4000)]
            await processing_msg.edit_text(f"الحل (جزء 1):\n\n{parts[0]}")
            for i, part in enumerate(parts[1:], 2):
                await update.message.reply_text(f"الحل (جزء {i}):\n\n{part}", reply_markup=get_rating_keyboard() if i == len(parts) else None)
        else:
            await processing_msg.edit_text(f"الحل:\n\n{answer}", reply_markup=get_rating_keyboard())
        
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        await processing_msg.edit_text("صار في مشكلة بقراءة الملف، جرب كمان مرة")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    text = update.message.text
    user = update.effective_user
    
    if text == "التحكم":
        await handle_control_command(update, context)
        return
    
    if is_banned(user.id):
        await update.message.reply_text("انت محظور من استخدام البوت")
        return
    
    if user.username == DEVELOPER_USERNAME:
        if context.user_data.get('waiting_broadcast'):
            context.user_data['waiting_broadcast'] = False
            members = load_members()
            success = 0
            fail = 0
            status_msg = await update.message.reply_text("جاري الاذاعة...")
            for user_id in members.keys():
                try:
                    await context.bot.send_message(chat_id=int(user_id), text=text)
                    success += 1
                except:
                    fail += 1
            await status_msg.edit_text(f"تم الاذاعة\n\nنجح: {success}\nفشل: {fail}")
            return
        
        if context.user_data.get('waiting_ban'):
            context.user_data['waiting_ban'] = False
            try:
                ban_id = int(text)
                ban_user(ban_id)
                await update.message.reply_text(f"تم حظر المستخدم {ban_id}", reply_markup=get_developer_panel())
            except:
                await update.message.reply_text("ايدي غير صحيح", reply_markup=get_developer_panel())
            return
        
        if context.user_data.get('waiting_unban'):
            context.user_data['waiting_unban'] = False
            try:
                unban_id = int(text)
                unban_user(unban_id)
                await update.message.reply_text(f"تم الغاء حظر المستخدم {unban_id}", reply_markup=get_developer_panel())
            except:
                await update.message.reply_text("ايدي غير صحيح", reply_markup=get_developer_panel())
            return
    
    if not bot_active:
        await update.message.reply_text("البوت واقف هلق، جرب بعدين")
        return
    
    if not await check_subscription(user.id, context):
        await update.message.reply_text(
            f"لازم تشترك اول شي\n\nاشترك هون: {REQUIRED_CHANNEL}",
            reply_markup=get_subscription_keyboard()
        )
        return
    
    mode = context.user_data.get('mode')
    
    if mode == 'text' or len(text) > 10:
        add_member(user.id, user.username, user.first_name)
        processing_msg = await update.message.reply_text("عم بحل السؤال...")
        
        try:
            user_memory = get_user_memory(user.id)
            messages = [{"role": "system", "content": "انت مدرس خبير تساعد الطلاب. اجب بالعربي بشكل واضح ومفصل بدون اي تنسيق او نجوم او علامات markdown."}]
            
            for mem in user_memory[-10:]:
                messages.append(mem)
            
            messages.append({"role": "user", "content": text})
            
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=2000
            )
            
            answer = response.choices[0].message.content
            answer = clean_markdown(answer)
            
            add_to_memory(user.id, "user", text)
            add_to_memory(user.id, "assistant", answer)
            increment_questions(user.id)
            
            await processing_msg.edit_text(f"الحل:\n\n{answer}", reply_markup=get_rating_keyboard())
            
        except Exception as e:
            logger.error(f"Error processing text: {e}")
            await processing_msg.edit_text("صار في مشكلة، جرب كمان مرة")
    else:
        await update.message.reply_text(
            "ابعتلي صورة السؤال او اكتبلي السؤال عشان احله",
            reply_markup=get_main_keyboard()
        )

async def handle_inline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query.query
    bot_info = await context.bot.get_me()
    
    results = [
        InlineQueryResultArticle(
            id="1",
            title="حل سؤال بالصورة",
            description="اضغط عشان ترسل رابط البوت وتحل سؤالك",
            input_message_content=InputTextMessageContent(
                message_text=f"بوت حل الاسئلة بالصور\n\nادخل على البوت وابعثلي صورة السؤال وبحلهولك:\n@{bot_info.username}"
            )
        ),
        InlineQueryResultArticle(
            id="2",
            title="تواصل مع المطور",
            description="للدعم الفني والاستفسارات",
            input_message_content=InputTextMessageContent(
                message_text=f"للتواصل مع المطور: @{DEVELOPER_USERNAME}\nجروب الدعم: {SUPPORT_GROUP}"
            )
        )
    ]
    
    await update.inline_query.answer(results, cache_time=60)

async def health_check(request):
    return web.Response(text="OK", status=200)

async def run_bot():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(InlineQueryHandler(handle_inline))
    
    web_app = web.Application()
    web_app.router.add_get('/', health_check)
    web_app.router.add_get('/health', health_check)
    
    runner = web.AppRunner(web_app)
    await runner.setup()
    
    port = int(os.environ.get('PORT', 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logger.info(f"Web server started on port {port}")
    
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Bot started polling...")
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(run_bot())
