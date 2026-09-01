import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
import json
import re
import time
import sys
import logging
from datetime import datetime, timedelta
from collections import defaultdict

# ============================================
# লগিং সেটআপ
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# ============================================
# কনফিগারেশন
# ============================================
BOT_TOKEN = '8707267313:AAFzqkne7yUZjeNnXza6KbhHIIJMuq1v_zI'  # আপনার টোকেন দিন
API_URL = 'https://nhbdprank.ct.ws/api.php'

# ============================================
# বট ইন্সট্যান্স (এরর হ্যান্ডেল সহ)
# ============================================
try:
    bot = telebot.TeleBot(BOT_TOKEN)
    logger.info("✅ বট ইন্সট্যান্স তৈরি হয়েছে")
except Exception as e:
    logger.error(f"❌ বট ইন্সট্যান্স তৈরি করতে ব্যর্থ: {e}")
    sys.exit(1)

user_data = {}
user_rate_limit = defaultdict(list)

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
# হেল্পার ফাংশন
# ============================================
def is_valid_bangladesh_number(number):
    try:
        pattern = r'^01[3-9]\d{8}$'
        return bool(re.match(pattern, number))
    except:
        return False

def check_rate_limit(user_id):
    try:
        now = datetime.now()
        user_rate_limit[user_id] = [t for t in user_rate_limit[user_id] if now - t < timedelta(seconds=60)]
        
        if len(user_rate_limit[user_id]) >= 5:
            return False, "⚠️ আপনি খুব দ্রুত রিকোয়েস্ট পাঠাচ্ছেন! দয়া করে ১ মিনিট অপেক্ষা করুন।"
        
        user_rate_limit[user_id].append(now)
        return True, ""
    except Exception as e:
        logger.error(f"Rate limit error: {e}")
        return True, ""

def send_prank_call(phone_number, prank_id):
    try:
        params = {'number': phone_number, 'prank': prank_id}
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Accept': 'application/json',
            'Connection': 'keep-alive'
        }
        
        logger.info(f"📤 Sending: number={phone_number}, prank={prank_id}")
        
        response = requests.get(
            API_URL,
            params=params,
            headers=headers,
            timeout=20
        )
        
        logger.info(f"📥 Status: {response.status_code}")
        
        if response.status_code == 200 and response.text:
            try:
                result = response.json()
                
                if result.get('success'):
                    return {'success': True, 'data': result.get('data', {}), 'message': result.get('message', '')}
                else:
                    error_msg = result.get('message', 'অজানা এরর')
                    debug = result.get('debug', '')
                    
                    if 'multi petitiones' in str(debug).lower():
                        return {
                            'success': False,
                            'error': '⚠️ API রেট লিমিট! ২ মিনিট অপেক্ষা করুন।',
                            'retry_after': 120
                        }
                    
                    return {'success': False, 'error': f'❌ {error_msg}'}
                    
            except json.JSONDecodeError:
                return {'success': False, 'error': f'❌ ভুল রেসপন্স: {response.text[:50]}'}
        else:
            return {'success': False, 'error': f'❌ HTTP {response.status_code}'}
            
    except requests.exceptions.Timeout:
        return {'success': False, 'error': '⏰ টাইমআউট! আবার চেষ্টা করুন।'}
    except requests.exceptions.ConnectionError:
        return {'success': False, 'error': '🔌 সংযোগ নেই!'}
    except Exception as e:
        logger.error(f"API Error: {e}")
        return {'success': False, 'error': f'❌ এরর: {str(e)[:50]}'}

def test_api_connection():
    try:
        response = requests.get(API_URL, timeout=5)
        if response.status_code == 200:
            return "🟢 API সংযুক্ত", True
        else:
            return f"🟡 স্ট্যাটাস: {response.status_code}", False
    except Exception as e:
        return f"🔴 সংযোগ নেই: {str(e)[:30]}", False

# ============================================
# কীবোর্ড তৈরি
# ============================================
def get_main_keyboard():
    try:
        keyboard = InlineKeyboardMarkup(row_width=1)
        keyboard.add(
            InlineKeyboardButton("📞 নতুন প্র্যাঙ্ক কল", callback_data="new_prank"),
            InlineKeyboardButton("🔍 API স্ট্যাটাস", callback_data="test_api"),
            InlineKeyboardButton("❓ সাহায্য", callback_data="help"),
            InlineKeyboardButton("ℹ️ সম্পর্কে", callback_data="about")
        )
        return keyboard
    except Exception as e:
        logger.error(f"Keyboard error: {e}")
        return None

def get_prank_selection_keyboard():
    try:
        keyboard = InlineKeyboardMarkup(row_width=1)
        for prank in PRANK_OPTIONS:
            keyboard.add(InlineKeyboardButton(prank['title'], callback_data=f"prank_{prank['id']}"))
        keyboard.add(InlineKeyboardButton("🔙 পেছনে", callback_data="back_to_menu"))
        return keyboard
    except Exception as e:
        logger.error(f"Prank keyboard error: {e}")
        return None

# ============================================
# বট হ্যান্ডলার (এরর প্রোটেক্টেড)
# ============================================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    try:
        status, _ = test_api_connection()
        
        welcome_text = (
            f"👋 *প্র্যাঙ্ক কল বট*\n\n"
            f"📡 {status}\n\n"
            f"📌 নিচের বোতামে ক্লিক করুন।\n"
            f"⚠️ প্রতি মিনিটে ৫ বার রিকোয়েস্ট সীমা।"
        )
        bot.reply_to(message, welcome_text, parse_mode='Markdown', reply_markup=get_main_keyboard())
    except Exception as e:
        logger.error(f"Welcome error: {e}")
        bot.reply_to(message, "❌ কিছু সমস্যা হয়েছে। আবার /start দিন।")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    try:
        user_id = call.from_user.id
        data = call.data
        
        if data.startswith("prank_"):
            allowed, msg = check_rate_limit(user_id)
            if not allowed:
                bot.answer_callback_query(call.id, msg, show_alert=True)
                return

        if data == "new_prank":
            bot.answer_callback_query(call.id, "📱 নম্বর পাঠান")
            bot.send_message(
                call.message.chat.id,
                "📱 আপনার 11 ডিজিটের নম্বর পাঠান:\nউদাহরণ: `018XXXXXXXX`",
                parse_mode='Markdown'
            )
            user_data[user_id] = {'state': 'awaiting_number'}

        elif data == "test_api":
            bot.answer_callback_query(call.id, "⏳ চেক করা হচ্ছে...")
            status, _ = test_api_connection()
            bot.send_message(
                call.message.chat.id,
                f"🔍 *API স্ট্যাটাস*\n\n{status}",
                parse_mode='Markdown'
            )

        elif data == "help":
            help_text = (
                "📖 *কীভাবে ব্যবহার করবেন:*\n\n"
                "1️⃣ '📞 নতুন প্র্যাঙ্ক কল' ক্লিক করুন\n"
                "2️⃣ নম্বর পাঠান\n"
                "3️⃣ প্র্যাঙ্ক টাইটেল সিলেক্ট করুন\n"
                "4️⃣ কল পাঠানো হবে!\n\n"
                "⚠️ প্রতি মিনিটে ৫ বার"
            )
            bot.send_message(call.message.chat.id, help_text, parse_mode='Markdown')

        elif data == "about":
            about_text = (
                "🤖 *প্র্যাঙ্ক কল বট*\n\n"
                "🔗 API: NHB Prank\n"
                "👤 Creator: @nobxvau\n"
                "🛡️ রেট লিমিট: ৫/মিনিট"
            )
            bot.send_message(call.message.chat.id, about_text, parse_mode='Markdown')

        elif data == "back_to_menu":
            bot.edit_message_text(
                "👋 মূল মেনু",
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
                    f"⏳ *'{prank_title}'* দিয়ে `{phone_number}` এ কল পাঠানো হচ্ছে...",
                    parse_mode='Markdown'
                )

                result = send_prank_call(phone_number, prank_id)
                
                try:
                    bot.delete_message(call.message.chat.id, msg.message_id)
                except:
                    pass

                if result.get('success'):
                    response_msg = (
                        f"✅ *প্র্যাঙ্ক কল সফল!*\n\n"
                        f"📞 `{phone_number}`\n"
                        f"🎭 {prank_title}\n"
                        f"🆔 `{result.get('data', {}).get('task_id', 'N/A')}`"
                    )
                    bot.send_message(call.message.chat.id, response_msg, parse_mode='Markdown')
                else:
                    error_msg = result.get('error', 'অজানা এরর')
                    bot.send_message(
                        call.message.chat.id,
                        f"❌ *ব্যর্থ!*\n\n{error_msg}",
                        parse_mode='Markdown'
                    )
                
                if user_id in user_data:
                    del user_data[user_id]
            else:
                bot.send_message(call.message.chat.id, "⚠️ আগে নম্বর দিন। /start করুন।")

    except Exception as e:
        logger.error(f"Callback error: {e}")
        try:
            bot.send_message(call.message.chat.id, f"❌ ত্রুটি: {str(e)[:50]}")
        except:
            pass

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    try:
        user_id = message.from_user.id
        text = message.text.strip()

        if user_id in user_data and user_data[user_id].get('state') == 'awaiting_number':
            if is_valid_bangladesh_number(text):
                user_data[user_id]['number'] = text
                user_data[user_id]['state'] = 'awaiting_prank'
                bot.reply_to(
                    message,
                    "✅ নম্বর গ্রহণ করা হয়েছে!\n\nএখন প্র্যাঙ্ক টাইটেল সিলেক্ট করুন:",
                    reply_markup=get_prank_selection_keyboard()
                )
            else:
                bot.reply_to(
                    message,
                    "❌ নম্বরটি বৈধ নয়!\nসঠিক ফরম্যাট: `018XXXXXXXX`",
                    parse_mode='Markdown'
                )
        else:
            bot.reply_to(
                message,
                "👋 /start দিয়ে শুরু করুন।",
                reply_markup=get_main_keyboard()
            )
    except Exception as e:
        logger.error(f"Message handler error: {e}")
        bot.reply_to(message, f"❌ ত্রুটি: {str(e)[:50]}")

# ============================================
# বট চালু করুন (এরর হ্যান্ডেল সহ)
# ============================================
if __name__ == "__main__":
    print("=" * 50)
    print("🤖 প্র্যাঙ্ক কল বট চালু হচ্ছে...")
    print("=" * 50)
    
    # API চেক
    status, _ = test_api_connection()
    print(f"📡 {status}")
    print(f"📋 {len(PRANK_OPTIONS)} টি প্র্যাঙ্ক লোড হয়েছে")
    print("🛡️ রেট লিমিট: ৫/মিনিট")
    print("=" * 50)
    
    # টোকেন চেক
    if BOT_TOKEN == 'YOUR_BOT_API_TOKEN_HERE':
        print("⚠️ সতর্কতা: টোকেন সেট করা হয়নি!")
        print("❌ বট চালু হবে না। টোকেন দিন।")
        sys.exit(1)
    
    print("🚀 বট রানিং...")
    
    # ইনফিনিটি পোলিং (এরর হ্যান্ডেল সহ)
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=30)
        except Exception as e:
            logger.error(f"❌ বট ক্রাশ: {e}")
            print(f"🔄 ৫ সেকেন্ড পর রিস্টার্ট হচ্ছে...")
            time.sleep(5)
            continue
