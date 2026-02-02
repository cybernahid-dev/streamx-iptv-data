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
except ImportError:
    print(f"⚠️ Warning: Search library missing. Using Wikipedia backup only.")

# --- ⚙️ CONFIGURATION ---
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

# --- 🛡️ USER AGENTS ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
]

STATS = {
    "checked": 0, "manual_skipped": 0, "repaired": 0,
    "logo_fixed": 0, "added": 0, "files_updated": 0, "m3u_generated": 0
}

# --- 📝 LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%H:%M:%S')
logger = logging.getLogger()

# --- 🕵️‍♂️ LOGO ENGINE (DUCKDUCKGO + WIKIPEDIA FALLBACK) ---
SEARCH_DISABLED = False

def get_wikipedia_logo(query):
    """Wikipedia API থেকে লোগো খোঁজার ফাংশন"""
    try:
        # ১. পেজ খোঁজা
        search_url = "https://en.wikipedia.org/w/api.php"
        search_params = {
            "action": "query", "list": "search", "srsearch": f"{query} TV channel",
            "format": "json", "srlimit": 1
        }
        r = requests.get(search_url, params=search_params, timeout=5).json()
        if not r.get('query', {}).get('search'): return None
        
        title = r['query']['search'][0]['title']

        # ২. লোগো ইমেজ বের করা
        img_params = {
            "action": "query", "titles": title, "prop": "pageimages",
            "pithumbsize": 500, "format": "json"
        }
        r = requests.get(search_url, params=img_params, timeout=5).json()
        pages = r.get('query', {}).get('pages', {})
        
        for k, v in pages.items():
            if 'thumbnail' in v:
                return v['thumbnail']['source']
    except Exception as e:
        logger.warning(f"   ⚠️ Wiki Search failed: {e}")
    return None

def find_real_logo_online(channel_name):
    global SEARCH_DISABLED
    
    # Method 1: DuckDuckGo (Primary)
    if not SEARCH_DISABLED and DDGS:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.images(f"{channel_name} tv logo transparent", max_results=1))
                if results: return results[0]['image']
        except Exception:
            # DDGS fail করলে আমরা উইকিপিডিয়া ট্রাই করব
            pass 

    # Method 2: Wikipedia API (Backup - Very Reliable)
    logger.info(f"     🌍 Trying Wikipedia backup for: {channel_name}")
    wiki_logo = get_wikipedia_logo(channel_name)
    if wiki_logo: return wiki_logo

    return DEFAULT_LOGO

# --- 🛠️ UTILS ---
def cleanup_old_backups():
    if not os.path.exists(BACKUP_DIR): return
    # (Cleanup logic simplified for brevity)
    pass

def create_backup(filepath):
    if not os.path.exists(filepath): return
    if not os.path.exists(BACKUP_DIR): os.makedirs(BACKUP_DIR)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    try: shutil.copy2(filepath, os.path.join(BACKUP_DIR, f"{os.path.basename(filepath)}_{timestamp}.bak"))
    except: pass

def save_json(filepath, data):
    with tempfile.NamedTemporaryFile('w', dir=os.path.dirname(filepath), delete=False, encoding='utf-8') as tf:
        json.dump(data, tf, indent=2, ensure_ascii=False)
        tempname = tf.name
    shutil.move(tempname, filepath)
    STATS["files_updated"] += 1

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f: return json.load(f)
        except: pass
    return {"channels": []}

# --- 🌐 NETWORK ---
def check_link_status(url):
    if not url: return False
    try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        with requests.get(url, headers=headers, stream=True, timeout=4) as r:
            return 200 <= r.status_code < 400
    except: return False

def get_working_streams(candidate_streams):
    working = []
    # Check max 5 streams per channel to save time
    for s in candidate_streams[:5]: 
        if check_link_status(s.get('url')):
            working.append(s.get('url'))
            if len(working) >= 1: break # ১টা পেলেই হবে (ফাস্ট আপডেটের জন্য)
    return working

# --- 🎵 M3U GENERATOR ---
def generate_m3u(json_data, filename):
    if not os.path.exists(PLAYLIST_DIR): os.makedirs(PLAYLIST_DIR)
    content = ["#EXTM3U"]
    for ch in json_data.get('channels', []):
        if not ch.get('streamUrls'): continue
        line = f'#EXTINF:-1 tvg-id="{ch.get("id")}" tvg-logo="{ch.get("logoUrl")}" group-title="{ch.get("category")}",{ch.get("name")}'
        content.append(line)
        content.append(ch['streamUrls'][0])
    
    with open(os.path.join(PLAYLIST_DIR, filename.replace(".json", ".m3u")), 'w', encoding='utf-8') as f:
        f.write('\n'.join(content))
    STATS["m3u_generated"] += 1

def generate_master_playlist(all_channels):
    if not os.path.exists(PLAYLIST_DIR): os.makedirs(PLAYLIST_DIR)
    content = ["#EXTM3U"]
    for ch in all_channels:
        if not ch.get('streamUrls'): continue
        line = f'#EXTINF:-1 tvg-id="{ch.get("id")}" tvg-logo="{ch.get("logoUrl")}" group-title="{ch.get("category")}",{ch.get("name")}'
        content.append(line)
        content.append(ch['streamUrls'][0])
    
    with open(os.path.join(PLAYLIST_DIR, "all_channels.m3u"), 'w', encoding='utf-8') as f:
        f.write('\n'.join(content))

# --- 🚀 MAIN ---
def update_channels():
    logger.info("🚀 Starting Channel Update (Broken Links + Wiki Logo Backup)...")
    
    try:
        api_streams = requests.get(STREAMS_API, timeout=15).json()
        api_channels = requests.get(CHANNELS_API, timeout=15).json()
    except Exception as e:
        logger.error(f"❌ API Fail: {e}")
        return

    channel_map = {c['id']: c for c in api_channels}
    streams_map = {}
    for s in api_streams:
        if s.get('status') not in ['error', 'offline'] and s.get('channel'):
            streams_map.setdefault(s['channel'], []).append(s)

    if not os.path.exists(CATEGORY_DIR): os.makedirs(CATEGORY_DIR)
    all_channels_master = []

    for filename, rules in CATEGORY_RULES.items():
        logger.info(f"🔍 Processing: {filename}")
        filepath = os.path.join(CATEGORY_DIR, filename)
        data = load_json(filepath)
        valid_channels = []
        modified = False
        existing_ids = set()

        # 1. MAINTENANCE (FIX LINKS + LOGOS)
        for ch in data.get('channels', []):
            STATS["checked"] += 1
            cid = ch.get('id')
            existing_ids.add(cid)
            
            # A. Broken Link Fixer
            current_urls = ch.get('streamUrls', [])
            if not current_urls or not check_link_status(current_urls[0]):
                logger.warning(f"   ❌ Dead Link: {ch['name']}")
                fresh = get_working_streams(streams_map.get(cid, []))
                if fresh:
                    ch['streamUrls'] = fresh
                    modified = True
                    STATS["repaired"] += 1
                    logger.info(f"   🩹 Fixed Link for: {ch['name']}")
            
            # B. Logo Fixer (with Wiki Backup)
            if not ch.get('logoUrl') or ch['logoUrl'] == DEFAULT_LOGO:
                new_logo = find_real_logo_online(ch['name'])
                if new_logo and new_logo != DEFAULT_LOGO:
                    ch['logoUrl'] = new_logo
                    modified = True
                    STATS["logo_fixed"] += 1
                    logger.info(f"   ✅ Logo Updated: {ch['name']}")
            
            valid_channels.append(ch)

        # 2. ADD NEW CHANNELS
        potential = []
        for cid, info in channel_map.items():
            if cid in existing_ids: continue
            
            match = False
            if rules['type'] == 'country' and info.get('country') == rules['filter']: match = True
            elif rules['type'] == 'genre':
                cats = [x.lower() for x in info.get('categories', [])]
                if any(f in cats for f in rules['filter']): match = True
            
            if match: potential.append(cid)

        if potential:
            logger.info(f"   ⚡ Checking {len(potential)} new candidates...")
            # Using thread pool to check streams faster
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                future_map = {ex.submit(get_working_streams, streams_map.get(pid, [])): pid for pid in potential}
                for f in concurrent.futures.as_completed(future_map):
                    pid = future_map[f]
                    urls = f.result()
                    if urls:
                        info = channel_map[pid]
                        # Try to get logo
                        logo = info.get('logo')
                        if not logo: logo = find_real_logo_online(info['name'])
                        
                        new_ch = {
                            "id": pid, "name": info['name'],
                            "logoUrl": logo or DEFAULT_LOGO,
                            "streamUrls": urls,
                            "category": rules['category_name'],
                            "languages": info.get('languages', [])
                        }
                        valid_channels.append(new_ch)
                        STATS["added"] += 1
                        modified = True
                        print(f"   ✅ Added: {info['name']}")

        if modified:
            valid_channels.sort(key=lambda x: x['name'])
            data['channels'] = valid_channels
            create_backup(filepath)
            save_json(filepath, data)
        
        generate_m3u(data, filename)
        all_channels_master.extend(valid_channels)

    generate_master_playlist(all_channels_master)
    logger.info(f"\n🎉 Done! Stats: Repaired={STATS['repaired']}, Logos={STATS['logo_fixed']}, Added={STATS['added']}")

if __name__ == "__main__":
    update_channels()
