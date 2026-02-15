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
    from ddgs import DDGS
except ImportError:
    print(f"⚠️ Warning: 'ddgs' library missing. Logo updates will be skipped.")

# --- ⚙️ CONFIGURATION (Ultimate) ---
BASE_DIR = os.getcwd()
CATEGORY_DIR = os.path.join(BASE_DIR, "categories")
BACKUP_DIR = os.path.join(BASE_DIR, "backups")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
PLAYLIST_DIR = os.path.join(BASE_DIR, "playlists")

MAX_BACKUPS_TO_KEEP = 3
MAX_STREAMS_PER_CHANNEL = 3

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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

# --- 📊 REPORTING STATS ---
STATS = {
    "checked": 0,
    "manual_skipped": 0,
    "repaired": 0,
    "logo_fixed": 0,
    "added": 0,
    "files_updated": 0,
    "m3u_generated": 0
}

# --- 📝 LOGGING SETUP ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger()

# --- 🕵️‍♂️ LOGO SCRAPPING ENGINE ---
SEARCH_FAIL_COUNT = 0
MAX_CONSECUTIVE_FAILS = 5
SEARCH_DISABLED = False

def find_real_logo_online(channel_name):
    global SEARCH_FAIL_COUNT, SEARCH_DISABLED, DDGS
    if SEARCH_DISABLED or DDGS is None: return DEFAULT_LOGO

    query = f"{channel_name} tv channel logo transparent wikipedia"
    try:
        # DDGS লাইব্রেরির সঠিক ব্যবহার
        with DDGS() as ddgs:
            # max_results=1 ব্যবহার করা হয়েছে দ্রুত রেজাল্টের জন্য
            results = list(ddgs.images(query, max_results=1))
            if results:
                SEARCH_FAIL_COUNT = 0
                return results[0]['image']
    except Exception as e:
        SEARCH_FAIL_COUNT += 1
        logger.warning(f"   ⚠️ Logo search failed for '{channel_name}': {str(e)}")
        if SEARCH_FAIL_COUNT >= MAX_CONSECUTIVE_FAILS:
            logger.error("   🚫 Too many search failures. Disabling logo search.")
            SEARCH_DISABLED = True
        time.sleep(2) # API রেট লিমিট এড়াতে ডিলে
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
    if not os.path.exists(dir_name): os.makedirs(dir_name)
    
    with tempfile.NamedTemporaryFile('w', dir=dir_name, delete=False, encoding='utf-8') as tmp_file:
        json.dump(data, tmp_file, indent=2, ensure_ascii=False)
        temp_name = tmp_file.name
    try:
        shutil.move(temp_name, filepath)
        logger.info(f"💾 Saved JSON: {os.path.basename(filepath)}")
        STATS["files_updated"] += 1
    except Exception as e:
        logger.error(f"❌ Save failed: {e}")
        if os.path.exists(temp_name): os.remove(temp_name)

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f: return json.load(f)
        except: return {"channels": []}
    return {"channels": []}

# --- 🎵 M3U GENERATOR FUNCTIONS ---

def generate_m3u_from_json(json_data, filename):
    if not os.path.exists(PLAYLIST_DIR): os.makedirs(PLAYLIST_DIR)
    
    m3u_filename = filename.replace(".json", ".m3u")
    m3u_path = os.path.join(PLAYLIST_DIR, m3u_filename)
    
    content = ["#EXTM3U"]
    
    for ch in json_data.get('channels', []):
        urls = ch.get('streamUrls', [])
        if not urls: continue
        
        name = ch.get('name', 'Unknown')
        logo = ch.get('logoUrl', '')
        cid = ch.get('id', '')
        group = ch.get('category', 'Uncategorized')
        stream_url = urls[0] 
        
        line = f'#EXTINF:-1 tvg-id="{cid}" tvg-logo="{logo}" group-title="{group}",{name}'
        content.append(line)
        content.append(stream_url)
    
    try:
        with open(m3u_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        logger.info(f"🎵 Generated M3U: {m3u_filename}")
        STATS["m3u_generated"] += 1
    except Exception as e:
        logger.error(f"❌ M3U Generation failed for {filename}: {e}")

def generate_master_playlist(all_channels):
    if not os.path.exists(PLAYLIST_DIR): os.makedirs(PLAYLIST_DIR)
    master_path = os.path.join(PLAYLIST_DIR, "all_channels.m3u")
    
    content = ["#EXTM3U"]
    for ch in all_channels:
        urls = ch.get('streamUrls', [])
        if not urls: continue
        
        name = ch.get('name', 'Unknown')
        logo = ch.get('logoUrl', '')
        cid = ch.get('id', '')
        group = ch.get('category', 'Uncategorized')
        stream_url = urls[0]
        
        line = f'#EXTINF:-1 tvg-id="{cid}" tvg-logo="{logo}" group-title="{group}",{name}'
        content.append(line)
        content.append(stream_url)
        
    try:
        with open(master_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))
        logger.info(f"🌟 Generated Master Playlist: all_channels.m3u (Total: {len(all_channels)})")
    except Exception as e:
        logger.error(f"❌ Master M3U failed: {e}")

def write_summary_report():
    if not os.path.exists(REPORT_DIR): os.makedirs(REPORT_DIR)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = os.path.join(REPORT_DIR, f"report_{timestamp}.txt")
    
    content = f"""
    ========================================
       IPTV UPDATE & M3U GENERATOR REPORT
       Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    ========================================
    
    📊 Statistics:
    ----------------------------------------
    ✅ Total Channels Checked : {STATS['checked']}
    🛡️ Manual Channels Skipped: {STATS['manual_skipped']}
    🩹 Broken Links Repaired  : {STATS['repaired']}
    🖼️ Logos Fixed            : {STATS['logo_fixed']}
    🆕 New Channels Added     : {STATS['added']}
    
    📂 File Operations:
    ----------------------------------------
    💾 JSON Files Updated     : {STATS['files_updated']}
    🎵 M3U Playlists Created  : {STATS['m3u_generated']} + 1 Master
    
    ========================================
    """
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"📄 Report generated: {filename}")
    except Exception as e:
        logger.error(f"❌ Failed to write report: {e}")

# --- 🌐 NETWORK FUNCTIONS ---

def get_headers():
    return {"User-Agent": random.choice(USER_AGENTS)}

def check_link_status(url):
    if not url: return False
    try:
        with requests.get(url, headers=get_headers(), stream=True, timeout=(4, 7)) as r:
            return r.status_code == 200
    except: return False

def get_multiple_working_streams(channel_id, streams_by_id):
    candidates = streams_by_id.get(channel_id, [])
    if not candidates: return []

    working_urls = []
    # সর্বোচ্চ ৫টি লিঙ্ক চেক করবে টাইম বাঁচাতে
    check_limit = candidates[:5] 
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(check_link_status, s.get('url')): s.get('url') for s in check_limit}
        
        for future in concurrent.futures.as_completed(future_to_url):
            url = future_to_url[future]
            try:
                if future.result():
                    working_urls.append(url)
                    # ৩টি সচল লিঙ্ক পেলেই থামবে
                    if len(working_urls) >= MAX_STREAMS_PER_CHANNEL:
                        break
            except: pass
            
    return working_urls

# --- 🚀 MAIN LOGIC ---

def update_channels_ultimate():
    logger.info("🚀 Starting Ultimate Channel Updater (JSON + M3U)...")
    cleanup_old_backups()

    try:
        logger.info("📡 Fetching IPTV Database...")
        api_streams = requests.get(STREAMS_API, timeout=15).json()
        api_channels = requests.get(CHANNELS_API, timeout=15).json()
        
        channel_info_map = {c['id']: c for c in api_channels}
        
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
    
    all_channels_collection = []

    for filename, rules in CATEGORY_RULES.items():
        filepath = os.path.join(CATEGORY_DIR, filename)
        logger.info(f"\n🔍 Processing: {filename}")

        current_data = load_json(filepath)
        existing_channels = current_data.get('channels', [])
        existing_ids = {ch['id'] for ch in existing_channels}
        
        data_modified = False

        # --- PART 1: MAINTENANCE (Fix Links & Logos) ---
        for ch in existing_channels:
            STATS["checked"] += 1
            ch_id = ch.get('id')
            
            if ch_id not in channel_info_map:
                STATS["manual_skipped"] += 1
                continue 

            # Fix Broken Links
            current_urls = ch.get('streamUrls', [])
            main_url_dead = False
            
            if not current_urls or not check_link_status(current_urls[0]):
                main_url_dead = True
            
            if main_url_dead or len(current_urls) < 2:
                new_working_urls = get_multiple_working_streams(ch_id, streams_by_id)
                if new_working_urls:
                    if new_working_urls != current_urls:
                        ch['streamUrls'] = new_working_urls
                        data_modified = True
                        STATS["repaired"] += 1
                        logger.info(f"     🩹 Streams Updated: {ch.get('name')}")

            # Fix Missing Logos
            if not SEARCH_DISABLED:
                current_logo = ch.get('logoUrl', "")
                if not current_logo or current_logo == DEFAULT_LOGO:
                    real_logo = find_real_logo_online(ch['name'])
                    if real_logo and real_logo != DEFAULT_LOGO:
                        ch['logoUrl'] = real_logo
                        data_modified = True
                        STATS["logo_fixed"] += 1
                        logger.info(f"     ✅ Logo Updated: {ch.get('name')}")
                        time.sleep(2) # Politeness delay for search

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
                streams_to_check.append(ch_id)

        if streams_to_check:
            logger.info(f"   ⚡ Found {len(streams_to_check)} potential NEW channels...")
            new_channels_list = []
            
            def process_new_channel(target_ch_id):
                details = channel_info_map.get(target_ch_id)
                working_urls = get_multiple_working_streams(target_ch_id, streams_by_id)
                if working_urls:
                    return (details, working_urls)
                return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(process_new_channel, cid) for cid in streams_to_check]
                for future in concurrent.futures.as_completed(futures):
                    res = future.result()
                    if res:
                        details, urls = res
                        final_logo = details.get('logo')
                        if not final_logo and not SEARCH_DISABLED:
                            final_logo = find_real_logo_online(details.get('name'))
                        
                        langs = details.get('languages', [])
                        
                        new_channel = {
                            "id": details.get('id'),
                            "name": details.get('name'),
                            "logoUrl": final_logo or DEFAULT_LOGO,
                            "streamUrls": urls,
                            "category": rules['category_name'],
                            "languages": langs
                        }
                        if rules['type'] == 'genre': new_channel["genre"] = rules['category_name']
                        new_channels_list.append(new_channel)
                        STATS["added"] += 1
                        logger.info(f"     ✅ [NEW] {details.get('name')}")

            if new_channels_list:
                new_channels_list.sort(key=lambda x: x['name'])
                current_data['channels'].extend(new_channels_list)
                data_modified = True
                logger.info(f"   📥 Added {len(new_channels_list)} new channels.")

        # Save JSON if modified
        if data_modified:
            create_backup(filepath)
            atomic_save_json(filepath, current_data)
        
        # Always generate M3U
        generate_m3u_from_json(current_data, filename)
        
        # Add to master collection
        all_channels_collection.extend(current_data.get('channels', []))

    # --- FINAL: GENERATE MASTER PLAYLIST ---
    if all_channels_collection:
        generate_master_playlist(all_channels_collection)

    write_summary_report()
    logger.info("\n🎉 All updates completed! Check 'playlists' folder for M3U files.")

if __name__ == "__main__":
    update_channels_ultimate()
