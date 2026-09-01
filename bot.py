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
API_URL = 'https://nhbdprank.ct.ws/api.php'

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
    retry = Retry(total=3, read=3, connect=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

session = create_session()

def is_valid_bangladesh_number(number):
    pattern = r'^01[3-9]\d{8}$'
    return re.match(pattern, number) is not None

def send_prank_call(phone_number, prank_id):
    params = {'number': phone_number, 'prank': prank_id}
    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}
    
    try:
        response = session.get(API_URL, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        if response.text.strip():
            return response.json()
        return {'success': False, 'error': 'API থেকে খালি রেসপন্স'}
    except requests.exceptions.Timeout:
        return {'success': False, 'error': 'API টাইমআউট'}
    except requests.exceptions.ConnectionError:
        return {'success': False, 'error': 'API সংযোগ নেই'}
    except Exception as e:
        return {'success': False, 'error': f'এরর: {str(e)}'}

def test_api_connection():
    try:
        response = session.get(API_URL, timeout=10)
        return response.status_code == 200
    except:
        return False

def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📞 নতুন প্র্যাঙ্ক কল", callback_data="new_prank"),
        InlineKeyboardButton("🔍 API সংযোগ পরীক্ষা", callback_data="test_api"),
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
    api_status = "🟢 সংযুক্ত" if test_api_connection() else "🔴 সংযোগ নেই"
    bot.reply_to(
        message,
        f"👋 স্বাগতম! প্র্যাঙ্ক কল বট\n\n📡 API স্ট্যাটাস: {api_status}\n\n📌 নিচের বোতামে ক্লিক করুন।",
        reply_markup=get_main_keyboard()
    )

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = call.from_user.id
    data = call.data

    if data == "new_prank":
        bot.answer_callback_query(call.id, "📱 নম্বর পাঠান")
        bot.send_message(call.message.chat.id, "📱 আপনার 11 ডিজিটের নম্বর পাঠান (যেমন: 018XXXXXXXX):")
        user_data[user_id] = {'state': 'awaiting_number'}

    elif data == "test_api":
        bot.answer_callback_query(call.id, "⏳ চেক করা হচ্ছে...")
        if test_api_connection():
            bot.send_message(call.message.chat.id, "✅ API সার্ভার সংযুক্ত!")
        else:
            bot.send_message(call.message.chat.id, "❌ API সার্ভার সংযোগ নেই!")

    elif data == "help":
        bot.send_message(
            call.message.chat.id,
            "📖 *কীভাবে ব্যবহার করবেন:*\n\n1. '📞 নতুন প্র্যাঙ্ক কল' ক্লিক করুন\n2. নম্বর পাঠান\n3. প্র্যাঙ্ক টাইটেল সিলেক্ট করুন\n\n⚠️ শুধুমাত্র বিনোদনের জন্য",
            parse_mode='Markdown'
        )

    elif data == "about":
        bot.send_message(
            call.message.chat.id,
            "🤖 *প্র্যাঙ্ক কল বট*\n\nAPI: NHB Prank\n👤 @nobxvau",
            parse_mode='Markdown'
        )

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
                f"⏳ '{prank_title}' দিয়ে {phone_number} এ কল পাঠানো হচ্ছে..."
            )

            result = send_prank_call(phone_number, prank_id)
            bot.delete_message(call.message.chat.id, msg.message_id)

            if result.get('success'):
                bot.send_message(
                    call.message.chat.id,
                    f"✅ *প্র্যাঙ্ক কল সফল!*\n\n📞 {phone_number}\n🎭 {prank_title}\n🆔 {result.get('data', {}).get('task_id', 'N/A')}",
                    parse_mode='Markdown'
                )
            else:
                bot.send_message(
                    call.message.chat.id,
                    f"❌ *ব্যর্থ!*\n\nকারণ: {result.get('error', 'অজানা এরর')}",
                    parse_mode='Markdown'
                )
            
            del user_data[user_id]
        else:
            bot.send_message(call.message.chat.id, "⚠️ আগে নম্বর দিন। /start করুন।")

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
                "✅ নম্বর গ্রহণ করা হয়েছে। এখন প্র্যাঙ্ক টাইটেল সিলেক্ট করুন:",
                reply_markup=get_prank_selection_keyboard()
            )
        else:
            bot.reply_to(message, "❌ নম্বরটি বৈধ নয়। সঠিক 11 ডিজিটের নম্বর দিন।")
    else:
        bot.reply_to(message, "👋 /start দিয়ে শুরু করুন।")

if __name__ == "__main__":
    print("🤖 বট চালু হচ্ছে...")
    bot.infinity_polling()
