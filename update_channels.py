import json
import requests
import os
import concurrent.futures
import shutil
import time
import logging
import tempfile
from datetime import datetime

# --- ⚙️ CONFIGURATION (Ultimate) ---
BASE_DIR = os.getcwd()
CATEGORY_DIR = os.path.join(BASE_DIR, "categories")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

# ব্যাকআপ কনফিগারেশন: প্রতি ফাইলের জন্য সর্বোচ্চ কতগুলো ব্যাকআপ রাখবেন?
MAX_BACKUPS_TO_KEEP = 5 

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

# --- 🛡️ SAFETY & CLEANUP FUNCTIONS ---

def cleanup_old_backups():
    """পুরানো ব্যাকআপ ফাইল অটোমেটিক ডিলিট করে (Clean Storage)।"""
    if not os.path.exists(BACKUP_DIR):
        return

    logger.info("🧹 Checking for old backups to clean...")
    all_backups = [f for f in os.listdir(BACKUP_DIR) if f.endswith(".bak")]
    
    deleted_count = 0
    # ক্যাটাগরি অনুযায়ী চেক করা
    for filename in CATEGORY_RULES.keys():
        # এই নির্দিষ্ট ফাইলের সব ব্যাকআপ খুঁজে বের করা
        file_backups = [f for f in all_backups if f.startswith(f"{filename}_")]
        
        # তারিখ অনুযায়ী সাজানো (Oldest first)
        file_backups.sort()
        
        # যদি MAX_BACKUPS_TO_KEEP এর চেয়ে বেশি থাকে, তবে পুরানোগুলো ডিলিট করো
        if len(file_backups) > MAX_BACKUPS_TO_KEEP:
            files_to_delete = file_backups[:-MAX_BACKUPS_TO_KEEP] # নতুন ৫টি রেখে বাকি সব ডিলিট
            
            for old_file in files_to_delete:
                try:
                    os.remove(os.path.join(BACKUP_DIR, old_file))
                    logger.info(f"   🗑️ Auto-Deleted Old Backup: {old_file}")
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ Failed to delete {old_file}: {e}")
    
    if deleted_count == 0:
        logger.info("   ✅ No old backups needed deletion.")

def create_backup(filepath):
    """সেভ করার আগে ফাইলের ব্যাকআপ তৈরি করে।"""
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
    """ডাটা সেভ করে এবং টেম্পোরারি ফাইল অটোমেটিক রিমুভ করে।"""
    dir_name = os.path.dirname(filepath)
    
    # ১. টেম্পোরারি ফাইল তৈরি
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False, encoding='utf-8') as tmp_file:
        json.dump(data, tmp_file, indent=2, ensure_ascii=False)
        temp_name = tmp_file.name
    
    # ২. সেভ করার চেষ্টা (Replace logic)
    try:
        shutil.move(temp_name, filepath)
        # shutil.move সফল হলে সোর্স (temp) ফাইল অটোমেটিক ডিলিট হয়ে যায়
        logger.info(f"💾 Safely saved & Temp file cleaned: {os.path.basename(filepath)}")
    except Exception as e:
        logger.error(f"❌ Save failed: {e}")
        # ৩. ফেইল করলে ম্যানুয়ালি টেম্প ফাইল ডিলিট
        if os.path.exists(temp_name):
            os.remove(temp_name)
            logger.info("   🧹 Residual Temp file removed manually.")

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
    """Advanced Check: লিঙ্কটি লাইভ কিনা চেক করে"""
    if not url: return False
    try:
        with requests.get(url, headers=get_headers(), stream=True, timeout=(3.05, 5), allow_redirects=True) as response:
            if response.status_code == 200:
                content_type = response.headers.get('Content-Type', '').lower()
                if 'application/x-mpegurl' in content_type or 'video' in content_type or 'octet-stream' in content_type:
                    return True
                return True 
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
    logger.info("🚀 Starting Ultimate Channel Updater (Clean Mode)...")
    
    # শুরুতে পুরনো ব্যাকআপ ডিলিট করা
    cleanup_old_backups()

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

    for filename, rules in CATEGORY_RULES.items():
        filepath = os.path.join(CATEGORY_DIR, filename)
        logger.info(f"\n🔍 Processing Category: {rules['category_name']} ({filename})")

        current_data = load_json(filepath)
        existing_ids = {ch['id'] for ch in current_data.get('channels', [])}
        
        streams_to_check = []
        for stream in api_streams:
            ch_id = stream.get('channel')
            if not ch_id or ch_id in existing_ids: continue
            if stream.get('status') in ['error', 'offline']: continue

            ch_details = channel_info_map.get(ch_id)
            if not ch_details: continue

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
                already_queued = any(s[0].get('channel') == ch_id for s in streams_to_check)
                if not already_queued:
                    streams_to_check.append((stream, ch_details))

        if not streams_to_check:
            logger.info("   😴 No new channels found.")
            continue

        logger.info(f"   ⚡ Found {len(streams_to_check)} potential NEW channels. Checking liveness...")

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

        if new_channels_list:
            new_channels_list.sort(key=lambda x: x['name'])
            
            logger.info(f"   📥 Adding {len(new_channels_list)} confirmed live channels.")
            
            # ব্যাকআপ তৈরি
            create_backup(filepath)
            
            # ডাটা আপডেট
            current_data['channels'].extend(new_channels_list)
            
            # সেভ এবং টেম্প ফাইল ক্লিনআপ
            atomic_save_json(filepath, current_data)
        else:
            logger.info("   ⚠️ Potential channels found, but none were live.")

    logger.info("\n🎉 All updates and cleanups completed successfully!")

if __name__ == "__main__":
    update_channels_pro()

