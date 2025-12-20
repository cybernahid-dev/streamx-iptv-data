import requests
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor

# --- কনফিগারেশন ---
CATEGORIES_DIR = "categories" # আপনার JSON ফাইলগুলোর ফোল্ডার
IPTV_ORG_BASE_URL = "https://raw.githubusercontent.com/iptv-org/iptv/master/streams/"
# বিভিন্ন দেশের M3U ফাইল থেকে লিঙ্ক সংগ্রহ করা হবে
SOURCE_FILES = ["bd.m3u", "in.m3u", "uk.m3u", "us.m3u", "ca.m3u", "au.m3u"]

# --- ধাপ ১: সমস্ত উৎস থেকে লিঙ্ক সংগ্রহ এবং একটি ডিকশনারিতে রাখা ---
def fetch_all_source_links():
    """সবগুলো M3U ফাইল থেকে লিঙ্ক সংগ্রহ করে একটি বড় ডিকশনারি তৈরি করে।"""
    print("Fetching all source links from iptv-org...")
    all_links = {}
    
    def fetch_url(file_name):
        url = f"{IPTV_ORG_BASE_URL}{file_name}"
        try:
            response = requests.get(url, timeout=20)
            response.raise_for_status()
            lines = response.text.split('\n')
            
            source_channels = {}
            for i in range(0, len(lines) - 1, 2):
                if lines[i].startswith('#EXTINF:'):
                    # নামের মধ্যে থাকা অতিরিক্ত ট্যাগ (যেমন (720p)) বাদ দেওয়া হচ্ছে
                    name_part = lines[i].split(',')[-1].strip()
                    clean_name = name_part.split('(')[0].strip()
                    
                    channel_url = lines[i+1].strip()
                    if clean_name and channel_url:
                        # যদি একই চ্যানেলের একাধিক লিঙ্ক পাওয়া যায়, সেগুলো লিস্টে যোগ করা হবে
                        if clean_name not in source_channels:
                            source_channels[clean_name] = []
                        source_channels[clean_name].append(channel_url)
            return source_channels
        except requests.exceptions.RequestException:
            return {}

    with ThreadPoolExecutor(max_workers=len(SOURCE_FILES)) as executor:
        results = executor.map(fetch_url, SOURCE_FILES)
        for result in results:
            for name, urls in result.items():
                if name not in all_links:
                    all_links[name] = []
                all_links[name].extend(urls)
                
    print(f"Total unique channels fetched from sources: {len(all_links)}")
    return all_links

# --- ধাপ ২: লিঙ্ক পরীক্ষা করার ফাংশন (FFprobe ব্যবহার করে) ---
def is_link_working(url):
    """একটি স্ট্রিম লিঙ্ক কাজ করছে কি না তা পরীক্ষা করে।"""
    command = [
        'ffprobe', '-v', 'error', '-i', url,
        '-show_entries', 'stream=codec_type',
        '-of', 'csv=p=0'
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=10)
        return result.returncode == 0 and 'video' in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

# --- ধাপ ৩: আপনার JSON ফাইল আপডেট করার মূল লজিক ---
def process_json_file(file_path, source_links):
    print(f"\nProcessing file: {file_path}")
    file_updated = False
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for channel in data.get('channels', []):
            channel_name = channel.get('name')
            stream_urls = channel.get('streamUrls', [])
            
            # লিঙ্কগুলো সমান্তরালভাবে পরীক্ষা করা হবে
            with ThreadPoolExecutor(max_workers=5) as executor:
                working_status = list(executor.map(is_link_working, stream_urls))
            
            working_urls = [url for url, is_working in zip(stream_urls, working_status) if is_working]
            broken_urls_count = len(stream_urls) - len(working_urls)

            if broken_urls_count > 0:
                print(f"  - Channel '{channel_name}': Found {broken_urls_count} broken link(s).")
                channel['streamUrls'] = working_urls # শুধুমাত্র কার্যকরী লিঙ্কগুলো রাখা হলো
                file_updated = True
                
                # কার্যকরী লিঙ্ক খুঁজে বের করার চেষ্টা
                potential_new_links = source_links.get(channel_name, [])
                if potential_new_links:
                    print(f"    Searching for replacement links for '{channel_name}'...")
                    for new_link in potential_new_links:
                        if new_link not in working_urls: # ডুপ্লিকেট যোগ করা হবে না
                            if is_link_working(new_link):
                                print(f"    + Found working replacement: {new_link}")
                                channel['streamUrls'].append(new_link)
                                break # একটি কার্যকরী লিঙ্ক পেলেই যথেষ্ট
        
        if file_updated:
            print(f"  -> File '{file_path}' has been updated. Saving changes.")
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        return file_updated

    except Exception as e:
        print(f"  ! Error processing {file_path}: {e}")
        return False

# --- মূল 실행 ---
if __name__ == "__main__":
    all_source_links = fetch_all_source_links()
    
    if not all_source_links:
        print("Could not fetch any source links. Exiting.")
        exit(1)

    if not os.path.isdir(CATEGORIES_DIR):
        print(f"Error: Directory '{CATEGORIES_DIR}' not found.")
        exit(1)
        
    any_file_changed = False
    for filename in os.listdir(CATEGORIES_DIR):
        if filename.endswith(".json"):
            file_path = os.path.join(CATEGORIES_DIR, filename)
            if process_json_file(file_path, all_source_links):
                any_file_changed = True
    
    if not any_file_changed:
        print("\nAll files are up-to-date. No changes made.")
    else:
        print("\nUpdate process finished. Some files were modified.")
