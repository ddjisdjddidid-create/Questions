import os
import json
import logging
import base64
import re
from io import BytesIO
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler, ContextTypes, filters
from telegram.constants import ChatType
from groq import Groq
import aiohttp
from aiohttp import web
import asyncio
import fitz
from gtts import gTTS
from langdetect import detect

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
SETTINGS_FILE = "settings.json"

groq_client = Groq(api_key=GROQ_API_KEY)

PERSONALITIES = {
    "teacher": {"name": "معلم 🕵🏻", "prompt": "انت معلم خبير ومتخصص. تشرح الامور بطريقة تعليمية واكاديمية مفصلة مع امثلة توضيحية."},
    "assistant": {"name": "مساعد 🧐", "prompt": "انت مساعد ذكي ومفيد. تجيب بشكل مباشر ومختصر وعملي."},
    "expert": {"name": "خبير 🎖️", "prompt": "انت خبير محترف في مجالك. تقدم تحليلات عميقة ومعلومات دقيقة ومتقدمة."},
    "friend": {"name": "صديق 👥", "prompt": "انت صديق ودود ومرح. تتكلم بطريقة غير رسمية وممتعة مع استخدام تعبيرات شبابية."}
}

LANGUAGES = {
    "ar": "عربي 🇸🇦", "en": "انجليزي 🇬🇧", "fr": "فرنسي 🇫🇷", "es": "اسباني 🇪🇸",
    "de": "الماني 🇩🇪", "it": "ايطالي 🇮🇹", "ru": "روسي 🇷🇺", "pt": "برتغالي 🇵🇹",
    "tr": "تركي 🇹🇷", "fa": "فارسي 🇮🇷", "ur": "اردو 🇵🇰", "hi": "هندي 🇮🇳",
    "zh": "صيني 🇨🇳", "ja": "ياباني 🇯🇵", "ko": "كوري 🇰🇷", "id": "اندونيسي 🇮🇩",
    "ms": "ماليزي 🇲🇾", "th": "تايلندي 🇹🇭", "vi": "فيتنامي 🇻🇳", "nl": "هولندي 🇳🇱",
    "pl": "بولندي 🇵🇱", "uk": "اوكراني 🇺🇦", "sv": "سويدي 🇸🇪", "el": "يوناني 🇬🇷"
}

ZODIAC_SIGNS = {
    "aries": "الحمل ♈", "taurus": "الثور ♉", "gemini": "الجوزاء ♊", "cancer": "السرطان ♋",
    "leo": "الاسد ♌", "virgo": "العذراء ♍", "libra": "الميزان ♎", "scorpio": "العقرب ♏",
    "sagittarius": "القوس ♐", "capricorn": "الجدي ♑", "aquarius": "الدلو ♒", "pisces": "الحوت ♓"
}

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

def load_settings():
    return load_json(SETTINGS_FILE)

def save_settings(data):
    save_json(SETTINGS_FILE, data)

def get_user_personality(user_id):
    settings = load_settings()
    return settings.get(str(user_id), {}).get("personality", None)

def set_user_personality(user_id, personality):
    settings = load_settings()
    if str(user_id) not in settings:
        settings[str(user_id)] = {}
    settings[str(user_id)]["personality"] = personality
    save_settings(settings)

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

def is_private_chat(update: Update) -> bool:
    return update.effective_chat.type == ChatType.PRIVATE

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
        [InlineKeyboardButton("تحقق من الاشتراك ✅", callback_data="check_subscription")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_personality_keyboard():
    keyboard = [
        [InlineKeyboardButton("معلم 🕵🏻", callback_data="personality_teacher"),
         InlineKeyboardButton("مساعد 🧐", callback_data="personality_assistant")],
        [InlineKeyboardButton("خبير 🎖️", callback_data="personality_expert"),
         InlineKeyboardButton("صديق 👥", callback_data="personality_friend")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("حل النصوص 📝", callback_data="solve_text"),
         InlineKeyboardButton("حل Pdf 🖤", callback_data="solve_pdf")],
        [InlineKeyboardButton("حل الاسئله بالصوره 🖼️", callback_data="solve_image")],
        [InlineKeyboardButton("جروب المساعده 🧰", url=f"https://t.me/{SUPPORT_GROUP[1:]}"),
         InlineKeyboardButton("مطور البوت 🎖️", url=f"https://t.me/{DEVELOPER_USERNAME}")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_pdf_details_keyboard():
    keyboard = [
        [InlineKeyboardButton("نعم ✅", callback_data="pdf_details_yes"),
         InlineKeyboardButton("لا ❌", callback_data="pdf_details_no")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_vip_keyboard():
    keyboard = [
        [InlineKeyboardButton("ترجمة 🌍", callback_data="vip_translate"),
         InlineKeyboardButton("أبراج ♈", callback_data="vip_horoscope")],
        [InlineKeyboardButton("قصص 📖", callback_data="vip_stories"),
         InlineKeyboardButton("ألعاب 🎮", callback_data="vip_games")],
        [InlineKeyboardButton("نص لصوت 🔊", callback_data="vip_tts")],
        [InlineKeyboardButton("رجوع 🔙", callback_data="back_main")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_language_keyboard(page=0):
    lang_list = list(LANGUAGES.items())
    per_page = 8
    start = page * per_page
    end = start + per_page
    current_langs = lang_list[start:end]
    
    keyboard = []
    row = []
    for i, (code, name) in enumerate(current_langs):
        row.append(InlineKeyboardButton(name, callback_data=f"translate_to_{code}"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀️ السابق", callback_data=f"lang_page_{page-1}"))
    if end < len(lang_list):
        nav_row.append(InlineKeyboardButton("التالي ▶️", callback_data=f"lang_page_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    keyboard.append([InlineKeyboardButton("رجوع 🔙", callback_data="vip_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_zodiac_keyboard():
    keyboard = []
    signs = list(ZODIAC_SIGNS.items())
    row = []
    for i, (code, name) in enumerate(signs):
        row.append(InlineKeyboardButton(name, callback_data=f"zodiac_{code}"))
        if len(row) == 3:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("رجوع 🔙", callback_data="vip_menu")])
    return InlineKeyboardMarkup(keyboard)

def get_story_keyboard():
    keyboard = [
        [InlineKeyboardButton("مغامرة 🗺️", callback_data="story_adventure")],
        [InlineKeyboardButton("رعب 👻", callback_data="story_horror")],
        [InlineKeyboardButton("رومانسي 💕", callback_data="story_romance")],
        [InlineKeyboardButton("خيال علمي 🚀", callback_data="story_scifi")],
        [InlineKeyboardButton("رجوع 🔙", callback_data="vip_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_game_keyboard():
    keyboard = [
        [InlineKeyboardButton("اسئلة ذكاء 🧠", callback_data="game_iq")],
        [InlineKeyboardButton("الغاز 🔮", callback_data="game_riddles")],
        [InlineKeyboardButton("معلومات عامة 📚", callback_data="game_trivia")],
        [InlineKeyboardButton("رجوع 🔙", callback_data="vip_menu")]
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

def get_story_choice_keyboard(story_id):
    keyboard = [
        [InlineKeyboardButton("الخيار الاول 1️⃣", callback_data=f"story_choice_{story_id}_1")],
        [InlineKeyboardButton("الخيار الثاني 2️⃣", callback_data=f"story_choice_{story_id}_2")],
        [InlineKeyboardButton("انهاء القصة 🔚", callback_data="vip_stories")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_game_answer_keyboard(correct_answer):
    keyboard = [
        [InlineKeyboardButton("أ", callback_data=f"game_answer_a_{correct_answer}"),
         InlineKeyboardButton("ب", callback_data=f"game_answer_b_{correct_answer}")],
        [InlineKeyboardButton("ج", callback_data=f"game_answer_c_{correct_answer}"),
         InlineKeyboardButton("د", callback_data=f"game_answer_d_{correct_answer}")],
        [InlineKeyboardButton("سؤال جديد 🔄", callback_data="game_trivia")]
    ]
    return InlineKeyboardMarkup(keyboard)

bot_active = True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        return
    
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
    
    personality = get_user_personality(user.id)
    if not personality:
        await update.message.reply_text(
            "قم بتحديد شخصيتي 🎭",
            reply_markup=get_personality_keyboard()
        )
        return
    
    welcome_msg = f"""اهلا وسهلا فيك يا {user.first_name} 

انا بوت مساعد الطلاب ، ابعثلي صورة السؤال وبحلهولك 📝.

من لم ينفعه العلم لم يأمن ضرر الجهل

اختار اللي بدك اياه من تحت :"""
    
    await update.message.reply_text(welcome_msg, reply_markup=get_main_keyboard())

async def vipfree_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_private_chat(update):
        return
    
    user = update.effective_user
    
    if is_banned(user.id):
        await update.message.reply_text("انت محظور من استخدام البوت")
        return
    
    if not await check_subscription(user.id, context):
        await update.message.reply_text(
            f"لازم تشترك اول\n\nاشترك هون: {REQUIRED_CHANNEL}",
            reply_markup=get_subscription_keyboard()
        )
        return
    
    await update.message.reply_text(
        "🌟 مميزات VIP المجانية 🌟\n\nاختار الميزة اللي بدك اياها:",
        reply_markup=get_vip_keyboard()
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    query = update.callback_query
    
    if not is_private_chat(update):
        await query.answer()
        return
    
    await query.answer()
    user = query.from_user
    
    if is_banned(user.id):
        await query.answer("انت محظور", show_alert=True)
        return
    
    if query.data == "check_subscription":
        if await check_subscription(user.id, context):
            personality = get_user_personality(user.id)
            if not personality:
                await query.edit_message_text(
                    "قم بتحديد شخصيتي 🎭",
                    reply_markup=get_personality_keyboard()
                )
            else:
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
    
    elif query.data.startswith("personality_"):
        personality = query.data.replace("personality_", "")
        set_user_personality(user.id, personality)
        
        success_msg = await query.edit_message_text("تم بنجاح صنع مساعدك الخاص ✅")
        await asyncio.sleep(3)
        
        welcome_msg = f"""اهلا وسهلا فيك يا {user.first_name} 

انا بوت مساعد الطلاب ، ابعثلي صورة السؤال وبحلهولك 📝.

من لم ينفعه العلم لم يأمن ضرر الجهل

اختار اللي بدك اياه من تحت :"""
        await success_msg.edit_text(welcome_msg, reply_markup=get_main_keyboard())
    
    elif query.data == "solve_text":
        if not await check_subscription(user.id, context):
            await query.edit_message_text(
                f"لازم تشترك اول\n\nاشترك هون: {REQUIRED_CHANNEL}",
                reply_markup=get_subscription_keyboard()
            )
            return
        context.user_data['mode'] = 'text'
        await query.edit_message_text(
            "تمام، اكتبلي السؤال وان شاء الله بحلهولك 📝",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع 🔙", callback_data="back_main")]])
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
            "تمام، ابعتلي صورة السؤال وان شاء الله بحلهولك 🖼️",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع 🔙", callback_data="back_main")]])
        )
    
    elif query.data == "solve_pdf":
        if not await check_subscription(user.id, context):
            await query.edit_message_text(
                f"لازم تشترك اول\n\nاشترك هون: {REQUIRED_CHANNEL}",
                reply_markup=get_subscription_keyboard()
            )
            return
        context.user_data['mode'] = 'pdf'
        await query.edit_message_text(
            "تمام، ابعتلي ملف PDF وان شاء الله بحلهولك 📄",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع 🔙", callback_data="back_main")]])
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
        context.user_data['waiting_translate'] = False
        context.user_data['waiting_tts'] = False
    
    elif query.data == "vip_menu":
        await query.edit_message_text(
            "🌟 مميزات VIP المجانية 🌟\n\nاختار الميزة اللي بدك اياها:",
            reply_markup=get_vip_keyboard()
        )
    
    elif query.data == "vip_translate":
        context.user_data['mode'] = 'translate'
        await query.edit_message_text(
            "✍️ اكتبلي النص اللي بدك اترجمه:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع 🔙", callback_data="vip_menu")]])
        )
    
    elif query.data.startswith("lang_page_"):
        page = int(query.data.replace("lang_page_", ""))
        await query.edit_message_text(
            "🌍 قم باختيار لغة الترجمة:",
            reply_markup=get_language_keyboard(page)
        )
    
    elif query.data.startswith("translate_to_"):
        target_lang = query.data.replace("translate_to_", "")
        text_to_translate = context.user_data.get('text_to_translate', '')
        
        if not text_to_translate:
            await query.edit_message_text(
                "لم يتم العثور على نص للترجمة. اكتب النص اولا.",
                reply_markup=get_vip_keyboard()
            )
            return
        
        processing_msg = await query.edit_message_text("جاري الترجمة... 🔄")
        
        try:
            messages = [
                {"role": "system", "content": f"انت مترجم محترف. ترجم النص التالي الى {LANGUAGES.get(target_lang, target_lang)} فقط بدون اي شرح او اضافات."},
                {"role": "user", "content": text_to_translate}
            ]
            
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=2000
            )
            
            translated = response.choices[0].message.content
            translated = clean_markdown(translated)
            
            await processing_msg.edit_text(
                f"🌍 الترجمة الى {LANGUAGES.get(target_lang, target_lang)}:\n\n{translated}",
                reply_markup=get_vip_keyboard()
            )
        except Exception as e:
            logger.error(f"Translation error: {e}")
            await processing_msg.edit_text(
                "حصل خطأ في الترجمة، جرب كمان مرة",
                reply_markup=get_vip_keyboard()
            )
    
    elif query.data == "vip_horoscope":
        await query.edit_message_text(
            "♈ اختار برجك:",
            reply_markup=get_zodiac_keyboard()
        )
    
    elif query.data.startswith("zodiac_"):
        sign = query.data.replace("zodiac_", "")
        sign_name = ZODIAC_SIGNS.get(sign, sign)
        
        processing_msg = await query.edit_message_text(f"جاري تحضير توقعات {sign_name}... 🔮")
        
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            messages = [
                {"role": "system", "content": "انت خبير ابراج ومنجم محترف. اكتب توقعات يومية شاملة ومفصلة بالعربي."},
                {"role": "user", "content": f"اكتب توقعات برج {sign_name} لهذا اليوم {today}. اذكر الحب والعمل والصحة والمال والنصيحة."}
            ]
            
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=1000
            )
            
            horoscope = response.choices[0].message.content
            horoscope = clean_markdown(horoscope)
            
            await processing_msg.edit_text(
                f"🔮 توقعات {sign_name} لهذا اليوم:\n\n{horoscope}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("برج اخر ♈", callback_data="vip_horoscope")],
                    [InlineKeyboardButton("رجوع 🔙", callback_data="vip_menu")]
                ])
            )
        except Exception as e:
            logger.error(f"Horoscope error: {e}")
            await processing_msg.edit_text(
                "حصل خطأ، جرب كمان مرة",
                reply_markup=get_vip_keyboard()
            )
    
    elif query.data == "vip_stories":
        await query.edit_message_text(
            "📖 اختار نوع القصة:",
            reply_markup=get_story_keyboard()
        )
    
    elif query.data.startswith("story_") and not query.data.startswith("story_choice_"):
        story_type = query.data.replace("story_", "")
        story_types = {
            "adventure": "مغامرة مثيرة",
            "horror": "رعب ومخيفة",
            "romance": "رومانسية",
            "scifi": "خيال علمي"
        }
        
        processing_msg = await query.edit_message_text("جاري كتابة القصة... ✍️")
        
        try:
            messages = [
                {"role": "system", "content": "انت كاتب قصص محترف. اكتب قصة قصيرة تفاعلية بالعربي. في نهاية كل جزء اعطي خيارين للقارئ ليختار."},
                {"role": "user", "content": f"اكتب بداية قصة {story_types.get(story_type, 'مغامرة')} تفاعلية قصيرة ومشوقة. في النهاية اعطي خيارين."}
            ]
            
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=1000
            )
            
            story = response.choices[0].message.content
            story = clean_markdown(story)
            context.user_data['current_story'] = story
            context.user_data['story_type'] = story_type
            
            await processing_msg.edit_text(
                f"📖 القصة:\n\n{story}",
                reply_markup=get_story_choice_keyboard(story_type)
            )
        except Exception as e:
            logger.error(f"Story error: {e}")
            await processing_msg.edit_text(
                "حصل خطأ، جرب كمان مرة",
                reply_markup=get_story_keyboard()
            )
    
    elif query.data.startswith("story_choice_"):
        parts = query.data.split("_")
        choice = parts[-1]
        
        previous_story = context.user_data.get('current_story', '')
        story_type = context.user_data.get('story_type', 'adventure')
        
        processing_msg = await query.edit_message_text("جاري اكمال القصة... ✍️")
        
        try:
            messages = [
                {"role": "system", "content": "انت كاتب قصص محترف. اكمل القصة بناء على اختيار القارئ. في نهاية كل جزء اعطي خيارين جديدين."},
                {"role": "user", "content": f"القصة السابقة:\n{previous_story}\n\nاختار القارئ الخيار رقم {choice}. اكمل القصة واعطي خيارين جديدين."}
            ]
            
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=1000
            )
            
            story = response.choices[0].message.content
            story = clean_markdown(story)
            context.user_data['current_story'] = story
            
            await processing_msg.edit_text(
                f"📖 تكملة القصة:\n\n{story}",
                reply_markup=get_story_choice_keyboard(story_type)
            )
        except Exception as e:
            logger.error(f"Story continuation error: {e}")
            await processing_msg.edit_text(
                "حصل خطأ، جرب كمان مرة",
                reply_markup=get_story_keyboard()
            )
    
    elif query.data == "vip_games":
        await query.edit_message_text(
            "🎮 اختار نوع اللعبة:",
            reply_markup=get_game_keyboard()
        )
    
    elif query.data in ["game_iq", "game_riddles", "game_trivia"]:
        game_type = query.data.replace("game_", "")
        game_prompts = {
            "iq": "اسئلة ذكاء",
            "riddles": "الغاز",
            "trivia": "معلومات عامة"
        }
        
        processing_msg = await query.edit_message_text("جاري تحضير السؤال... 🎯")
        
        try:
            messages = [
                {"role": "system", "content": "انت مقدم العاب ذكاء. اكتب سؤال مع 4 خيارات (أ، ب، ج، د) وحدد الجواب الصحيح في النهاية بصيغة: الجواب الصحيح: [الحرف]"},
                {"role": "user", "content": f"اعطني سؤال {game_prompts.get(game_type, 'ذكاء')} صعب مع 4 خيارات بالعربي."}
            ]
            
            response = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=messages,
                max_tokens=500
            )
            
            question = response.choices[0].message.content
            question = clean_markdown(question)
            
            correct = "a"
            if "الجواب الصحيح: أ" in question or "الجواب الصحيح: ا" in question:
                correct = "a"
            elif "الجواب الصحيح: ب" in question:
                correct = "b"
            elif "الجواب الصحيح: ج" in question:
                correct = "c"
            elif "الجواب الصحيح: د" in question:
                correct = "d"
            
            display_question = re.sub(r'الجواب الصحيح:.*', '', question).strip()
            context.user_data['current_question'] = display_question
            context.user_data['correct_answer'] = correct
            
            await processing_msg.edit_text(
                f"🎯 السؤال:\n\n{display_question}",
                reply_markup=get_game_answer_keyboard(correct)
            )
        except Exception as e:
            logger.error(f"Game error: {e}")
            await processing_msg.edit_text(
                "حصل خطأ، جرب كمان مرة",
                reply_markup=get_game_keyboard()
            )
    
    elif query.data.startswith("game_answer_"):
        parts = query.data.split("_")
        user_answer = parts[2]
        correct_answer = parts[3]
        
        if user_answer == correct_answer:
            await query.edit_message_text(
                f"✅ اجابة صحيحة! ممتاز!\n\n{context.user_data.get('current_question', '')}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("سؤال جديد 🔄", callback_data="game_trivia")],
                    [InlineKeyboardButton("رجوع 🔙", callback_data="vip_games")]
                ])
            )
        else:
            answer_map = {"a": "أ", "b": "ب", "c": "ج", "d": "د"}
            await query.edit_message_text(
                f"❌ اجابة خاطئة!\n\nالجواب الصحيح: {answer_map.get(correct_answer, correct_answer)}\n\n{context.user_data.get('current_question', '')}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("سؤال جديد 🔄", callback_data="game_trivia")],
                    [InlineKeyboardButton("رجوع 🔙", callback_data="vip_games")]
                ])
            )
    
    elif query.data == "vip_tts":
        context.user_data['mode'] = 'tts'
        await query.edit_message_text(
            "🔊 اكتبلي النص اللي بدك احوله لصوت:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("رجوع 🔙", callback_data="vip_menu")]])
        )
    
    elif query.data == "pdf_details_yes":
        context.user_data['pdf_waiting_details'] = True
        await query.edit_message_text(
            "📝 اكتبلي التفاصيل اللي بدك اياها:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("الغاء ❌", callback_data="pdf_details_no")]])
        )
    
    elif query.data == "pdf_details_no":
        context.user_data['pdf_waiting_details'] = False
        pdf_data = context.user_data.get('pending_pdf')
        if pdf_data:
            await process_pdf(update, context, pdf_data, None)
        else:
            await query.edit_message_text(
                "لم يتم العثور على ملف PDF",
                reply_markup=get_main_keyboard()
            )
    
    elif query.data == "rate_like":
        await query.answer("شكرا على تقييمك 💚", show_alert=True)
        await query.edit_message_reply_markup(reply_markup=None)
    
    elif query.data == "rate_dislike":
        await query.answer("شكرا على ملاحظتك، سنحاول التحسين 💙", show_alert=True)
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
    if not is_private_chat(update):
        return
    
    user = update.effective_user
    if user.username != DEVELOPER_USERNAME:
        return
    
    await update.message.reply_text(
        "لوحة تحكم المطور",
        reply_markup=get_developer_panel()
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    
    if not is_private_chat(update):
        return
    
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
    processing_msg = await update.message.reply_text("عم بحل السؤال... 🔄")
    
    try:
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        photo_bytes = BytesIO()
        await file.download_to_memory(photo_bytes)
        photo_bytes.seek(0)
        
        image_base64 = base64.b64encode(photo_bytes.read()).decode('utf-8')
        
        personality = get_user_personality(user.id)
        personality_prompt = PERSONALITIES.get(personality, PERSONALITIES["teacher"])["prompt"]
        
        user_memory = get_user_memory(user.id)
        messages = []
        for mem in user_memory[-10:]:
            messages.append(mem)
        
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": f"{personality_prompt} حل هذا السؤال بالتفصيل وبطريقة سهلة الفهم. اكتب الاجابة بالعربي بدون اي تنسيق او نجوم او علامات. لو في اختيارات اختار الصح وقول ليه."},
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

async def process_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE, pdf_bytes, details):
    user = update.effective_user if update.effective_user else update.callback_query.from_user
    
    chat_id = update.effective_chat.id
    processing_msg = await context.bot.send_message(chat_id=chat_id, text="عم بقرأ الملف وبحل السؤال... 🔄")
    
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = ""
        for page in pdf_document:
            text += page.get_text()
        pdf_document.close()
        
        if len(text) > 5000:
            text = text[:5000] + "..."
        
        personality = get_user_personality(user.id)
        personality_prompt = PERSONALITIES.get(personality, PERSONALITIES["teacher"])["prompt"]
        
        user_memory = get_user_memory(user.id)
        messages = []
        for mem in user_memory[-10:]:
            messages.append(mem)
        
        prompt = f"{personality_prompt} حل الاسئلة في هذا النص بالتفصيل وبطريقة سهلة الفهم. اكتب الاجابة بالعربي بدون اي تنسيق او نجوم او علامات."
        if details:
            prompt += f"\n\nتفاصيل اضافية من المستخدم: {details}"
        prompt += f"\n\nالنص:\n{text}"
        
        messages.append({
            "role": "user",
            "content": prompt
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
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"الحل (جزء {i}):\n\n{part}",
                    reply_markup=get_rating_keyboard() if i == len(parts) else None
                )
        else:
            await processing_msg.edit_text(f"الحل:\n\n{answer}", reply_markup=get_rating_keyboard())
        
        context.user_data['pending_pdf'] = None
        context.user_data['pdf_waiting_details'] = False
        
    except Exception as e:
        logger.error(f"Error processing PDF: {e}")
        await processing_msg.edit_text("صار في مشكلة بقراءة الملف، جرب كمان مرة")

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    
    if not is_private_chat(update):
        return
    
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
        await update.message.reply_text("ابعتلي ملف PDF فقط 📄")
        return
    
    add_member(user.id, user.username, user.first_name)
    
    file = await context.bot.get_file(document.file_id)
    pdf_bytes = BytesIO()
    await file.download_to_memory(pdf_bytes)
    pdf_bytes.seek(0)
    pdf_data = pdf_bytes.read()
    
    context.user_data['pending_pdf'] = pdf_data
    
    await update.message.reply_text(
        "📄 هل تريد كتابة تفاصيل معينة؟",
        reply_markup=get_pdf_details_keyboard()
    )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global bot_active
    
    if not is_private_chat(update):
        return
    
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
    
    if context.user_data.get('pdf_waiting_details'):
        context.user_data['pdf_waiting_details'] = False
        pdf_data = context.user_data.get('pending_pdf')
        if pdf_data:
            await process_pdf(update, context, pdf_data, text)
        return
    
    mode = context.user_data.get('mode')
    
    if mode == 'translate':
        try:
            detected_lang = detect(text)
            detected_msg = await update.message.reply_text(f"حسنا تم التعرف التلقائي على اللغة ✅")
            await asyncio.sleep(2)
            await detected_msg.delete()
        except:
            pass
        
        context.user_data['text_to_translate'] = text
        await update.message.reply_text(
            "🌍 قم باختيار لغة الترجمة:",
            reply_markup=get_language_keyboard()
        )
        return
    
    if mode == 'tts':
        processing_msg = await update.message.reply_text("جاري تحويل النص لصوت... 🔊")
        
        try:
            try:
                lang = detect(text)
                if lang not in ['ar', 'en', 'fr', 'es', 'de', 'it', 'ru', 'pt', 'tr', 'hi', 'ja', 'ko', 'zh-cn']:
                    lang = 'ar'
            except:
                lang = 'ar'
            
            tts = gTTS(text=text, lang=lang)
            audio_bytes = BytesIO()
            tts.write_to_fp(audio_bytes)
            audio_bytes.seek(0)
            
            await processing_msg.delete()
            await update.message.reply_voice(
                voice=audio_bytes,
                caption="🔊 تم تحويل النص لصوت",
                reply_markup=get_vip_keyboard()
            )
            context.user_data['mode'] = None
        except Exception as e:
            logger.error(f"TTS error: {e}")
            await processing_msg.edit_text(
                "حصل خطأ في تحويل النص، جرب نص اقصر",
                reply_markup=get_vip_keyboard()
            )
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
    
    if mode == 'text' or len(text) > 10:
        add_member(user.id, user.username, user.first_name)
        processing_msg = await update.message.reply_text("عم بحل السؤال... 🔄")
        
        try:
            personality = get_user_personality(user.id)
            personality_prompt = PERSONALITIES.get(personality, PERSONALITIES["teacher"])["prompt"]
            
            user_memory = get_user_memory(user.id)
            messages = [{"role": "system", "content": f"{personality_prompt} اجب بالعربي بشكل واضح ومفصل بدون اي تنسيق او نجوم او علامات markdown."}]
            
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
            title="حل سؤال بالصورة 🖼️",
            description="اضغط عشان ترسل رابط البوت وتحل سؤالك",
            input_message_content=InputTextMessageContent(
                message_text=f"🤖 بوت حل الاسئلة بالصور\n\nادخل على البوت وابعثلي صورة السؤال وبحلهولك:\n@{bot_info.username}"
            )
        ),
        InlineQueryResultArticle(
            id="2",
            title="مميزات VIP المجانية 🌟",
            description="ترجمة، ابراج، قصص، العاب، نص لصوت",
            input_message_content=InputTextMessageContent(
                message_text=f"🌟 بوت بمميزات VIP مجانية!\n\n✅ ترجمة ل 20+ لغة\n✅ توقعات الابراج\n✅ قصص تفاعلية\n✅ العاب ذكاء\n✅ تحويل نص لصوت\n\nجرب الان: @{bot_info.username}"
            )
        ),
        InlineQueryResultArticle(
            id="3",
            title="تواصل مع المطور 🎖️",
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
    app.add_handler(CommandHandler("VipFree", vipfree_command))
    app.add_handler(CommandHandler("vipfree", vipfree_command))
    app.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, handle_photo))
    app.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.PRIVATE, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, handle_text))
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
