import json
import requests
import os
import concurrent.futures
import shutil
import time
import logging
import tempfile
from datetime import datetime

# লাইব্রেরি ইমপোর্ট (Scraping এর জন্য)
try:
    from duckduckgo_search import DDGS
except ImportError as e:
    print(f"❌ Error: 'duckduckgo-search' library missing or failed to import.")
    print(f"Details: {e}")
    print("👉 Please run: pip install duckduckgo-search")
    exit()

# --- ⚙️ CONFIGURATION (Ultimate) ---
BASE_DIR = os.getcwd()
CATEGORY_DIR = os.path.join(BASE_DIR, "categories")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

MAX_BACKUPS_TO_KEEP = 5 

# API Endpoints
STREAMS_API = "https://iptv-org.github.io/api/streams.json"
CHANNELS_API = "https://iptv-org.github.io/api/channels.json"

# Default Assets (এই লিংকটি থাকলে স্ক্রিপ্ট বুঝবে লোগো মিসিং)
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

# --- 🕵️‍♂️ LOGO SCRAPPING ENGINE ---

def find_real_logo_online(channel_name):
    """DuckDuckGo ব্যবহার করে রিয়েল লোগো খুঁজে বের করে।"""
    query = f"{channel_name} tv channel logo transparent wikipedia"
    try:
        # DDGS ব্যবহার করে ইমেজ সার্চ (১টি রেজাল্ট আনবে)
        # Context Manager ব্যবহার করা ভালো
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=1))
            if results:
                image_url = results[0]['image']
                return image_url
    except Exception as e:
        logger.warning(f"   ⚠️ Logo search failed for {channel_name}: {e}")
    
    return DEFAULT_LOGO  # না পেলে ডিফল্ট লোগোই থাকবে

# --- 🛡️ SAFETY & CLEANUP FUNCTIONS ---

def cleanup_old_backups():
    """পুরানো ব্যাকআপ ডিলিট করে।"""
    if not os.path.exists(BACKUP_DIR): return
    logger.info("🧹 Cleaning up old backups...")
    all_backups = [f for f in os.listdir(BACKUP_DIR) if f.endswith(".bak")]
    deleted_count = 0
    for filename in CATEGORY_RULES.keys():
        file_backups = [f for f in all_backups if f.startswith(f"{filename}_")]
        file_backups.sort()
        if len(file_backups) > MAX_BACKUPS_TO_KEEP:
            for old_file in file_backups[:-MAX_BACKUPS_TO_KEEP]:
                try:
                    os.remove(os.path.join(BACKUP_DIR, old_file))
                    deleted_count += 1
                except: pass
    if deleted_count > 0: logger.info(f"   🗑️ Removed {deleted_count} old backup files.")

def create_backup(filepath):
    if not os.path.exists(filepath): return
    if not os.path.exists(BACKUP_DIR): os.makedirs(BACKUP_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"{os.path.basename(filepath)}_{timestamp}.bak")
    try: shutil.copy2(filepath, backup_path)
    except Exception as e: logger.warning(f"⚠️ Backup failed: {e}")

def atomic_save_json(filepath, data):
    dir_name = os.path.dirname(filepath)
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False, encoding='utf-8') as tmp_file:
        json.dump(data, tmp_file, indent=2, ensure_ascii=False)
        temp_name = tmp_file.name
    try:
        shutil.move(temp_name, filepath)
        logger.info(f"💾 Saved & Cleaned: {os.path.basename(filepath)}")
    except Exception as e:
        logger.error(f"❌ Save failed: {e}")
        if os.path.exists(temp_name): os.remove(temp_name)

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {"channels": []}
    return {"channels": []}

# --- 🌐 NETWORK FUNCTIONS ---

def get_headers():
    return {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/115.0.0.0 Safari/537.36"}

def check_link_status(url):
    if not url: return False
    try:
        with requests.get(url, headers=get_headers(), stream=True, timeout=(3, 5)) as r:
            return r.status_code == 200
    except: return False

def process_stream_check(stream, details):
    url = stream.get('url')
    ch_id = stream.get('channel')
    if check_link_status(url):
        return (ch_id, url, details)
    return None

# --- 🚀 MAIN LOGIC ---

def update_channels_ultimate():
    logger.info("🚀 Starting Ultimate Channel Updater (Auto-Logo Fixer)...")
    cleanup_old_backups()

    try:
        logger.info("📡 Fetching IPTV Database...")
        api_streams = requests.get(STREAMS_API, timeout=10).json()
        api_channels = requests.get(CHANNELS_API, timeout=10).json()
        channel_info_map = {c['id']: c for c in api_channels}
    except Exception as e:
        logger.critical(f"❌ API Error: {e}")
        return

    if not os.path.exists(CATEGORY_DIR): os.makedirs(CATEGORY_DIR)

    for filename, rules in CATEGORY_RULES.items():
        filepath = os.path.join(CATEGORY_DIR, filename)
        logger.info(f"\n🔍 Processing: {filename}")

        current_data = load_json(filepath)
        existing_channels = current_data.get('channels', [])
        existing_ids = {ch['id'] for ch in existing_channels}
        
        data_modified = False

        # --- PART 1: FIX OLD LOGOS (Retroactive Fix) ---
        # যাদের লোগো নেই বা ডিফল্ট লোগো আছে, তাদের খুঁজে বের করা
        logger.info("   🛠️ Checking existing channels for missing logos...")
        fixed_count = 0
        
        for ch in existing_channels:
            current_logo = ch.get('logoUrl', "")
            
            # যদি লোগো না থাকে বা ডিফল্ট লোগো থাকে
            if not current_logo or current_logo == DEFAULT_LOGO:
                logger.info(f"     🔎 Searching logo for existing channel: {ch['name']}...")
                real_logo = find_real_logo_online(ch['name'])
                
                if real_logo and real_logo != DEFAULT_LOGO:
                    ch['logoUrl'] = real_logo
                    fixed_count += 1
                    data_modified = True
                    logger.info(f"     ✅ Fixed Logo: {ch['name']}")
                    # সার্চের মাঝে একটু বিরতি (Rate Limit এড়াতে)
                    time.sleep(1) 

        if fixed_count > 0:
            logger.info(f"   🎉 Repaired {fixed_count} logos in existing list.")

        # --- PART 2: ADD NEW CHANNELS ---
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
                    if target.lower() in api_cats: is_match = True; break
            
            if is_match:
                # ডুপ্লিকেট এড়ানো
                if not any(s[0].get('channel') == ch_id for s in streams_to_check):
                    streams_to_check.append((stream, ch_details))

        if streams_to_check:
            logger.info(f"   ⚡ Found {len(streams_to_check)} potential NEW channels. Verifying...")
            
            new_channels_list = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                future_to_url = {executor.submit(process_stream_check, s, d): s for s, d in streams_to_check}

                for future in concurrent.futures.as_completed(future_to_url):
                    result = future.result()
                    if result:
                        ch_id, url, details = result
                        
                        # লোগো ডিসিশন
                        api_logo = details.get('logo')
                        final_logo = DEFAULT_LOGO
                        
                        if api_logo:
                            final_logo = api_logo
                        else:
                            # API তে লোগো নেই, তাই অনলাইনে সার্চ করবো
                            logger.info(f"     🌍 Scraping logo for NEW channel: {details.get('name')}")
                            final_logo = find_real_logo_online(details.get('name'))
                            time.sleep(1) # Safety delay

                        new_channel = {
                            "id": ch_id,
                            "name": details.get('name', 'Unknown Channel'),
                            "logoUrl": final_logo,
                            "streamUrls": [url],
                            "category": rules['category_name']
                        }
                        if rules['type'] == 'genre': new_channel["genre"] = rules['category_name']
                        
                        new_channels_list.append(new_channel)
                        print(f"     ✅ [NEW LIVE] {details.get('name')}")

            if new_channels_list:
                new_channels_list.sort(key=lambda x: x['name'])
                current_data['channels'].extend(new_channels_list)
                data_modified = True
                logger.info(f"   📥 Added {len(new_channels_list)} new channels.")

        # --- SAVE IF MODIFIED ---
        if data_modified:
            create_backup(filepath)
            atomic_save_json(filepath, current_data)
        else:
            logger.info("   😴 No changes needed.")

    logger.info("\n🎉 All updates completed!")

if __name__ == "__main__":
    update_channels_ultimate()

