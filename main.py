import os
import json
import time
import subprocess
import re
from datetime import datetime

TRACKER_FILE = "tracker.json"
INPUT_DIR = "input_keywords"
KEYWORD_MAPPINGS_DIR = "keyword_mappings"

os.makedirs(INPUT_DIR, exist_ok=True)
os.makedirs(KEYWORD_MAPPINGS_DIR, exist_ok=True)

def load_tracker():
    if os.path.exists(TRACKER_FILE):
        with open(TRACKER_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_tracker(data):
    with open(TRACKER_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

def run_scraper(keyword_file_path):
    print(f"  🚀 Running scraper for file: {keyword_file_path}")
    if os.name == 'nt':
        git_bash_path = r"C:\Program Files\Git\bin\bash.exe"
        cmd = [git_bash_path, "scraper.sh", keyword_file_path] if os.path.exists(git_bash_path) else ["bash", "scraper.sh", keyword_file_path]
    else:
        os.chmod("scraper.sh", 0o755)
        cmd = ["./scraper.sh", keyword_file_path]
        
    result = subprocess.run(cmd)
    return result.returncode == 0

def main():
    print("=" * 60)
    print("🤖 OrderMonk Scraper - Processing Manual Keyword Files")
    print("=" * 60)

    tracker = load_tracker()

    files_to_process = [f for f in os.listdir(INPUT_DIR) if f.endswith('.txt')]

    if not files_to_process:
        print(f"No keyword files found in '{INPUT_DIR}/'.")
        print("Please add a .txt file named after the category (e.g., 'Premium Face Wash.txt') with keywords line-by-line.")
        return

    processed_count = 0
    BATCH_SIZE = 5 # Limit per run if you add a lot

    for file_name in files_to_process:
        if processed_count >= BATCH_SIZE:
             print("\nReached batch size limit. The workflow will pick up the rest on the next run!")
             break

        category_name = file_name.replace(".txt", "").strip()
        filepath = os.path.join(INPUT_DIR, file_name)

        if category_name not in tracker:
             tracker[category_name] = {"status": "unscraped"}
        
        info = tracker[category_name]

        if isinstance(info, dict) and info.get("status") == "scraped":
             print(f"\n⏭️ Skipping '{category_name}' (Already scraped!)")
             continue

        print(f"\n📂 Processing Category: '{category_name}' from {file_name}")

        # Count keywords for summary
        with open(filepath, "r", encoding="utf-8") as f:
            keywords = [line.strip() for line in f if line.strip()]

        print(f"  ✅ Found {len(keywords)} keywords to scrape.")

        # Trigger Scraper passing the file directly
        success = run_scraper(filepath)

        if success:
            tracker[category_name]["status"] = "scraped"
            tracker[category_name]["scraped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Save mapping optionally
            safe_name = re.sub(r'[^A-Za-z0-9]', '_', category_name)
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            keywords_filename = f"{timestamp}_{safe_name}.json"
            
            mapping_filepath = os.path.join(KEYWORD_MAPPINGS_DIR, keywords_filename)
            keyword_data = {
                "category": category_name,
                "keywords_count": len(keywords),
                "mapped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "keywords": list(keywords)
            }
            
            with open(mapping_filepath, "w", encoding="utf-8") as map_file:
                json.dump(keyword_data, map_file, indent=4)
                
            tracker[category_name]["keywords_file"] = mapping_filepath
            save_tracker(tracker)
            print(f"  ✅ '{category_name}' successfully marked as SCRAPED.")
        else:
            print(f"  ❌ Scraper failed for '{category_name}'. Status remains UNSCRAPED.")
            
        processed_count += 1
        time.sleep(3)

    print("\n" + "=" * 60)
    print("📊 Daily Run Complete!")
    print("=" * 60)

if __name__ == "__main__":
    main()
