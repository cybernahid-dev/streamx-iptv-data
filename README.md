# 🌐 StreamX Ultra – Official IPTV JSON Data

[![GitHub Repo stars](https://img.shields.io/github/stars/yourusername/streamx-iptv-data?style=social)](https://github.com/yourusername/streamx-iptv-data)  
[![GitHub license](https://img.shields.io/github/license/yourusername/streamx-iptv-data)](LICENSE)

---

## 🚀 Overview

**StreamX Ultra** is a futuristic IPTV platform designed to deliver **live TV channels**, **HD streams**, **sports events**, and **informative content** directly to your app.  
This repository contains **structured JSON data** for all categories, including auto-updating country channels, movies, kids content, sports, and informative channels.

All JSON files are structured to **auto-integrate with the StreamX Ultra app**, providing seamless updates and a rich user experience.

---

## 📂 Repository Structure


streamx-iptv-data/ │ ├── index.json                # Master index file for all categories ├── auto_m3u_to_json.py       # Automated Python script for M3U to JSON & GitHub update └── categories/               # All category-wise JSON ├── bangladesh.json ├── india.json ├── usa.json ├── sports.json ├── movies.json ├── kids.json └── informative.json

---

## 🏷️ Categories

| Category       | Description                                        | Icon  |
|----------------|----------------------------------------------------|-------|
| Bangladesh     | All Bangladeshi TV channels                        | 🇧🇩    |
| India          | All Indian TV channels                              | 🇮🇳    |
| USA            | All USA channels                                   | 🇺🇸    |
| Sports         | Live sports channels with HD streams & schedules  | 🏅    |
| Movies         | Action, Entertainment & Movie channels            | 🎬    |
| Kids           | Children’s & Cartoon channels                      | 🧒    |
| Informative    | Discovery, Science, Documentary, Animal, History | 🔬 🐅 🏛️ 🎥 🧠 🌍 |

---

## ⚡ Features

- **HD Streams:** All channels marked with `isHD: true`.
- **Featured Channels:** Top channels auto-featured for every category.
- **Kids Parental Control:** `parentalControl: true` flag for all kids channels.
- **Live Sports Integration:** Channels include live events and upcoming matches with countdown timers.
- **Auto Daily Update:** Python script can be scheduled via Termux or cron job to refresh JSON automatically.
- **GitHub Push:** Auto push to repo ensures StreamX Ultra app always fetches the latest data.
- **JSON Structure:** Fully compatible with StreamX Ultra app.

---

## 🛠️ Automated Script

- **File:** `auto_m3u_to_json.py`  
- **Functions:**
  - Parse M3U links per category
  - Generate category-wise JSON files
  - Assign featured channels and HD flag
  - Add `liveEvent` objects for sports channels
  - Update master `index.json`
  - Auto push files to GitHub repository

- **Dependencies:**
  ```bash
  pip install requests PyGithub

Run manually:

python auto_m3u_to_json.py

Run daily (Termux loop):

while true; do
  python ~/streamx-iptv-data/auto_m3u_to_json.py
  sleep 86400
done

Run daily (Linux cron job example):

0 3 * * * /usr/bin/python3 /home/user/streamx-iptv-data/auto_m3u_to_json.py



---

## 🌐 Master Index

File: index.json

Contains references to all category JSON files.

Example structure:


{
  "appName": "StreamX Ultra",
  "version": "1.0.0",
  "categories": [
    {
      "id": "cat_bangladesh",
      "name": "Bangladesh",
      "file": "categories/bangladesh.json",
      "parentalControl": false
    },
    {
      "id": "cat_sports",
      "name": "Sports",
      "file": "categories/sports.json",
      "parentalControl": false
    }
  ]
}


---

## 🔗 Integration with StreamX Ultra App

1. Clone the repository:

git clone https://github.com/cybernahid-dev/streamx-iptv-data.git


2. Point your StreamX Ultra app to the raw GitHub URL:

https://raw.githubusercontent.com/cybernahid-dev/streamx-iptv-data/main/index.json


3. App will automatically fetch all categories and channels.




---

## 📝 Contribution Guidelines

Pull requests are welcome for new channels, M3U updates, or improvements.

Ensure all JSON follows the same structure.

Do not include private M3U links without proper authorization.



---

## 📄 License

This repository is licensed under MIT License – see the LICENSE file for details.


---

## 🔮 Future Roadmap

🔹 Real-time live sports API integration

🔹 Push notifications for upcoming matches

🔹 Regional category expansion (Europe, Asia, Africa)

🔹 User ratings & channel popularity tracking

🔹 HD/4K stream detection and tagging



---

> Made with ❤️ for StreamX Ultra by cybernahid-dev



---

