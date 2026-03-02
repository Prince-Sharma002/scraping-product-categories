import os
import csv
import json
import time
import subprocess
import re
from datetime import datetime
from google import genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
if not api_key:
    print("Error: GOOGLE_GEMINI_API_KEY not found in environment.")
    exit(1)

client = genai.Client(api_key=api_key)

CSV_FILE = "ultra_deep_marketplace_taxonomy_1000_plus.csv"
TRACKER_FILE = "tracker.json"
KEYWORD_MAPPINGS_DIR = "keyword_mappings"

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

def initialize_tracker_from_csv():
    tracker = load_tracker()
    
    if not os.path.exists(CSV_FILE):
        print(f"Error: CSV file {CSV_FILE} not found.")
        return tracker

    added_count = 0
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if "Level 4" not in reader.fieldnames:
             print("Error: 'Level 4' column not found in CSV. Make sure headers are correct.")
             return tracker
             
        for row in reader:
            category_name = row.get("Level 4", "").strip()
            if category_name and category_name not in tracker:
                tracker[category_name] = {
                    "status": "unscraped",
                    "keywords_file": None,
                    "scraped_at": None,
                    "generated_keywords": []
                }
                added_count += 1
                
    if added_count > 0:
        save_tracker(tracker)
        print(f"Added {added_count} new categories to tracker based on CSV.")
        
    return tracker

def generate_keywords(category_name):
    print(f"  Calling Gemini for category: '{category_name}'...")
    prompt = (
        f"You are an e-commerce SEO and PPC expert. "
        f"Generate exactly 5 highly relevant e-commerce search keywords for the product category: '{category_name}'. "
        f"Return ONLY a comma-separated list of the 5 keywords, with no numbers, bullet points, or extra text."
    )
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            text = response.text.strip()
            if ',' in text:
                keywords = [kw.strip() for kw in text.split(',') if kw.strip()]
            else:
                keywords = [kw.strip() for kw in text.split('\n') if kw.strip()]
                
            clean_keywords = []
            for kw in keywords:
                kw = kw.lstrip('- *1234567890.').strip()
                if kw: clean_keywords.append(kw)
            return clean_keywords[:5]
        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "RESOURCE_EXHAUSTED" in error_msg:
                # Find retry delay suggested by API if possible
                match = re.search(r'retryDelay[^0-9]*([0-9]+)s', error_msg)
                wait_time = int(match.group(1)) + 5 if match else 65
                print(f"   Rate limit hit. Waiting {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                print(f"   Gemini Error: {e}")
                break
    return None
    
def run_scraper(keyword_list):
    if not keyword_list:
        return True
        
    temp_kw_file = "temp_keywords.txt"
    with open(temp_kw_file, "w", encoding="utf-8") as f:
        for kw in keyword_list:
            f.write(kw + "\n")
            
    if os.name == 'nt':
        git_bash_path = r"C:\Program Files\Git\bin\bash.exe"
        cmd = [git_bash_path, "scraper.sh", temp_kw_file] if os.path.exists(git_bash_path) else ["bash", "scraper.sh", temp_kw_file]
    else:
        os.chmod("scraper.sh", 0o755)
        cmd = ["./scraper.sh", temp_kw_file]
        
    # Run the bash script process
    result = subprocess.run(cmd)
    
    if os.path.exists(temp_kw_file):
        os.remove(temp_kw_file)
        
    return result.returncode == 0

def main():
    print("=" * 60)
    print(" OrderMonk Scraper - Synchronizing with CSV Taxonomy")
    print("=" * 60)
    
    tracker = initialize_tracker_from_csv()
    if not tracker:
        print("Empty tracker. Check if CSV file is formatted properly.")
        return
        
    # Run ONLY unscraped categories mapping from the logic
    unscraped_categories = [cat for cat, info in tracker.items() if isinstance(info, dict) and info.get("status") == "unscraped"]
    print(f"Total categories: {len(tracker)} | Remaining Unscraped: {len(unscraped_categories)}")
    
    # Process up to 5 categories per run to respect time/API limits
    BATCH_SIZE = 5
    categories_to_process = unscraped_categories[:BATCH_SIZE]
    
    if not categories_to_process:
        print(" All categories from the CSV have been successfully scraped!")
        return

    for category_name in categories_to_process:
        print(f"\n Processing Category: '{category_name}'")
        
        # 1. Check if we already generated keywords from a previous failed run
        keywords = tracker[category_name].get("generated_keywords", [])
        if not keywords:
            keywords = generate_keywords(category_name)
            if not keywords:
                print("  Skipping")
                continue
            
            # Save generated keywords immediately in tracker
            tracker[category_name]["generated_keywords"] = keywords
            save_tracker(tracker)
            
        print(f"   Keywords to scrape: {keywords}")
        
        # 2. Save mapped keywords JSON file exactly as requested: Date Time and Category Name
        safe_name = re.sub(r'[^A-Za-z0-9]', '_', category_name)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        keywords_filename = f"{timestamp}_{safe_name}.json"
        
        keywords_filepath = os.path.join(KEYWORD_MAPPINGS_DIR, keywords_filename)
        keyword_data = {
            "category": category_name,
            "generated_keywords": keywords,
            "mapped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open(keywords_filepath, "w", encoding="utf-8") as f:
            json.dump(keyword_data, f, indent=4)
            
        print(f"   Mapped JSON saved successfully: {keywords_filepath}")
        
        # Track file path early
        tracker[category_name]["keywords_file"] = keywords_filepath
        save_tracker(tracker)
        
        # 3. Trigger Scraper
        print(f"   Running Scraper for {len(keywords)} keywords...")
        success = run_scraper(keywords)
        
        # 4. Update Tracker Status Based on Success
        if success:
            tracker[category_name]["status"] = "scraped"
            tracker[category_name]["scraped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_tracker(tracker)
            print(f"   '{category_name}' successfully marked as SCRAPED.")
        else:
            print(f"   Scraper failed for '{category_name}'. Status remains UNSCRAPED.")
            
        # Small delay to prevent hitting Gemini API rate limits immediately
        time.sleep(3)

    print("\n" + "=" * 60)
    print(" Daily Run Complete! Tracker updated.")
    print("=" * 60)

if __name__ == "__main__":
    main()
