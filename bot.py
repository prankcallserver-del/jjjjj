import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import json
import re
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --- কনফিগারেশন ---
BOT_TOKEN = '8707267313:AAFzqkne7yUZjeNnXza6KbhHIIJMuq1v_zI'  # এখানে আপনার টোকেন দিন

# একাধিক API URL (যদি একটি কাজ না করে অন্যটি চেষ্টা করবে)
API_URLS = [
    'https://nhbdprank.ct.ws/api.php',
    'http://nhbdprank.ct.ws/api.php',  # HTTP ভার্সন
    'https://nhbdprank.ct.ws/api.php?',  # অল্টারনেটিভ
]

bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}

PRANK_OPTIONS = [
    {"id": "8810", "title": "📱 আপনি আমার গার্লফ্রেন্ডকে কল করেন কেন?"},
    {"id": "8805", "title": "💨 গাজার মতো দুর্গন্ধ!"},
    {"id": "8808", "title": "📶 আপনি আমার ওয়াই-ফাই চুরি করছেন!"},
    {"id": "8809", "title": "🤔 আপনি কেন আমাকে কল করেন?"},
    {"id": "8803", "title": "🍕 পিজ্জা ডেলিভারি"},
    {"id": "8804", "title": "🚕 আপনার ট্যাক্সি আপনার জন্য অপেক্ষা করছে"},
    {"id": "8806", "title": "🔊 আপনার কামরার হৈচৈ আওয়াজ"},
    {"id": "8807", "title": "🐕 আপনার কুকুরটি খুবই ক্লান্তিকর!"}
]

def create_session():
    session = requests.Session()
    retry = Retry(
        total=3,
        read=3,
        connect=3,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504, 429]
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

session = create_session()

def is_valid_bangladesh_number(number):
    pattern = r'^01[3-9]\d{8}$'
    return re.match(pattern, number) is not None

def send_prank_call(phone_number, prank_id):
    """একাধিক API URL চেষ্টা করবে"""
    params = {
        'number': phone_number,
        'prank': prank_id
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'Cache-Control': 'no-cache'
    }
    
    last_error = None
    
    # প্রতিটি API URL চেষ্টা করি
    for api_url in API_URLS:
        try:
            print(f"📤 Trying API: {api_url}")
            
            response = session.get(
                api_url, 
                params=params, 
                headers=headers,
                timeout=20,
                verify=False  # SSL সমস্যা এড়াতে
            )
            
            print(f"📥 Status: {response.status_code}")
            
            if response.status_code == 200 and response.text:
                try:
                    result = response.json()
                    if result.get('success'):
                        return result
                    else:
                        # success false হলে পরবর্তী URL চেষ্টা করি
                        continue
                except json.JSONDecodeError:
                    continue
                    
        except Exception as e:
            last_error = str(e)
            print(f"❌ Error with {api_url}: {e}")
            continue
    
    # সব URL ব্যর্থ হলে
    return {
        'success': False,
        'error': f'সব API এন্ডপয়েন্ট ব্যর্থ। শেষ এরর: {last_error}',
        'raw_response': None
    }

def test_api_connection():
    """সব API URL চেক করে"""
    results = []
    for api_url in API_URLS:
        try:
            response = session.get(api_url, timeout=10, verify=False)
            if response.status_code == 200:
                results.append(f"✅ {api_url} - সংযুক্ত")
            else:
                results.append(f"❌ {api_url} - স্ট্যাটাস {response.status_code}")
        except Exception as e:
            results.append(f"❌ {api_url} - {str(e)[:50]}")
    
    return "\n".join(results)

def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📞 নতুন প্র্যাঙ্ক কল", callback_data="new_prank"),
        InlineKeyboardButton("🔍 API ডায়াগনস্টিক", callback_data="test_api"),
        InlineKeyboardButton("🔄 API রিফ্রেশ", callback_data="refresh_api"),
        InlineKeyboardButton("❓ সাহায্য", callback_data="help"),
        InlineKeyboardButton("ℹ️ সম্পর্কে", callback_data="about")
    )
    return keyboard

def get_prank_selection_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    for prank in PRANK_OPTIONS:
        keyboard.add(InlineKeyboardButton(prank['title'], callback_data=f"prank_{prank['id']}"))
    keyboard.add(InlineKeyboardButton("🔙 পেছনে", callback_data="back_to_menu"))
    return keyboard

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    status_text = test_api_connection()
    
    welcome_text = (
        f"👋 *প্র্যাঙ্ক কল বট*\n\n"
        f"📡 *API স্ট্যাটাস:*\n{status_text}\n\n"
        f"📌 নিচের বোতামে ক্লিক করে প্র্যাঙ্ক কল পাঠান।\n\n"
        f"⚠️ API সার্ভার ডাউন থাকলে '🔄 API রিফ্রেশ' চাপুন।"
    )
    bot.reply_to(message, welcome_text, parse_mode='Markdown', reply_markup=get_main_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data

    if data == "new_prank":
        bot.answer_callback_query(call.id, "📱 নম্বর পাঠান")
        bot.send_message(
            call.message.chat.id, 
            "📱 আপনার 11 ডিজিটের মোবাইল নম্বর পাঠান:\n\n"
            "উদাহরণ: `018XXXXXXXX`\n"
            "⚠️ শুধুমাত্র বাংলাদেশি নম্বর",
            parse_mode='Markdown'
        )
        user_data[user_id] = {'state': 'awaiting_number'}

    elif data == "test_api":
        bot.answer_callback_query(call.id, "⏳ API চেক করা হচ্ছে...")
        status_text = test_api_connection()
        
        bot.send_message(
            call.message.chat.id,
            f"🔍 *API ডায়াগনস্টিক রেজাল্ট:*\n\n{status_text}\n\n"
            f"💡 যদি সব URL ব্যর্থ হয়, তাহলে API সার্ভার ডাউন।",
            parse_mode='Markdown'
        )

    elif data == "refresh_api":
        bot.answer_callback_query(call.id, "🔄 API রিফ্রেশ করা হচ্ছে...")
        status_text = test_api_connection()
        
        bot.send_message(
            call.message.chat.id,
            f"🔄 *API রিফ্রেশ সম্পন্ন!*\n\n{status_text}\n\n"
            f"✅ এখন আবার প্র্যাঙ্ক কল চেষ্টা করুন।",
            parse_mode='Markdown'
        )

    elif data == "help":
        help_text = (
            "📖 *কীভাবে ব্যবহার করবেন:*\n\n"
            "1️⃣ '📞 নতুন প্র্যাঙ্ক কল' ক্লিক করুন\n"
            "2️⃣ আপনার 11 ডিজিটের নম্বর পাঠান\n"
            "3️⃣ প্র্যাঙ্ক টাইটেল সিলেক্ট করুন\n"
            "4️⃣ কল পাঠানো হবে!\n\n"
            "🔄 যদি API ডাউন থাকে, '🔄 API রিফ্রেশ' চাপুন\n\n"
            "⚠️ *সতর্কতা:* শুধুমাত্র বিনোদনের জন্য"
        )
        bot.send_message(call.message.chat.id, help_text, parse_mode='Markdown')

    elif data == "about":
        about_text = (
            "🤖 *প্র্যাঙ্ক কল বট v2.1*\n\n"
            "🔗 API: NHB Prank\n"
            "👤 Creator: @nobxvau\n"
            "🔄 মাল্টিপল API এন্ডপয়েন্ট সাপোর্ট"
        )
        bot.send_message(call.message.chat.id, about_text, parse_mode='Markdown')

    elif data == "back_to_menu":
        status_text = test_api_connection()
        bot.edit_message_text(
            f"👋 মূল মেনুতে ফিরে এসেছেন।\n\n📡 {status_text}",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=get_main_keyboard(),
            parse_mode='Markdown'
        )

    elif data.startswith("prank_"):
        prank_id = data.split("_")[1]
        prank_title = next((p['title'] for p in PRANK_OPTIONS if p['id'] == prank_id), f"ID: {prank_id}")

        if user_id in user_data and 'number' in user_data[user_id]:
            phone_number = user_data[user_id]['number']
            bot.answer_callback_query(call.id, "⏳ কল পাঠানো হচ্ছে...")
            
            msg = bot.send_message(
                call.message.chat.id,
                f"⏳ *'{prank_title}'* দিয়ে `{phone_number}` এ কল পাঠানো হচ্ছে...\n\n"
                f"⏱️ দয়া করে অপেক্ষা করুন (সর্বোচ্চ ২০ সেকেন্ড)\n"
                f"🔄 একাধিক API এন্ডপয়েন্ট চেষ্টা করা হচ্ছে...",
                parse_mode='Markdown'
            )

            result = send_prank_call(phone_number, prank_id)
            bot.delete_message(call.message.chat.id, msg.message_id)

            if result.get('success'):
                response_msg = (
                    f"✅ *প্র্যাঙ্ক কল সফল!*\n\n"
                    f"📞 টার্গেট: `{result.get('data', {}).get('target', phone_number)}`\n"
                    f"🎭 প্র্যাঙ্ক: {prank_title}\n"
                    f"🆔 টাস্ক: `{result.get('data', {}).get('task_id', 'N/A')}`\n"
                    f"💳 ক্রেডিট: {result.get('data', {}).get('credit_used', 1)}\n"
                    f"👤 মালিক: {result.get('owner', '@nobxvau')}"
                )
                bot.send_message(call.message.chat.id, response_msg, parse_mode='Markdown')
            else:
                error_msg = result.get('error', 'API সার্ভার ডাউন')
                
                error_response = (
                    f"❌ *প্র্যাঙ্ক কল ব্যর্থ!*\n\n"
                    f"🔴 কারণ: {error_msg}\n\n"
                    f"💡 *সমাধান:*\n"
                    f"• '🔄 API রিফ্রেশ' বোতাম চাপুন\n"
                    f"• কিছুক্ষণ পর আবার চেষ্টা করুন\n"
                    f"• API সার্ভার ডাউন থাকতে পারে\n"
                    f"• @nobxvau-কে জানান"
                )
                bot.send_message(call.message.chat.id, error_response, parse_mode='Markdown')
            
            if user_id in user_data:
                del user_data[user_id]
        else:
            bot.send_message(
                call.message.chat.id, 
                "⚠️ আগে একটি বৈধ নম্বর দিন। /start দিয়ে শুরু করুন।"
            )

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    text = message.text.strip()

    if user_id in user_data and user_data[user_id].get('state') == 'awaiting_number':
        if is_valid_bangladesh_number(text):
            user_data[user_id]['number'] = text
            user_data[user_id]['state'] = 'awaiting_prank'
            bot.reply_to(
                message,
                "✅ নম্বর গ্রহণ করা হয়েছে!\n\nএখন আপনার পছন্দের প্র্যাঙ্ক টাইটেল সিলেক্ট করুন:",
                reply_markup=get_prank_selection_keyboard()
            )
        else:
            bot.reply_to(
                message, 
                "❌ নম্বরটি বৈধ নয়!\n\n"
                "সঠিক ফরম্যাট: `018XXXXXXXX`\n"
                "⚠️ 01 দিয়ে শুরু এবং 11 ডিজিট হতে হবে।",
                parse_mode='Markdown'
            )
    else:
        bot.reply_to(
            message, 
            "👋 /start দিয়ে বট চালু করুন।",
            reply_markup=get_main_keyboard()
        )

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 প্র্যাঙ্ক কল বট v2.1 চালু হচ্ছে...")
    print("=" * 50)
    
    # সব API চেক
    status_text = test_api_connection()
    print(f"📡 API স্ট্যাটাস:\n{status_text}")
    
    print("🚀 বট রানিং...")
    print("=" * 50)
    bot.infinity_polling()
