import json
import requests
import os
import concurrent.futures
import shutil
import time
import logging
import tempfile
import random
from datetime import datetime

# --- 📚 LIBRARY IMPORT & SAFETY ---
DDGS = None
try:
    try:
        from ddgs import DDGS
    except ImportError:
        from duckduckgo_search import DDGS
except ImportError as e:
    print(f"⚠️ Warning: Search library missing. Logo updates will be skipped.")
    print(f"Details: {e}")

# --- ⚙️ CONFIGURATION (Ultimate) ---
BASE_DIR = os.getcwd()
CATEGORY_DIR = os.path.join(BASE_DIR, "categories")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")

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

# --- 🛡️ ANTI-BLOCKING: USER AGENTS ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/116.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
]

# --- 📝 LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger()

# --- 🕵️‍♂️ LOGO SCRAPPING ENGINE ---
SEARCH_FAIL_COUNT = 0
MAX_CONSECUTIVE_FAILS = 3
SEARCH_DISABLED = False

def find_real_logo_online(channel_name):
    global SEARCH_FAIL_COUNT, SEARCH_DISABLED, DDGS
    if SEARCH_DISABLED or DDGS is None: return DEFAULT_LOGO

    query = f"{channel_name} tv channel logo transparent wikipedia"
    try:
        with DDGS(timeout=10) as ddgs:
            results = list(ddgs.images(query, max_results=1))
            if results:
                SEARCH_FAIL_COUNT = 0
                return results[0]['image']
    except Exception as e:
        SEARCH_FAIL_COUNT += 1
        logger.warning(f"   ⚠️ Logo search failed for '{channel_name}': {e}")
        if SEARCH_FAIL_COUNT >= MAX_CONSECUTIVE_FAILS:
            logger.error("   🚫 Too many search failures. Disabling logo search.")
            SEARCH_DISABLED = True
    return DEFAULT_LOGO

# --- 🛡️ SAFETY & CLEANUP FUNCTIONS ---

def cleanup_old_backups():
    if not os.path.exists(BACKUP_DIR): return
    all_backups = [f for f in os.listdir(BACKUP_DIR) if f.endswith(".bak")]
    for filename in CATEGORY_RULES.keys():
        file_backups = [f for f in all_backups if f.startswith(f"{filename}_")]
        file_backups.sort()
        if len(file_backups) > MAX_BACKUPS_TO_KEEP:
            for old_file in file_backups[:-MAX_BACKUPS_TO_KEEP]:
                try: os.remove(os.path.join(BACKUP_DIR, old_file))
                except: pass

def create_backup(filepath):
    if not os.path.exists(filepath): return
    if not os.path.exists(BACKUP_DIR): os.makedirs(BACKUP_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    try: shutil.copy2(filepath, os.path.join(BACKUP_DIR, f"{os.path.basename(filepath)}_{timestamp}.bak"))
    except Exception as e: logger.warning(f"⚠️ Backup failed: {e}")

def atomic_save_json(filepath, data):
    dir_name = os.path.dirname(filepath)
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False, encoding='utf-8') as tmp_file:
        json.dump(data, tmp_file, indent=2, ensure_ascii=False)
        temp_name = tmp_file.name
    try:
        shutil.move(temp_name, filepath)
        logger.info(f"💾 Saved JSON: {os.path.basename(filepath)}")
    except Exception as e:
        logger.error(f"❌ Save failed: {e}")
        if os.path.exists(temp_name): os.remove(temp_name)

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {"channels": []}
    return {"channels": []}

# --- 🌐 NETWORK FUNCTIONS (ROTATING UA) ---

def get_headers():
    return {"User-Agent": random.choice(USER_AGENTS)}

def check_link_status(url):
    if not url: return False
    try:
        with requests.get(url, headers=get_headers(), stream=True, timeout=(3, 5)) as r:
            return r.status_code == 200
    except: return False

def get_alternative_working_stream(channel_id, streams_by_id):
    """API থেকে একই চ্যানেলের অন্য কোনো সচল লিঙ্ক খুঁজে বের করে"""
    candidates = streams_by_id.get(channel_id, [])
    for cand in candidates:
        url = cand.get('url')
        if check_link_status(url):
            return url
    return None

def process_stream_check(stream, details):
    url = stream.get('url')
    ch_id = stream.get('channel')
    if check_link_status(url):
        return (ch_id, url, details)
    return None

# --- 🚀 MAIN LOGIC ---

def update_channels_ultimate():
    logger.info("🚀 Starting Ultimate Channel Updater (Logo + Broken Link Fixer)...")
    cleanup_old_backups()

    try:
        logger.info("📡 Fetching IPTV Database...")
        api_streams = requests.get(STREAMS_API, timeout=10).json()
        api_channels = requests.get(CHANNELS_API, timeout=10).json()
        
        channel_info_map = {c['id']: c for c in api_channels}
        
        # 🆕 ফাস্ট লুকআপের জন্য স্ট্রিমগুলোকে ID দিয়ে সাজানো হচ্ছে
        streams_by_id = {}
        for s in api_streams:
            if s.get('status') not in ['error', 'offline']:
                cid = s.get('channel')
                if cid:
                    if cid not in streams_by_id: streams_by_id[cid] = []
                    streams_by_id[cid].append(s)

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

        # --- PART 1: MAINTENANCE (LOGOS & BROKEN LINKS) ---
        logger.info("   🛠️ Checking existing channels (Logos + Links)...")
        
        for ch in existing_channels:
            ch_id = ch.get('id')
            
            # 1. BROKEN LINK FIXER (🆕 ADDED)
            current_urls = ch.get('streamUrls', [])
            main_url_dead = False
            
            # বর্তমান লিঙ্ক চেক করা
            if not current_urls or not check_link_status(current_urls[0]):
                main_url_dead = True
                logger.warning(f"     ❌ Dead Link Found: {ch.get('name')}")
                
                # যদি লিঙ্ক ডেড হয়, আমরা নতুন লিঙ্ক খুঁজব
                new_url = get_alternative_working_stream(ch_id, streams_by_id)
                
                if new_url and new_url != current_urls[0] if current_urls else True:
                    ch['streamUrls'] = [new_url]
                    data_modified = True
                    logger.info(f"     🩹 Repaired Link: {ch.get('name')} -> New URL Found")
                else:
                    logger.warning(f"     ⚠️ No alternative stream found for: {ch.get('name')}")

            # 2. LOGO FIXER (EXISTING)
            if not SEARCH_DISABLED:
                current_logo = ch.get('logoUrl', "")
                if not current_logo or current_logo == DEFAULT_LOGO:
                    real_logo = find_real_logo_online(ch['name'])
                    if real_logo and real_logo != DEFAULT_LOGO:
                        ch['logoUrl'] = real_logo
                        data_modified = True
                        logger.info(f"     ✅ Fixed Logo: {ch.get('name')}")
                        time.sleep(1)

        # --- PART 2: ADD NEW CHANNELS ---
        streams_to_check = []
        for ch_id, streams in streams_by_id.items():
            if ch_id in existing_ids: continue 
            
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
                # প্রথম স্ট্রিমটি নিচ্ছি চেক করার জন্য
                streams_to_check.append((streams[0], ch_details))

        if streams_to_check:
            logger.info(f"   ⚡ Found {len(streams_to_check)} potential NEW channels...")
            
            new_channels_list = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                # মডিফাইড: process_stream_check ব্যবহার করা হচ্ছে
                futures = [executor.submit(process_stream_check, s, d) for s, d in streams_to_check]
                
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        ch_id, url, details = result
                        
                        api_logo = details.get('logo')
                        final_logo = DEFAULT_LOGO
                        if api_logo: final_logo = api_logo
                        elif not SEARCH_DISABLED:
                            final_logo = find_real_logo_online(details.get('name'))
                        
                        new_channel = {
                            "id": ch_id,
                            "name": details.get('name'),
                            "logoUrl": final_logo,
                            "streamUrls": [url],
                            "category": rules['category_name']
                        }
                        if rules['type'] == 'genre': new_channel["genre"] = rules['category_name']
                        new_channels_list.append(new_channel)
                        print(f"     ✅ [NEW] {details.get('name')}")

            if new_channels_list:
                new_channels_list.sort(key=lambda x: x['name'])
                current_data['channels'].extend(new_channels_list)
                data_modified = True
                logger.info(f"   📥 Added {len(new_channels_list)} new channels.")

        if data_modified:
            create_backup(filepath)
            atomic_save_json(filepath, current_data)
        
    logger.info("\n🎉 All updates completed!")

if __name__ == "__main__":
    update_channels_ultimate()
