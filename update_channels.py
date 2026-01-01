import json
import requests
import os

# ==========================================
# কনফিগারেশন সেকশন
# ==========================================
CATEGORY_CONFIG = {
    # দেশ ভিত্তিক (Country Based)
    "categories/bangladesh.json": {"type": "country", "filter": "BD", "category_name": "Bangladesh"},
    "categories/india.json": {"type": "country", "filter": "IN", "category_name": "India"},
    "categories/usa.json": {"type": "country", "filter": "US", "category_name": "USA"},
    "categories/uk.json": {"type": "country", "filter": "GB", "category_name": "UK"},
    "categories/uae.json": {"type": "country", "filter": "AE", "category_name": "UAE"},
    
    # ক্যাটাগরি ভিত্তিক (Genre Based)
    "categories/sports.json": {"type": "genre", "filter": ["sports"], "category_name": "Sports"},
    "categories/kids.json": {"type": "genre", "filter": ["kids", "animation"], "category_name": "Kids"},
    "categories/music.json": {"type": "genre", "filter": ["music"], "category_name": "Music"},
    "categories/informative.json": {"type": "genre", "filter": ["documentary", "education", "science"], "category_name": "Informative"}
}

# API URLs
STREAMS_API = "https://iptv-org.github.io/api/streams.json"
CHANNELS_API = "https://iptv-org.github.io/api/channels.json"

# ডিফল্ট লোগো (যদি কোনো লোগো না পাওয়া যায়)
DEFAULT_LOGO = "https://i.ibb.co/2Wn7bYf/now-rock-logo.png" # আপনি চাইলে চেঞ্জ করতে পারেন

# ==========================================
# হেল্পার ফাংশন: লিংক চেক করার জন্য
# ==========================================
def is_url_working(url):
    """
    Check if a URL returns a 200 OK status.
    Uses HEAD request for speed (doesn't download image).
    """
    if not url or len(url) < 5:
        return False
    try:
        # Timeout 2 সেকেন্ড দেওয়া হলো যাতে স্ক্রিপ্ট স্লো না হয়
        response = requests.head(url, timeout=2, allow_redirects=True)
        return response.status_code == 200
    except:
        return False

def load_existing_channels(filename):
    """
    Load current channels from file to preserve custom logos.
    """
    if not os.path.exists(filename):
        return {}
    
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # ID দিয়ে ডিকশনারি বানানো হচ্ছে
            return {ch['id']: ch for ch in data.get('channels', [])}
    except:
        return {}

# ==========================================
# মেইন আপডেট ফাংশন
# ==========================================
def update_files():
    print("Fetching latest data from iptv-org...")
    try:
        streams = requests.get(STREAMS_API).json()
        channels_data = requests.get(CHANNELS_API).json()
        channel_info_map = {c['id']: c for c in channels_data}
    except Exception as e:
        print(f"Error fetching API: {e}")
        return

    for filename, config in CATEGORY_CONFIG.items():
        print(f"\nProcessing {filename}...")
        
        # ১. আগের ডাটা লোড করা (যাতে আমরা আগের লোগো চেক করতে পারি)
        existing_channels = load_existing_channels(filename)
        
        new_channel_dict = {}
        
        # ২. নতুন স্ট্রিম প্রসেস করা
        for stream in streams:
            ch_id = stream.get('channel')
            
            # বেসিক ভ্যালিডেশন
            if not ch_id or ch_id not in channel_info_map:
                continue
            if stream.get('status') != 'online':
                continue # শুধু অনলাইন চ্যানেল নেওয়া হবে
                
            ch_api_data = channel_info_map[ch_id]
            is_match = False

            # ৩. ফিল্টারিং (দেশ বা জেনরা)
            if config['type'] == 'country':
                if ch_api_data.get('country') == config['filter']:
                    is_match = True
            elif config['type'] == 'genre':
                ch_cats = ch_api_data.get('categories', [])
                for target in config['filter']:
                    if target in ch_cats:
                        is_match = True
                        break
            
            if is_match:
                # ৪. চ্যানেল অবজেক্ট তৈরি বা আপডেট করা
                if ch_id not in new_channel_dict:
                    
                    # --- লোগো সিলেকশন লজিক (সবচেয়ে গুরুত্বপূর্ণ অংশ) ---
                    final_logo = ""
                    
                    # ক) আগে ফাইলটিতে এই চ্যানেল ছিল কিনা চেক করুন
                    if ch_id in existing_channels:
                        old_logo = existing_channels[ch_id].get('logoUrl')
                        
                        # যদি আগের লোগো থাকে এবং সেটা কাজ করে, তবে সেটাই রাখুন
                        if is_url_working(old_logo):
                            final_logo = old_logo
                            # print(f"Keeping existing logo for {ch_id}")
                    
                    # খ) যদি আগের লোগো না থাকে বা কাজ না করে, তবে API এর লোগো চেক করুন
                    if not final_logo:
                        api_logo = ch_api_data.get('logo')
                        if is_url_working(api_logo):
                            final_logo = api_logo
                            # print(f"Using API logo for {ch_id}")
                    
                    # গ) যদি কোনো লোগোই কাজ না করে, তবে খালি রাখুন বা ডিফল্ট দিন
                    if not final_logo:
                        final_logo = "" # অথবা DEFAULT_LOGO ব্যবহার করতে পারেন

                    # অবজেক্ট তৈরি
                    new_channel_dict[ch_id] = {
                        "id": ch_id,
                        "name": ch_api_data.get('name', 'Unknown'),
                        "logoUrl": final_logo,
                        "streamUrls": [],
                        "category": config['category_name']
                    }
                    
                    # যদি জেনরা স্পেসিফিক হয় তবে genre ফিল্ড এড করা ভালো
                    if config['type'] == 'genre':
                         new_channel_dict[ch_id]["genre"] = config['category_name']

                # স্ট্রিম লিংক এড করা (ডুপ্লিকেট চেক সহ)
                url = stream.get('url')
                if url and url not in new_channel_dict[ch_id]['streamUrls']:
                    new_channel_dict[ch_id]['streamUrls'].append(url)

        # ৫. ফাইল সেভ করা
        final_list = list(new_channel_dict.values())
        final_list.sort(key=lambda x: x['name']) # নামের সিরিয়ালে সাজানো

        output_data = {"channels": final_list}
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            print(f"✅ Saved {filename}: {len(final_list)} channels.")
        except Exception as e:
            print(f"❌ Error writing {filename}: {e}")

if __name__ == "__main__":
    update_files()

