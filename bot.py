import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import json
import re
import time
import random
from datetime import datetime, timedelta
from collections import defaultdict
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ============================================
# কনফিগারেশন
# ============================================
BOT_TOKEN = '8707267313:AAFzqkne7yUZjeNnXza6KbhHIIJMuq1v_zI'  # আপনার টোকেন দিন
API_URL = 'https://nhbdprank.ct.ws/api.php'
DEMO_MODE = False  # False রাখুন, API কাজ করছে

# ============================================
# বট ইন্সট্যান্স
# ============================================
bot = telebot.TeleBot(BOT_TOKEN)
user_data = {}
user_rate_limit = defaultdict(list)  # ইউজারের রিকোয়েস্ট ট্র্যাক করতে

# ============================================
# প্র্যাঙ্ক অপশন
# ============================================
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

# ============================================
# সেশন তৈরি
# ============================================
def create_session():
    session = requests.Session()
    retry = Retry(
        total=5,
        read=5,
        connect=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

session = create_session()

# ============================================
# হেল্পার ফাংশন
# ============================================
def is_valid_bangladesh_number(number):
    pattern = r'^01[3-9]\d{8}$'
    return re.match(pattern, number) is not None

def check_rate_limit(user_id):
    """ইউজারের রেট লিমিট চেক করে"""
    now = datetime.now()
    # গত 60 সেকেন্ডে কত রিকোয়েস্ট
    user_rate_limit[user_id] = [t for t in user_rate_limit[user_id] if now - t < timedelta(seconds=60)]
    
    if len(user_rate_limit[user_id]) >= 5:  # প্রতি মিনিটে ৫ টি রিকোয়েস্ট
        return False, "⚠️ আপনি খুব দ্রুত রিকোয়েস্ট পাঠাচ্ছেন! দয়া করে ১ মিনিট অপেক্ষা করুন।"
    
    user_rate_limit[user_id].append(now)
    return True, ""

def send_prank_call(phone_number, prank_id):
    """রেট লিমিট হ্যান্ডেল সহ API কল"""
    params = {'number': phone_number, 'prank': prank_id}
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive'
    }
    
    try:
        print(f"📤 Sending: number={phone_number}, prank={prank_id}")
        
        response = session.get(
            API_URL,
            params=params,
            headers=headers,
            timeout=30
        )
        
        print(f"📥 Status: {response.status_code}")
        print(f"📄 Response: {response.text[:200] if response.text else 'Empty'}")
        
        # রেসপন্স চেক
        if response.status_code == 200 and response.text:
            try:
                result = response.json()
                
                # API রেসপন্স চেক
                if result.get('success'):
                    return {'success': True, 'data': result.get('data', {}), 'message': result.get('message', '')}
                else:
                    # এরর মেসেজ চেক
                    error_msg = result.get('message', 'অজানা এরর')
                    debug = result.get('debug', '')
                    
                    # রেট লিমিট চেক
                    if 'multi petitiones' in str(debug).lower() or 'too many' in str(error_msg).lower():
                        return {
                            'success': False,
                            'error': '⚠️ API রেট লিমিট! দয়া করে ২-৩ মিনিট অপেক্ষা করুন।',
                            'debug': debug,
                            'message': error_msg,
                            'retry_after': 120  # ২ মিনিট
                        }
                    
                    return {
                        'success': False,
                        'error': f'❌ {error_msg}',
                        'debug': debug,
                        'message': error_msg
                    }
                    
            except json.JSONDecodeError as e:
                return {
                    'success': False,
                    'error': f'❌ API থেকে ভুল রেসপন্স: {response.text[:100]}',
                    'raw': response.text
                }
        else:
            return {
                'success': False,
                'error': f'❌ HTTP {response.status_code}: {response.reason}'
            }
            
    except requests.exceptions.Timeout:
        return {'success': False, 'error': '⏰ API টাইমআউট! আবার চেষ্টা করুন।'}
    except requests.exceptions.ConnectionError:
        return {'success': False, 'error': '🔌 API সংযোগ নেই! ইন্টারনেট চেক করুন।'}
    except Exception as e:
        return {'success': False, 'error': f'❌ অজানা এরর: {str(e)}'}

def test_api_connection():
    """API সংযোগ পরীক্ষা"""
    try:
        response = session.get(API_URL, timeout=10)
        if response.status_code == 200:
            return "🟢 API সংযুক্ত", True
        else:
            return f"🟡 API স্ট্যাটাস: {response.status_code}", False
    except Exception as e:
        return f"🔴 API সংযোগ নেই: {str(e)[:50]}", False

# ============================================
# কীবোর্ড তৈরি
# ============================================
def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📞 নতুন প্র্যাঙ্ক কল", callback_data="new_prank"),
        InlineKeyboardButton("🔍 API স্ট্যাটাস", callback_data="test_api"),
        InlineKeyboardButton("📊 আমার স্ট্যাটাস", callback_data="my_status"),
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

# ============================================
# বট কমান্ড হ্যান্ডলার
# ============================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    status, is_connected = test_api_connection()
    
    welcome_text = (
        f"👋 *প্র্যাঙ্ক কল বট*\n\n"
        f"📡 {status}\n\n"
        f"📌 নিচের বোতামে ক্লিক করে প্র্যাঙ্ক কল পাঠান।\n\n"
        f"⚠️ *নিয়ম:* প্রতি মিনিটে ৫ বার রিকোয়েস্ট করতে পারবেন।"
    )
    bot.reply_to(message, welcome_text, parse_mode='Markdown', reply_markup=get_main_keyboard())

# ============================================
# কলব্যাক হ্যান্ডলার
# ============================================
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data
    
    try:
        # রেট লিমিট চেক (শুধু প্র্যাঙ্ক কলের জন্য)
        if data.startswith("prank_"):
            allowed, msg = check_rate_limit(user_id)
            if not allowed:
                bot.answer_callback_query(call.id, msg, show_alert=True)
                return

        if data == "new_prank":
            bot.answer_callback_query(call.id, "📱 নম্বর পাঠান")
            bot.send_message(
                call.message.chat.id,
                "📱 আপনার 11 ডিজিটের মোবাইল নম্বর পাঠান:\n\n"
                "উদাহরণ: `018XXXXXXXX`\n"
                "⚠️ শুধুমাত্র বাংলাদেশি নম্বর (01 দিয়ে শুরু)",
                parse_mode='Markdown'
            )
            user_data[user_id] = {'state': 'awaiting_number'}

        elif data == "test_api":
            bot.answer_callback_query(call.id, "⏳ চেক করা হচ্ছে...")
            status, _ = test_api_connection()
            bot.send_message(
                call.message.chat.id,
                f"🔍 *API ডায়াগনস্টিক*\n\n{status}\n\n"
                f"💡 API কাজ করছে, কিন্তু রেট লিমিট থাকতে পারে।",
                parse_mode='Markdown'
            )

        elif data == "my_status":
            now = datetime.now()
            recent = [t for t in user_rate_limit[user_id] if now - t < timedelta(seconds=60)]
            remaining = 5 - len(recent)
            status_text = (
                f"📊 *আপনার স্ট্যাটাস*\n\n"
                f"⏱️ গত ১ মিনিটে রিকোয়েস্ট: {len(recent)}/৫\n"
                f"🟢 বাকি: {remaining if remaining > 0 else ০}\n"
                f"🔄 রিসেট: {60 - (now - recent[0]).seconds if recent else ০} সেকেন্ড"
            )
            bot.send_message(call.message.chat.id, status_text, parse_mode='Markdown')

        elif data == "help":
            help_text = (
                "📖 *কীভাবে ব্যবহার করবেন:*\n\n"
                "1️⃣ '📞 নতুন প্র্যাঙ্ক কল' ক্লিক করুন\n"
                "2️⃣ আপনার 11 ডিজিটের নম্বর পাঠান\n"
                "3️⃣ প্র্যাঙ্ক টাইটেল সিলেক্ট করুন\n"
                "4️⃣ কল পাঠানো হবে!\n\n"
                "⚠️ *সতর্কতা:*\n"
                "• প্রতি মিনিটে ৫ বার রিকোয়েস্ট\n"
                "• শুধুমাত্র বিনোদনের জন্য\n"
                "• API ডাউন থাকলে অপেক্ষা করুন\n\n"
                "📞 প্রশ্ন: @nobxvau"
            )
            bot.send_message(call.message.chat.id, help_text, parse_mode='Markdown')

        elif data == "about":
            about_text = (
                "🤖 *প্র্যাঙ্ক কল বট v3.0*\n\n"
                "🔗 API: NHB Prank\n"
                "👤 Creator: @nobxvau\n"
                "🛡️ ফিচার: রেট লিমিট, অটো রিট্রাই\n"
                "📅 শেষ আপডেট: সেপ্টেম্বর ২০২৬"
            )
            bot.send_message(call.message.chat.id, about_text, parse_mode='Markdown')

        elif data == "back_to_menu":
            bot.edit_message_text(
                "👋 মূল মেনুতে ফিরে এসেছেন।",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=get_main_keyboard()
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
                    f"⏱️ দয়া করে অপেক্ষা করুন (সর্বোচ্চ ৩০ সেকেন্ড)",
                    parse_mode='Markdown'
                )

                # API কল
                result = send_prank_call(phone_number, prank_id)
                bot.delete_message(call.message.chat.id, msg.message_id)

                # রেসপন্স প্রসেস
                if result.get('success'):
                    response_msg = (
                        f"✅ *প্র্যাঙ্ক কল সফল!*\n\n"
                        f"📞 টার্গেট: `{phone_number}`\n"
                        f"🎭 প্র্যাঙ্ক: {prank_title}\n"
                        f"🆔 টাস্ক: `{result.get('data', {}).get('task_id', 'N/A')}`\n"
                        f"💳 ক্রেডিট: {result.get('data', {}).get('credit_used', 1)}\n"
                        f"👤 মালিক: {result.get('owner', '@nobxvau')}"
                    )
                    bot.send_message(call.message.chat.id, response_msg, parse_mode='Markdown')
                    
                else:
                    error_msg = result.get('error', 'অজানা এরর')
                    retry_after = result.get('retry_after', 0)
                    
                    error_response = (
                        f"❌ *প্র্যাঙ্ক কল ব্যর্থ!*\n\n"
                        f"🔴 কারণ: {error_msg}\n"
                    )
                    
                    if retry_after > 0:
                        error_response += f"\n⏳ *রেট লিমিট!* {retry_after} সেকেন্ড অপেক্ষা করুন।"
                    else:
                        error_response += (
                            f"\n💡 *সমাধান:*\n"
                            f"• ১-২ মিনিট অপেক্ষা করুন\n"
                            f"• আলাদা প্র্যাঙ্ক ট্রাই করুন\n"
                            f"• @nobxvau-কে জানান"
                        )
                    
                    bot.send_message(call.message.chat.id, error_response, parse_mode='Markdown')
                
                # ইউজার ডেটা ক্লিয়ার
                if user_id in user_data:
                    del user_data[user_id]
                    
            else:
                bot.send_message(
                    call.message.chat.id,
                    "⚠️ আগে একটি বৈধ নম্বর দিন। /start দিয়ে শুরু করুন।"
                )

    except Exception as e:
        print(f"Error in callback: {e}")
        bot.send_message(call.message.chat.id, f"❌ একটি ত্রুটি ঘটেছে: {str(e)[:100]}")

# ============================================
# মেসেজ হ্যান্ডলার
# ============================================
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    try:
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
    except Exception as e:
        print(f"Error in message handler: {e}")
        bot.reply_to(message, f"❌ ত্রুটি: {str(e)[:100]}")

# ============================================
# বট চালু করুন
# ============================================
if __name__ == "__main__":
    print("=" * 60)
    print("🤖 প্র্যাঙ্ক কল বট v3.0 চালু হচ্ছে...")
    print("=" * 60)
    
    status, _ = test_api_connection()
    print(f"📡 {status}")
    print(f"📋 মোট {len(PRANK_OPTIONS)} টি প্র্যাঙ্ক টাইটেল লোড করা হয়েছে")
    print(f"🛡️ রেট লিমিট: প্রতি মিনিটে ৫ টি রিকোয়েস্ট")
    print("=" * 60)
    print("🚀 বট রানিং...")
    
    try:
        bot.infinity_polling()
    except Exception as e:
        print(f"❌ বট ক্র্যাশ: {e}")
        time.sleep(5)
        print("🔄 রিস্টার্ট হচ্ছে...")
        bot.infinity_polling()
