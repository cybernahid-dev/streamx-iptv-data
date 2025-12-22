import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import os
import re

# --- Configuration ---
CRICBUZZ_SCHEDULE_URL = "https://www.cricbuzz.com/cricket-schedule/upcoming-series/international"
CATEGORIES_DIR = "categories"
OUTPUT_FILE = os.path.join(CATEGORIES_DIR, "events.json")

# চ্যানেল ম্যাপিং-এর জন্য কীওয়ার্ড
CHANNEL_MAPPING_RULES = {
    # টুর্নামেন্টের নামের উপর ভিত্তি করে
    "asia cup": ["gtv_bd", "tsports_bd", "star_sports_1_in"],
    "indian premier league": ["star_sports_1_in", "colors_in"],
    "the ashes": ["sky_sports_main_event_uk", "sony_ten_5_in", "willow_cricket_hd"],
    "t20 world cup": ["gtv_bd", "tsports_bd", "star_sports_1_in", "ptv_sports_pk", "willow_cricket_hd"],
    "odi world cup": ["gtv_bd", "tsports_bd", "star_sports_1_in", "ptv_sports_pk", "willow_cricket_hd"],
    "premier league": ["sky_sports_main_event_uk", "sky_sports_football_uk"],
    "champions league": ["bein_sports_1_hd", "sport_tv_1_pt"],

    # দলের নামের উপর ভিত্তি করে
    "india": ["star_sports_1_in", "sony_ten_1_in", "dd_sports_in"],
    "bangladesh": ["gtv_bd", "tsports_bd"],
    "pakistan": ["ptv_sports_pk", "ten_sports_pk"],
    "england": ["sky_sports_main_event_uk"],
    "australia": ["fox_sports_au", "willow_cricket_hd"]
}

TEAM_LOGOS = {
    "india": "https://www.cricbuzz.com/a/img/v1/25x25/i1/c172115/india.jpg",
    "pakistan": "https://www.cricbuzz.com/a/img/v1/25x25/i1/c172119/pakistan.jpg",
    "bangladesh": "https://www.cricbuzz.com/a/img/v1/25x25/i1/c172120/bangladesh.jpg",
    "australia": "https://www.cricbuzz.com/a/img/v1/25x25/i1/c172112/australia.jpg",
    "england": "https://www.cricbuzz.com/a/img/v1/25x25/i1/c172114/england.jpg",
    "south africa": "https://www.cricbuzz.com/a/img/v1/25x25/i1/c172117/south-africa.jpg",
    "new zealand": "https://www.cricbuzz.com/a/img/v1/25x25/i1/c172113/new-zealand.jpg",
    "sri lanka": "https://www.cricbuzz.com/a/img/v1/25x25/i1/c172118/sri-lanka.jpg",
    "afghanistan": "https://www.cricbuzz.com/a/img/v1/25x25/i1/c172121/afghanistan.jpg",
    "west indies": "https://www.cricbuzz.com/a/img/v1/25x25/i1/c172116/west-indies.jpg",
    "ireland": "https://www.cricbuzz.com/a/img/v1/25x25/i1/c172122/ireland.jpg",
    "zimbabwe": "https://www.cricbuzz.com/a/img/v1/25x25/i1/c172123/zimbabwe.jpg"
}

def get_logo_for_team(team_name):
    """দলের নামের উপর ভিত্তি করে লোগোর URL খুঁজে বের করে।"""
    for key, url in TEAM_LOGOS.items():
        if key in team_name.lower():
            return url
    return ""

def load_all_channels():
    """সব JSON ফাইল থেকে চ্যানেল ID এবং নাম লোড করে।"""
    all_channels = {}
    if not os.path.isdir(CATEGORIES_DIR):
        print(f"Error: Directory '{CATEGORIES_DIR}' not found.")
        return {}
        
    for filename in os.listdir(CATEGORIES_DIR):
        if filename.endswith(".json") and filename != "events.json":
            file_path = os.path.join(CATEGORIES_DIR, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for channel in data.get('channels', []):
                        channel_id = channel.get('id')
                        if channel_id:
                            all_channels[channel_id] = channel.get('name', '').lower()
            except Exception as e:
                print(f"  - Error reading channel file {filename}: {e}")
    return all_channels

def map_event_to_channels(event_text, all_channels_map):
    """একটি ইভেন্টের টেক্সটের উপর ভিত্তি করে সম্ভাব্য চ্যানেল ID-গুলো খুঁজে বের করে।"""
    matched_channel_ids = set()
    lower_text = event_text.lower()

    for keyword, channel_ids in CHANNEL_MAPPING_RULES.items():
        if keyword in lower_text:
            for cid in channel_ids:
                if cid in all_channels_map:
                    matched_channel_ids.add(cid)
    
    return list(matched_channel_ids)

def scrape_cricbuzz_schedule(all_channels_map):
    """Cricbuzz থেকে সময়সূচী স্ক্র্যাপ করে এবং চ্যানেল ম্যাপ করে।"""
    print("Scraping Cricbuzz for upcoming cricket matches...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(CRICBUZZ_SCHEDULE_URL, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        
        events = []
        match_cards = soup.find_all("div", class_="cb-sch-lst-row")
        
        for card in match_cards:
            try:
                title_elem = card.find("a", class_="text-hvr-underline")
                if not title_elem: continue
                title = title_elem.text.strip()

                teams = title.split(",")[0].split(" vs ")
                if len(teams) < 2: continue
                team1_name = teams[0].strip()
                team2_name = teams[1].strip()

                series_elem = card.find("div", class_="cb-font-12 text-gray")
                tournament = series_elem.text.strip() if series_elem else "International Match"
                
                time_elem = card.find("span", title="Time in GMT")
                date_elem = card.find("span", class_="schedule-date")
                
                if not time_elem or not date_elem or not date_elem.has_attr('ng-if'): continue
                
                time_str = time_elem.text.strip().replace(" GMT", "")
                date_str_js = date_elem['ng-if']
                date_match = re.search(r"'(.*?)'", date_str_js)
                if not date_match: continue
                date_str = date_match.group(1)
                
                dt_str = f"{date_str} {time_str}"
                dt_obj = datetime.strptime(dt_str, "%b %d, %Y %H:%M")
                start_time_iso = dt_obj.strftime("%Y-%m-%dT%H:%M:%SZ")
                
                search_text = f"{title} {tournament}" 
                mapped_channel_ids = map_event_to_channels(search_text, all_channels_map)
                
                event = {
                    "title": title,
                    "team1_logo": get_logo_for_team(team1_name),
                    "team2_logo": get_logo_for_team(team2_name),
                    "startTime": start_time_iso,
                    "tournament": tournament,
                    "channelIds": mapped_channel_ids
                }
                events.append(event)
                
            except Exception as e:
                print(f"  - Could not parse a match card: {e}")

        print(f"Successfully scraped and mapped {len(events)} events.")
        return events

    except Exception as e:
        print(f"Error scraping Cricbuzz: {e}")
        return []

if __name__ == "__main__":
    print("Loading all channel data for mapping...")
    available_channels = load_all_channels()
    
    if not available_channels:
        print("Could not load any channel data. Cannot perform channel mapping.")
        exit(1)
        
    scraped_events = scrape_cricbuzz_schedule(available_channels)
    
    if scraped_events:
        output_data = {"events": scraped_events}
        try:
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            print(f"Successfully saved events to {OUTPUT_FILE}")
        except IOError as e:
            print(f"Error saving events to file: {e}")
    else:
        print("No events were scraped. The output file was not updated.")
