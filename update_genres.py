import requests
import json
import os
import time

# --- Configuration ---
# GitHub Secret থেকে API কী নেওয়া হবে
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
# OpenRouter-এর একটি জনপ্রিয় ফ্রি মডেল, যা এই কাজের জন্য যথেষ্ট
MODEL_NAME = "mistralai/mistral-7b-instruct:free" 
CATEGORIES_DIR = "categories"
# AI-কে এই ক্যাটাগরিগুলোর মধ্যেই উত্তর দিতে বলা হবে
VALID_GENRES = ["Sports", "News", "Entertainment", "Movies", "Music", "Kids", "Informative", "Lifestyle", "Religion", "Unknown"]

def get_genre_from_ai(channel_name):
    """OpenRouter AI ব্যবহার করে চ্যানেলের জেনার বের করে।"""
    if not OPENROUTER_API_KEY:
        print("  ! ERROR: OPENROUTER_API_KEY is not set. Skipping AI classification.")
        return "Unknown"

    prompt = f"Based on the TV channel name '{channel_name}', classify it into ONE of the following categories: {', '.join(VALID_GENRES)}. Respond with only the single category name, nothing else."
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/cybernahid-dev/StreamX-Ultra", # Recommended by OpenRouter
        "X-Title": "StreamX IPTV Categorizer" # Recommended by OpenRouter
    }
    
    data = { "model": MODEL_NAME, "messages": [{"role": "user", "content": prompt}] }
    
    try:
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=data, timeout=30)
        
        if response.status_code == 429:
            print("    Rate limit hit. Waiting for 60 seconds...")
            time.sleep(60)
            return "Unknown" # পরেরবার আবার চেষ্টা করা হবে

        response.raise_for_status()
        result = response.json()
        genre = result['choices'][0]['message']['content'].strip().title().replace("_", " ")

        # উত্তরটি আমাদের দেওয়া তালিকার মধ্যে আছে কি না তা যাচাই করা
        if genre in VALID_GENRES:
            return genre
        
        print(f"  ! AI returned an invalid genre: '{genre}'. Marking as Unknown.")
        return "Unknown"
        
    except requests.exceptions.RequestException as e:
        print(f"  ! AI classification failed for '{channel_name}': {e}")
        return "Unknown"

def process_json_file(file_path):
    """একটি JSON ফাইল পড়ে, genre যোগ করে এবং প্রয়োজন হলে আপডেট করে।"""
    print(f"\nProcessing file: {file_path}")
    file_updated = False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # events.json ফাইলটিকে এড়িয়ে যাওয়া
        if 'events' in data:
            print("  - Skipping events.json file.")
            return False

        for channel in data.get('channels', []):
            # যদি 'genre' ফিল্ডটি না থাকে বা 'Unknown' হয়
            if not channel.get('genre') or channel.get('genre') == 'Unknown':
                print(f"  - Classifying '{channel.get('name', 'No Name')}'...")
                new_genre = get_genre_from_ai(channel.get('name', ''))
                
                if new_genre != 'Unknown':
                    channel['genre'] = new_genre
                    print(f"    -> Classified as: {new_genre}")
                    file_updated = True
                else:
                    print(f"    -> Could not classify. Will try again later.")
                
                time.sleep(2) # প্রতিটি API কলের মধ্যে ২ সেকেন্ড বিরতি, রেট লিমিট এড়ানোর জন্য

        if file_updated:
            print(f"  -> File '{file_path}' has been updated. Saving changes.")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        else:
            print(f"  - No new genres to add in {file_path}.")
            return False
            
    except Exception as e:
        print(f"  ! Error processing {file_path}: {e}")
        return False

if __name__ == "__main__":
    if not os.path.isdir(CATEGORIES_DIR):
        print(f"Error: Directory '{CATEGORIES_DIR}' not found.")
        exit(1)
        
    any_file_changed = False
    for filename in sorted(os.listdir(CATEGORIES_DIR)):
        if filename.endswith(".json"):
            file_path = os.path.join(CATEGORIES_DIR, filename)
            if process_json_file(file_path):
                any_file_changed = True
    
    if not any_file_changed:
        print("\nAll channel genres are up-to-date. No changes made.")
    else:
        print("\nGenre update process finished. Some files were modified.")
