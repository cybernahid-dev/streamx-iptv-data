import json
import requests
import os

# শুধুমাত্র categories/ ফোল্ডারের ফাইলগুলো প্রসেস করবে
CATEGORY_DIR = "categories"

# আগের মতো কনফিগারেশন, কিন্তু এখানে শুধু ফিল্টার লজিক থাকবে
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

STREAMS_API = "https://iptv-org.github.io/api/streams.json"
CHANNELS_API = "https://iptv-org.github.io/api/channels.json"

def is_url_working(url):
    if not url or len(url) < 5: return False
    try:
        response = requests.head(url, timeout=2, allow_redirects=True)
        return response.status_code == 200
    except: return False

def update_files():
    print("Fetching data from iptv-org...")
    try:
        streams = requests.get(STREAMS_API).json()
        channels_data = requests.get(CHANNELS_API).json()
        channel_info_map = {c['id']: c for c in channels_data}
    except Exception as e:
        print(f"Error: {e}")
        return

    # শুধুমাত্র categories ফোল্ডারের ফাইলগুলো চেক করা
    for filename in os.listdir(CATEGORY_DIR):
        if filename not in CATEGORY_RULES:
            continue
            
        filepath = os.path.join(CATEGORY_DIR, filename)
        config = CATEGORY_RULES[filename]
        
        print(f"Updating existing file: {filepath}")
        
        # বর্তমান ফাইল থেকে লোগো বা ডাটা রিড করা
        existing_channels = {}
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
                existing_channels = {ch['id']: ch for ch in data.get('channels', [])}
        except: pass

        new_channel_dict = {}
        
        for stream in streams:
            ch_id = stream.get('channel')
            if not ch_id or ch_id not in channel_info_map or stream.get('status') != 'online':
                continue
                
            ch_api_data = channel_info_map[ch_id]
            is_match = False

            # ক্যাটাগরি ফিল্টার
            if config['type'] == 'country':
                if ch_api_data.get('country') == config['filter']: is_match = True
            elif config['type'] == 'genre':
                ch_cats = ch_api_data.get('categories', [])
                for target in config['filter']:
                    if target in ch_cats:
                        is_match = True
                        break
            
            if is_match:
                if ch_id not in new_channel_dict:
                    # লোগো লজিক: আগেরটা ঠিক থাকলে সেটা থাকবে, নয়তো নতুন
                    final_logo = ""
                    if ch_id in existing_channels:
                        old_logo = existing_channels[ch_id].get('logoUrl', '')
                        if is_url_working(old_logo):
                            final_logo = old_logo
                    
                    if not final_logo:
                        api_logo = ch_api_data.get('logo', '')
                        if is_url_working(api_logo):
                            final_logo = api_logo

                    new_channel_dict[ch_id] = {
                        "id": ch_id,
                        "name": ch_api_data.get('name', 'Unknown'),
                        "logoUrl": final_logo,
                        "streamUrls": [],
                        "category": config['category_name']
                    }

                url = stream.get('url')
                if url and url not in new_channel_dict[ch_id]['streamUrls']:
                    new_channel_dict[ch_id]['streamUrls'].append(url)

        # ডাটা সেভ করা (একই ফাইলে)
        if new_channel_dict:
            final_list = list(new_channel_dict.values())
            final_list.sort(key=lambda x: x['name'])
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({"channels": final_list}, f, indent=2, ensure_ascii=False)
            print(f"✅ {filename} updated with {len(final_list)} channels.")

if __name__ == "__main__":
    update_files()

