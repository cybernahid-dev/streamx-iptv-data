import json
import requests
import os
import concurrent.futures

# --- CONFIGURATION ---
CATEGORY_DIR = "categories"
STREAMS_API = "https://iptv-org.github.io/api/streams.json"
CHANNELS_API = "https://iptv-org.github.io/api/channels.json"

# আপনার ফাইলের নামের সাথে API ফিল্টার রুলস
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

# --- HELPER FUNCTIONS ---

def check_link_status(url):
    """
    লিংকটি জীবিত কিনা চেক করে।
    Timeout 5 সেকেন্ড করা হয়েছে।
    """
    if not url: return False
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    try:
        response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
        return response.status_code == 200
    except:
        return False

def load_json(filepath):
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"channels": []}
    return {"channels": []}

def save_json(filepath, data):
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def process_stream_check(stream, details, existing_urls):
    """
    এটি একটি নির্দিষ্ট স্ট্রিম চেক করে।
    মাল্টি-থ্রেডিং এর জন্য ব্যবহৃত হবে।
    """
    url = stream.get('url')
    ch_id = stream.get('channel')
    
    # ১. যদি লিংকটি ইতিমধ্যে আপনার ফাইলে থাকে, তবে চেক করার দরকার নেই (নিরাপদ)
    if url in existing_urls:
        return None 

    # ২. নতুন লিংক হলে চেক করি সেটা জীবিত কি না
    if check_link_status(url):
        return (ch_id, url, details) # সফল হলে ডাটা রিটার্ন করবে
    
    return None # ডেড লিংক হলে কিছু রিটার্ন করবে না

# --- MAIN LOGIC ---

def update_channels():
    print("📡 Fetching API Data from iptv-org...")
    try:
        api_streams = requests.get(STREAMS_API).json()
        api_channels = requests.get(CHANNELS_API).json()
        
        # চ্যানেল ইনফো ম্যাপ
        channel_info_map = {c['id']: c for c in api_channels}
    except Exception as e:
        print(f"❌ Critical Error fetching API: {e}")
        return

    if not os.path.exists(CATEGORY_DIR):
        os.makedirs(CATEGORY_DIR)

    for filename, rules in CATEGORY_RULES.items():
        filepath = os.path.join(CATEGORY_DIR, filename)
        print(f"\n🔄 Processing: {filename}...")

        # ১. বর্তমান ডাটা লোড (আপনার ম্যানুয়াল ডাটা মেমোরিতে রাখা হচ্ছে)
        current_data = load_json(filepath)
        channel_map = {ch['id']: ch for ch in current_data.get('channels', [])}
        
        # বর্তমান সব লিংক একটি সেটে রাখা (ডুপ্লিকেট এড়ানোর জন্য)
        all_existing_urls = set()
        for ch in channel_map.values():
            for u in ch.get('streamUrls', []):
                all_existing_urls.add(u)

        # ২. API থেকে পোটেনশিয়াল স্ট্রিম ফিল্টার করা
        streams_to_check = []
        for stream in api_streams:
            ch_id = stream.get('channel')
            if not ch_id or ch_id not in channel_info_map: continue
            
            # API স্ট্যাটাস ফিল্টার
            if stream.get('status') == 'error' or stream.get('status') == 'offline': continue

            ch_details = channel_info_map[ch_id]
            is_match = False

            # রুলস চেকিং
            if rules['type'] == 'country':
                if ch_details.get('country') == rules['filter']: is_match = True
            elif rules['type'] == 'genre':
                api_cats = [c.lower() for c in ch_details.get('categories', [])]
                for target in rules['filter']:
                    if target.lower() in api_cats:
                        is_match = True
                        break
            
            if is_match:
                streams_to_check.append((stream, ch_details))

        print(f"   - Found {len(streams_to_check)} potential streams. Checking live status...")

        # ৩. প্যারালাল প্রসেসিং (Thread Pool - 10 Workers)
        new_links_count = 0
        new_channels_count = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_url = {
                executor.submit(process_stream_check, s, d, all_existing_urls): s 
                for s, d in streams_to_check
            }

            for future in concurrent.futures.as_completed(future_to_url):
                result = future.result()
                if result:
                    # যদি লিংকটি লাইভ হয় তবেই আমরা এখানে আসবো
                    ch_id, url, details = result
                    
                    # API থেকে লোগো বের করা
                    api_logo = details.get('logo')

                    if ch_id in channel_map:
                        # [SCENARIO A] চ্যানেলটি ইতিমধ্যে আছে
                        
                        # ১. লিংক যোগ করা (যদি নতুন হয়)
                        if url not in channel_map[ch_id]['streamUrls']:
                            channel_map[ch_id]['streamUrls'].append(url)
                            new_links_count += 1
                        
                        # ২. লোগো চেক (Smart Backfill)
                        # যদি আপনার ফাইলে লোগো না থাকে, শুধু তখনই API লোগো বসাবে
                        # আপনার ম্যানুয়াল লোগো থাকলে হাত দেবে না
                        current_logo = channel_map[ch_id].get('logoUrl', '')
                        if not current_logo and api_logo:
                            channel_map[ch_id]['logoUrl'] = api_logo
                            print(f"     [UPDATE] Added missing logo for: {channel_map[ch_id]['name']}")

                    else:
                        # [SCENARIO B] একদম নতুন চ্যানেল
                        
                        # ১. লোগো চেক (Strict Policy)
                        # যদি API তে লোগো না থাকে, আমরা চ্যানেলটি অ্যাড করবো না
                        if not api_logo:
                            continue # Skip adding this channel

                        # সব শর্ত পূরণ হলে নতুন চ্যানেল তৈরি
                        new_channel = {
                            "id": ch_id,
                            "name": details.get('name', 'Unknown Channel'),
                            "logoUrl": api_logo,
                            "streamUrls": [url],
                            "category": rules['category_name']
                        }
                        # Genre থাকলে অ্যাড হবে
                        if rules['type'] == 'genre':
                             new_channel["genre"] = rules['category_name']
                        
                        channel_map[ch_id] = new_channel
                        new_channels_count += 1
                        print(f"     [NEW] Added: {details.get('name')}")

        # ৪. ফাইল সেভ
        final_list = list(channel_map.values())
        
        # অপশনাল: নাম অনুযায়ী সাজাতে চাইলে নিচের লাইন আনকমেন্ট করুন
        # final_list.sort(key=lambda x: x['name']) 

        save_json(filepath, {"channels": final_list})
        print(f"✅ Saved {filename}: +{new_channels_count} New Channels, +{new_links_count} New Links.")

if __name__ == "__main__":
    update_channels()

