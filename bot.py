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
    retry = Retry(total=5, read=5, connect=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

session = create_session()

def is_valid_bangladesh_number(number):
    pattern = r'^01[3-9]\d{8}$'
    return re.match(pattern, number) is not None

def send_prank_call(phone_number, prank_id):
    """ইম্প্রুভড API কল - JSON পার্সিং এরর হ্যান্ডেল সহ"""
    params = {
        'number': phone_number,
        'prank': prank_id
    }
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive'
    }
    
    try:
        print(f"📤 API Request: {API_URL}?number={phone_number}&prank={prank_id}")
        
        response = session.get(
            API_URL, 
            params=params, 
            headers=headers,
            timeout=30,
            verify=True
        )
        
        print(f"📥 Response Status: {response.status_code}")
        print(f"📄 Response Text (first 200 chars): {response.text[:200] if response.text else 'Empty'}")
        
        # স্ট্যাটাস কোড চেক
        if response.status_code != 200:
            return {
                'success': False, 
                'error': f'HTTP {response.status_code}: {response.reason}'
            }
        
        # খালি রেসপন্স চেক
        if not response.text or not response.text.strip():
            return {
                'success': False, 
                'error': 'API থেকে খালি রেসপন্স পাওয়া গেছে'
            }
        
        # JSON পার্স করার চেষ্টা
        try:
            result = response.json()
            return result
        except json.JSONDecodeError as e:
            # যদি JSON না হয়, তাহলে টেক্সট রেসপন্স দেখান
            return {
                'success': False,
                'error': f'API থেকে ভুল রেসপন্স: {response.text[:100]}',
                'raw_response': response.text
            }
            
    except requests.exceptions.Timeout:
        return {'success': False, 'error': 'API সার্ভার সময়সীমা অতিক্রম করেছে (টাইমআউট)'}
    except requests.exceptions.ConnectionError:
        return {'success': False, 'error': 'API সার্ভারের সাথে সংযোগ স্থাপন করা যায়নি'}
    except requests.exceptions.SSLError:
        return {'success': False, 'error': 'SSL সার্টিফিকেট এরর (verify=False দিয়ে চেষ্টা করুন)'}
    except requests.exceptions.RequestException as e:
        return {'success': False, 'error': f'নেটওয়ার্ক সমস্যা: {str(e)}'}
    except Exception as e:
        return {'success': False, 'error': f'অজানা এরর: {str(e)}'}

def test_api_connection():
    """API সংযোগ পরীক্ষা - ডিটেইলড রেসপন্স সহ"""
    try:
        print("🔍 Testing API connection...")
        response = session.get(API_URL, timeout=10, headers={'Accept': 'application/json'})
        print(f"📥 Test Response Status: {response.status_code}")
        print(f"📄 Test Response: {response.text[:200] if response.text else 'Empty'}")
        
        if response.status_code == 200 and response.text:
            try:
                json.loads(response.text)
                return True, "API সংযুক্ত এবং JSON রেসপন্স দিচ্ছে"
            except:
                return False, f"API JSON দিচ্ছে না: {response.text[:100]}"
        return False, f"API স্ট্যাটাস: {response.status_code}"
    except Exception as e:
        return False, f"সংযোগ এরর: {str(e)}"

def get_main_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=1)
    keyboard.add(
        InlineKeyboardButton("📞 নতুন প্র্যাঙ্ক কল", callback_data="new_prank"),
        InlineKeyboardButton("🔍 API ডায়াগনস্টিক", callback_data="test_api"),
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
    status, msg = test_api_connection()
    api_status = "🟢 সংযুক্ত" if status else f"🔴 {msg}"
    
    welcome_text = (
        f"👋 *প্র্যাঙ্ক কল বট*\n\n"
        f"📡 API স্ট্যাটাস: {api_status}\n\n"
        f"📌 নিচের বোতামে ক্লিক করে প্র্যাঙ্ক কল পাঠান।"
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
        status, msg = test_api_connection()
        
        if status:
            bot.send_message(
                call.message.chat.id,
                f"✅ *API সংযুক্ত!*\n\n{msg}\n\nএখন প্র্যাঙ্ক কল পাঠাতে পারেন।",
                parse_mode='Markdown'
            )
        else:
            bot.send_message(
                call.message.chat.id,
                f"❌ *API সমস্যা!*\n\n{msg}\n\n"
                f"সম্ভাব্য কারণ:\n"
                f"• API সার্ভার ডাউন\n"
                f"• API URL পরিবর্তন হয়েছে\n"
                f"• নেটওয়ার্ক সমস্যা",
                parse_mode='Markdown'
            )

    elif data == "help":
        help_text = (
            "📖 *কীভাবে ব্যবহার করবেন:*\n\n"
            "1️⃣ '📞 নতুন প্র্যাঙ্ক কল' ক্লিক করুন\n"
            "2️⃣ আপনার 11 ডিজিটের নম্বর পাঠান\n"
            "3️⃣ প্র্যাঙ্ক টাইটেল সিলেক্ট করুন\n"
            "4️⃣ কল পাঠানো হবে!\n\n"
            "⚠️ *সতর্কতা:* শুধুমাত্র বিনোদনের জন্য\n"
            "📞 প্রশ্ন: @nobxvau"
        )
        bot.send_message(call.message.chat.id, help_text, parse_mode='Markdown')

    elif data == "about":
        about_text = (
            "🤖 *প্র্যাঙ্ক কল বট*\n\n"
            "🔗 API: NHB Prank\n"
            "👤 Creator: @nobxvau\n"
            "📅 ভার্সন: 2.0"
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

            result = send_prank_call(phone_number, prank_id)
            bot.delete_message(call.message.chat.id, msg.message_id)

            if result.get('success'):
                response_msg = (
                    f"✅ *প্র্যাঙ্ক কল সফল!*\n\n"
                    f"📞 টার্গেট: `{result.get('data', {}).get('target', phone_number)}`\n"
                    f"🎭 প্র্যাঙ্ক: {prank_title}\n"
                    f"🆔 টাস্ক: `{result.get('data', {}).get('task_id', 'N/A')}`\n"
                    f"💳 ক্রেডিট: {result.get('data', {}).get('credit_used', 1)}"
                )
                bot.send_message(call.message.chat.id, response_msg, parse_mode='Markdown')
            else:
                error_msg = result.get('error', 'অজানা এরর')
                raw_response = result.get('raw_response', '')
                
                error_response = (
                    f"❌ *প্র্যাঙ্ক কল ব্যর্থ!*\n\n"
                    f"🔴 কারণ: {error_msg}\n"
                )
                
                if raw_response:
                    error_response += f"\n📄 রেসপন্স: `{raw_response[:100]}`"
                
                error_response += (
                    f"\n\n💡 *সমাধান:*\n"
                    f"• '🔍 API ডায়াগনস্টিক' ব্যবহার করুন\n"
                    f"• কিছুক্ষণ পর চেষ্টা করুন\n"
                    f"• API প্রোভাইডার @nobxvau-কে জানান"
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
    print("🤖 প্র্যাঙ্ক কল বট চালু হচ্ছে...")
    print("=" * 50)
    
    # API চেক
    status, msg = test_api_connection()
    if status:
        print("✅ API সংযুক্ত!")
    else:
        print(f"⚠️ API সমস্যা: {msg}")
    
    print("🚀 বট রানিং...")
    print("=" * 50)
    bot.infinity_polling()
