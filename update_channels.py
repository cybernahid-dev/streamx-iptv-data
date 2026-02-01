import json
import requests
import os
import concurrent.futures
import shutil
import time
import logging
import tempfile
from datetime import datetime

# --- ⚙️ CONFIGURATION (Advanced) ---
BASE_DIR = os.getcwd()
CATEGORY_DIR = os.path.join(BASE_DIR, "categories")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

# API Endpoints
STREAMS_API = "https://iptv-org.github.io/api/streams.json"
CHANNELS_API = "https://iptv-org.github.io/api/channels.json"

# Default Assets
DEFAULT_LOGO = "https://raw.githubusercontent.com/iptv-org/api/master/data/categories/no-logo.png"

# Filter Rules
CATEGORY_RULES = {
    "bangladesh.json": {"type": "country", "filter": "BD", "category_name": "Bangladesh"},
    "india.json": {"type": "country", "filter": "IN", "category_name": "India"},
    "usa.json": {"type": "country", "filter": "US", "category_name": "USA"},
    "uk.json": {"type": "country", "filter": "GB", "category_name": "UK"},
    "uae.json": {"type": "country", "filter": "AE", "category_name": "UAE"},
    "sports.json": {"type": "genre", "filter": ["sports"], "category_name": "Sports"},
    "kids.json": {"type": "genre", "filter": ["kids", "animation"], "category_name": "Kids"},
    "music.json": {"type": "genre", "filter": ["music"], "category_name": "Music"},
    "informative.json": {"type": "genre", "filter": ["documentary", "education", "science"], "category_name": "Informative"}
}

# --- 📝 LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger()

# --- 🛡️ SAFETY FUNCTIONS ---

def create_backup(filepath):
    """Safety Feature: মডিফাই করার আগে ফাইলের ব্যাকআপ তৈরি করে।"""
    if not os.path.exists(filepath):
        return
    
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
        
    filename = os.path.basename(filepath)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"{filename}_{timestamp}.bak")
    
    try:
        shutil.copy2(filepath, backup_path)
        logger.info(f"🛡️ Backup created: {backup_path}")
    except Exception as e:
        logger.warning(f"⚠️ Backup failed: {e}")

def atomic_save_json(filepath, data):
    """Safety Feature: ডাটা করাপশন রোধ করতে Atomic Save পদ্ধতি।"""
    dir_name = os.path.dirname(filepath)
    # টেম্পোরারি ফাইল তৈরি
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False, encoding='utf-8') as tmp_file:
        json.dump(data, tmp_file, indent=2, ensure_ascii=False)
        temp_name = tmp_file.name
    
    # টেম্প ফাইলটি মেইন ফাইলের জায়গায় রিপ্লেস করা (Atomically)
    try:
        shutil.move(temp_name, filepath)
        logger.info(f"💾 Safely saved: {os.path.basename(filepath)}")
    except Exception as e:
        logger.error(f"❌ Save failed: {e}")
        os.remove(temp_name)

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.error(f"❌ Corrupted JSON found: {filepath}. Starting empty.")
            return {"channels": []}
    return {"channels": []}

# --- 🌐 NETWORK FUNCTIONS ---

def get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Connection": "keep-alive"
    }

def check_link_status(url):
    """Advanced Check: লিঙ্কটি লাইভ কিনা চেক করে (Connect Timeout 3s, Read Timeout 5s)"""
    if not url: return False
    try:
        # stream=True ব্যবহার করা হয়েছে যাতে পুরো ভিডিও ডাউনলোড না করে
        with requests.get(url, headers=get_headers(), stream=True, timeout=(3.05, 5), allow_redirects=True) as response:
            if response.status_code == 200:
                # কন্টেন্ট টাইপ চেক (অপশনাল, কিন্তু ভালো)
                content_type = response.headers.get('Content-Type', '').lower()
                if 'application/x-mpegurl' in content_type or 'video' in content_type or 'octet-stream' in content_type:
                    return True
                return True # টাইপ না মিললেও 200 মানে লাইভ
            return False
    except:
        return False

def process_stream_check(stream, details):
    url = stream.get('url')
    ch_id = stream.get('channel')
    if check_link_status(url):
        return (ch_id, url, details)
    return None

# --- 🚀 MAIN LOGIC ---

def update_channels_pro():
    logger.info("🚀 Starting Ultimate Channel Updater...")
    
    # ১. API ডাটা ফেচ করা
    try:
        logger.info("📡 Fetching global IPTV database...")
        api_streams = requests.get(STREAMS_API, timeout=10).json()
        api_channels = requests.get(CHANNELS_API, timeout=10).json()
        channel_info_map = {c['id']: c for c in api_channels}
        logger.info(f"✅ Loaded {len(api_channels)} channels and {len(api_streams)} streams.")
    except Exception as e:
        logger.critical(f"❌ Critical API Error: {e}")
        return

    if not os.path.exists(CATEGORY_DIR):
        os.makedirs(CATEGORY_DIR)

    # ২. প্রসেসিং শুরু
    for filename, rules in CATEGORY_RULES.items():
        filepath = os.path.join(CATEGORY_DIR, filename)
        logger.info(f"\n🔍 Processing Category: {rules['category_name']} ({filename})")

        # বর্তমান ডাটা লোড
        current_data = load_json(filepath)
        existing_ids = {ch['id'] for ch in current_data.get('channels', [])}
        
        # পোটেনশিয়াল চ্যানেল খোঁজা
        streams_to_check = []
        for stream in api_streams:
            ch_id = stream.get('channel')
            
            # 🛡️ Safety: আইডি আগে থাকলে স্কিপ (Strictly No Touch Policy)
            if not ch_id or ch_id in existing_ids:
                continue
            
            if stream.get('status') in ['error', 'offline']: 
                continue

            ch_details = channel_info_map.get(ch_id)
            if not ch_details: continue

            # রুলস চেকিং
            is_match = False
            if rules['type'] == 'country':
                if ch_details.get('country') == rules['filter']: is_match = True
            elif rules['type'] == 'genre':
                api_cats = [c.lower() for c in ch_details.get('categories', [])]
                for target in rules['filter']:
                    if target.lower() in api_cats:
                        is_match = True
                        break
            
            if is_match:
                # ডুপ্লিকেট স্ট্রিম চেক (একই আইডির একাধিক স্ট্রিম থাকলে প্রথমটি নেওয়া হবে চেকিংয়ের জন্য)
                already_queued = any(s[0].get('channel') == ch_id for s in streams_to_check)
                if not already_queued:
                    streams_to_check.append((stream, ch_details))

        if not streams_to_check:
            logger.info("   macOS😴 No new channels found.")
            continue

        logger.info(f"   ⚡ Found {len(streams_to_check)} potential NEW channels. Checking liveness...")

        # মাল্টি-থ্রেডিং চেকিং (আরও ফাস্ট)
        new_channels_list = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            future_to_url = {
                executor.submit(process_stream_check, s, d): s 
                for s, d in streams_to_check
            }

            for future in concurrent.futures.as_completed(future_to_url):
                result = future.result()
                if result:
                    ch_id, url, details = result
                    
                    # 🖼️ Smart Logo Logic
                    api_logo = details.get('logo')
                    final_logo = api_logo if api_logo else DEFAULT_LOGO

                    new_channel = {
                        "id": ch_id,
                        "name": details.get('name', 'Unknown Channel'),
                        "logoUrl": final_logo,
                        "streamUrls": [url],
                        "category": rules['category_name']
                    }
                    if rules['type'] == 'genre':
                         new_channel["genre"] = rules['category_name']
                    
                    new_channels_list.append(new_channel)
                    print(f"     ✅ [LIVE] {details.get('name')}")

        # ৩. ডাটা সেভ করা (যদি নতুন চ্যানেল পাওয়া যায়)
        if new_channels_list:
            # 🔡 নতুন চ্যানেলগুলোকে A-Z সর্ট করা
            new_channels_list.sort(key=lambda x: x['name'])
            
            logger.info(f"   📥 Adding {len(new_channels_list)} confirmed live channels.")
            
            # 🛡️ ব্যাকআপ নেওয়া
            create_backup(filepath)
            
            # লিস্ট আপডেট
            current_data['channels'].extend(new_channels_list)
            
            # 💾 Atomic Save
            atomic_save_json(filepath, current_data)
        else:
            logger.info("   ⚠️ Potential channels found, but none were live.")

    logger.info("\n🎉 All updates completed successfully!")

if __name__ == "__main__":
    update_channels_pro()

