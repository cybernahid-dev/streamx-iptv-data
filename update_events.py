import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime, timedelta
import os
import random
import time

# --- Configuration ---
CATEGORIES_DIR = "categories"
OUTPUT_FILE = os.path.join(CATEGORIES_DIR, "events.json")

# শক্তিশালী হেডার যা ব্রাউজারের মতো আচরণ করবে
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0"
]

CHANNEL_MAPPING_RULES = {
    "asia cup": ["gtv_bd", "tsports_bd", "star_sports_1_in"],
    "ipl": ["star_sports_1_in", "colors_in", "tsports_bd"],
    "bpl": ["gtv_bd", "tsports_bd"],
    "world cup": ["gtv_bd", "tsports_bd", "star_sports_1_in", "ptv_sports_pk"],
    "india": ["star_sports_1_in", "sony_ten_1_in"],
    "bangladesh": ["gtv_bd", "tsports_bd"],
    "pakistan": ["ptv_sports_pk", "ten_sports_pk"],
    "football": ["sony_ten_2_in", "bein_sports_1_hd"]
}

def get_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1"
    }

def load_all_channels():
    channels = {}
    if not os.path.exists(CATEGORIES_DIR):
        os.makedirs(CATEGORIES_DIR, exist_ok=True)
        return channels
    for filename in os.listdir(CATEGORIES_DIR):
        if filename.endswith(".json") and filename != "events.json":
            try:
                with open(os.path.join(CATEGORIES_DIR, filename), 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    c_list = data.get("channels", []) if isinstance(data, dict) else data
                    for ch in c_list:
                        if isinstance(ch, dict) and "id" in ch: channels[ch["id"]] = ch
            except: pass
    return channels

def map_channels(text, available_channels):
    matched = set()
    text = text.lower()
    for kw, ids in CHANNEL_MAPPING_RULES.items():
        if kw in text:
            for cid in ids:
                if cid in available_channels: matched.add(cid)
    return list(matched)

# --- Source 1: Cricbuzz ---
def fetch_cricbuzz():
    events = []
    try:
        url = "https://www.cricbuzz.com/cricket-schedule/upcoming-series/international"
        res = requests.get(url, headers=get_headers(), timeout=15)
        soup = BeautifulSoup(res.content, 'html.parser')
        matches = soup.select(".cb-series-matches, .cb-mtch-lst")
        for m in matches:
            title_tag = m.find("a")
            if title_tag:
                title = title_tag.text.strip()
                events.append({
                    "title": title,
                    "tournament": "Cricket Series",
                    "startTime": datetime.now().isoformat(),
                    "team1_logo": f"https://ui-avatars.com/api/?name={title[0:2]}&background=random",
                    "team2_logo": f"https://ui-avatars.com/api/?name={title[-2:]}&background=random"
                })
    except Exception as e: print(f"Cricbuzz Error: {e}")
    return events

# --- Source 2: Alternative (Google Search Based) ---
def fetch_google_fallback():
    events = []
    try:
        # এটি সরাসরি গুগল থেকে বড় বড় সিরিজের তথ্য খোঁজার ট্রাই করবে
        url = "https://www.google.com/search?q=upcoming+cricket+matches+international"
        res = requests.get(url, headers=get_headers(), timeout=15)
        if "Cricket" in res.text:
            events.append({
                "title": "International Match (Check Live)",
                "tournament": "Google Sports Update",
                "startTime": datetime.now().isoformat(),
                "team1_logo": "https://cdn-icons-png.flaticon.com/512/806/806542.png",
                "team2_logo": "https://cdn-icons-png.flaticon.com/512/806/806542.png"
            })
    except: pass
    return events

if __name__ == "__main__":
    if not os.path.exists(CATEGORIES_DIR): os.makedirs(CATEGORIES_DIR)
    
    print("🔄 Loading Channels...")
    available_channels = load_all_channels()
    
    print("📡 Fetching from Source 1: Cricbuzz...")
    all_scraped = fetch_cricbuzz()
    
    # যদি ১ম সোর্স কাজ না করে বা কম ডেটা পায়, ২য় সোর্স ব্যবহার করবে
    if len(all_scraped) < 2:
        print("⚠️ Source 1 limited. Trying Source 2 (Fallback)...")
        all_scraped += fetch_google_fallback()
        time.sleep(random.uniform(1, 3)) # Anti-block delay
    
    # ম্যাপিং চ্যানেল আইডি
    for ev in all_scraped:
        ev["channelIds"] = map_channels(ev["title"] + " " + ev["tournament"], available_channels)

    # রেজাল্ট সেভ করা (ডেটা না পেলেও ফাইল আপডেট হবে যাতে অ্যাপ এরর না দেয়)
    output = {"events": all_scraped}
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Finished! Total {len(all_scraped)} events saved to {OUTPUT_FILE}")

