import requests
import json
import os
import time

# --- Configuration ---
# GitHub Secret থেকে API কী নেওয়া হবে
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
# OpenRouter-এর একটি জনপ্রিয় ফ্রি মডেল
MODEL_NAME = "mistralai/mistral-7b-instruct:free" 
CATEGORIES_DIR = "categories"

# AI-কে এই ক্যাটাগরিগুলোর মধ্যেই উত্তর দিতে বলা হবে
VALID_GENRES = ["Sports", "News", "Entertainment", "Movies", "Music", "Kids", "Informative", "Lifestyle", "Religion", "Unknown"]

def get_genre_from_ai(channel_name):
    """OpenRouter AI ব্যবহার করে চ্যানেলের জেনার বের করে।"""
    if not OPENROUTER_API_KEY:
        # Key না থাকলে Unknown রিটার্ন করবে, প্রিন্ট একবারই মেইনে দেওয়া হবে
        return "Unknown"

    prompt = f"Based on the TV channel name '{channel_name}', classify it into ONE of the following categories: {', '.join(VALID_GENRES)}. Respond with only the single category name, nothing else."
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/cybernahid-dev/StreamX-Ultra",
        "X-Title": "StreamX IPTV Categorizer"
    }
    
    data = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1 # কম টেম্পারেচার মানে বেশি সঠিক উত্তর
    }
    
    try:
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=data, timeout=10)
        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content'].strip()
            # ক্লিনআপ: যদি AI অতিরিক্ত টেক্সট দেয়
            for genre in VALID_GENRES:
                if genre.lower() in content.lower():
                    return genre
            return "Unknown"
        else:
            print(f"  ! API Error {response.status_code}: {response.text}")
            return "Unknown"
    except Exception as e:
        print(f"  ! Connection Error: {e}")
        return "Unknown"

def process_json_file(file_path):
    """একটি JSON ফাইল পড়ে জেনার আপডেট করে।"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # JSON স্ট্রাকচার হ্যান্ডলিং (লিস্ট নাকি অবজেক্ট)
        channels = []
        is_dict = False
        
        if isinstance(data, list):
            channels = data
        elif isinstance(data, dict) and "channels" in data:
            channels = data["channels"]
            is_dict = True
        else:
            print(f"  - Invalid JSON structure in {file_path}")
            return False

        file_updated = False
        print(f"Processing {file_path} ({len(channels)} channels)...")

        for channel in channels:
            # যদি জেনার না থাকে বা Unknown থাকে, তবেই AI কল হবে
            current_genre = channel.get("genre", "Unknown")
            
            if current_genre == "Unknown" or not current_genre:
                name = channel.get("name", "")
                print(f"  ? Identifying genre for: {name}")
                
                new_genre = get_genre_from_ai(name)
                
                if new_genre != 'Unknown':
                    channel['genre'] = new_genre.upper() # অ্যাপে ENUM Uppercase এ থাকে
                    print(f"    -> Classified as: {new_genre}")
                    file_updated = True
                else:
                    print(f"    -> Could not classify.")
                
                # API রেট লিমিট এড়ানোর জন্য বিরতি
                time.sleep(2) 

        if file_updated:
            print(f"  -> Saving updates to '{file_path}'")
            # ডেটা আবার আগের ফরম্যাটে সেভ করা
            output_data = {"channels": channels} if is_dict else channels
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            return True
        else:
            print(f"  - No changes needed for {file_path}.")
            return False
            
    except Exception as e:
        print(f"  ! Error processing {file_path}: {e}")
        return False

if __name__ == "__main__":
    # 1. Directory Check
    if not os.path.exists(CATEGORIES_DIR):
        print(f"Error: Directory '{CATEGORIES_DIR}' not found. Cannot update genres.")
        exit(1) # Fail action if dir missing

    # 2. API Key Check
    if not OPENROUTER_API_KEY:
        print("WARNING: OPENROUTER_API_KEY is not set. AI classification will be skipped.")
        # আমরা এক্সিট করব না, কোড রান হবে কিন্তু জেনার 'Unknown' থাকবে
        
    any_file_changed = False
    
    # ইভেন্ট ফাইল বাদে বাকি সব ফাইল চেক করো
    for filename in sorted(os.listdir(CATEGORIES_DIR)):
        if filename.endswith(".json") and filename != "events.json":
            file_path = os.path.join(CATEGORIES_DIR, filename)
            if process_json_file(file_path):
                any_file_changed = True
    
    if any_file_changed:
        print("\nGenre update complete. Changes saved.")
    else:
        print("\nAll channel genres are up-to-date.")

