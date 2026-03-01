import os
import re
import time
import shutil
import subprocess
from google import genai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure the Gemini API (new google.genai SDK)
api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
if not api_key:
    print("Error: GOOGLE_GEMINI_API_KEY not found in .env file.")
    exit(1)

client = genai.Client(api_key=api_key)

# ==============================
# 📁 Folder Structure
# ==============================
# keywords/
#   unscraped/   → keyword files waiting to be scraped
#   scraped/     → keyword files successfully scraped
# categories/
#   unscraped/   → category name files waiting to be scraped
#   scraped/     → category name files already scraped

KEYWORDS_UNSCRAPED  = "keywords/unscraped"
KEYWORDS_SCRAPED    = "keywords/scraped"
CATEGORIES_UNSCRAPED = "categories/unscraped"
CATEGORIES_SCRAPED   = "categories/scraped"

for folder in [KEYWORDS_UNSCRAPED, KEYWORDS_SCRAPED, CATEGORIES_UNSCRAPED, CATEGORIES_SCRAPED]:
    os.makedirs(folder, exist_ok=True)

# ==============================
# 1️⃣ Categories
# ==============================

categories = {
    "body_scrub": "Body scrub",
    "salt_scrub": "Salt scrub",
    "sugar_scrub": "Sugar scrub",
    "exfoliating_gloves": "Exfoliating gloves",
    "body_polish": "Body polish"
}

# ==============================
# 2️⃣ Keyword Generator (Gemini)
# ==============================

def generate_keywords(category_name):
    print(f"  Calling Gemini for '{category_name}'...")
    prompt = (
        f"You are an e-commerce SEO and PPC expert. "
        f"Generate exactly 5 highly relevant e-commerce search keywords for the product category: '{category_name}'. "
        f"Return ONLY a comma-separated list of the 5 keywords, with no numbers, bullet points, or extra text."
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            text = response.text.strip()

            # Parse comma-separated or newline-separated list
            if ',' in text:
                keywords = [kw.strip() for kw in text.split(',') if kw.strip()]
            else:
                keywords = [kw.strip() for kw in text.split('\n') if kw.strip()]

            # Clean up bullet points or stray numbers
            clean_keywords = []
            for kw in keywords:
                kw = kw.lstrip('- *1234567890.')
                kw = kw.strip()
                if kw:
                    clean_keywords.append(kw)

            return clean_keywords[:5]

        except Exception as e:
            error_msg = str(e)

            if "429" in error_msg or "quota" in error_msg.lower() or "rate" in error_msg.lower():
                match = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', error_msg)
                wait_time = int(match.group(1)) + 5 if match else 65
                print(f"  ⏳ Rate limit hit. Waiting {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
            else:
                print(f"  ❌ Gemini Error: {error_msg}")
                break

    print(f"  ❌ All retries failed for '{category_name}'.")
    return None

# ==============================
# 3️⃣ Save Keywords to unscraped/
# ==============================

def save_keywords_unscraped(category_key, keywords):
    file_path = os.path.join(KEYWORDS_UNSCRAPED, f"{category_key}.txt")
    with open(file_path, "w", newline='\n', encoding='utf-8') as f:
        for kw in keywords:
            f.write(kw + "\n")
    return file_path

# ==============================
# 4️⃣ Save Category to unscraped/
# ==============================

def save_category_unscraped(category_key, category_name):
    file_path = os.path.join(CATEGORIES_UNSCRAPED, f"{category_key}.txt")
    with open(file_path, "w", newline='\n', encoding='utf-8') as f:
        f.write(category_name + "\n")
    return file_path

# ==============================
# 5️⃣ Mark as Scraped (move files)
# ==============================

def mark_keywords_scraped(category_key):
    src = os.path.join(KEYWORDS_UNSCRAPED, f"{category_key}.txt")
    dst = os.path.join(KEYWORDS_SCRAPED, f"{category_key}.txt")
    if os.path.exists(src):
        shutil.move(src, dst)
        print(f"  📁 Keywords moved → keywords/scraped/{category_key}.txt")

def mark_category_scraped(category_key):
    src = os.path.join(CATEGORIES_UNSCRAPED, f"{category_key}.txt")
    dst = os.path.join(CATEGORIES_SCRAPED, f"{category_key}.txt")
    if os.path.exists(src):
        shutil.move(src, dst)
        print(f"  📁 Category moved → categories/scraped/{category_key}.txt")

# ==============================
# 6️⃣ Run Scraper (Git Bash)
# ==============================

def run_scraper(keyword_file):
    print(f"  🚀 Running scraper for: {keyword_file}")
    git_bash_path = r"C:\Program Files\Git\bin\bash.exe"
    if os.path.exists(git_bash_path):
        result = subprocess.run([git_bash_path, "scraper.sh", keyword_file])
    else:
        result = subprocess.run(["bash", "scraper.sh", keyword_file])
    return result.returncode == 0

# ==============================
# 7️⃣ MAIN
# ==============================

if __name__ == "__main__":

    category_items = list(categories.items())
    total = len(category_items)

    print("=" * 60)
    print(f"🤖 OrderMonk AI Keyword Generator — {total} categories")
    print("=" * 60)

    for idx, (key, value) in enumerate(category_items):
        print(f"\n[{idx + 1}/{total}] Category: {value}")

        # Skip if already scraped
        if os.path.exists(os.path.join(CATEGORIES_SCRAPED, f"{key}.txt")):
            print(f"  ⏭️  Already scraped. Skipping.")
            continue

        # Generate keywords from Gemini
        keywords = generate_keywords(value)
        if not keywords:
            print(f"  ⚠️  Could not generate keywords for '{value}'. Skipping.")
            continue

        print(f"  ✅ Keywords: {keywords}")

        # Save to unscraped folders
        kw_file = save_keywords_unscraped(key, keywords)
        save_category_unscraped(key, value)

        print(f"  💾 Saved to: {kw_file}")

        # Run scraper
        success = run_scraper(kw_file)

        if success:
            # Move both keyword file and category file to scraped/
            mark_keywords_scraped(key)
            mark_category_scraped(key)
        else:
            print(f"  ❌ Scraper failed for '{value}'. Files remain in unscraped/.")

        # Rate limit: wait between Gemini calls (skip after last)
        if idx < total - 1:
            print(f"\n  ⏳ Waiting 5 seconds before next category...")
            time.sleep(5)

    print("\n" + "=" * 60)
    print("📊 Done! Folder summary:")
    print(f"   ✅ Scraped keywords   : keywords/scraped/")
    print(f"   🕐 Unscraped keywords : keywords/unscraped/")
    print(f"   ✅ Scraped categories  : categories/scraped/")
    print(f"   🕐 Unscraped categories: categories/unscraped/")
    print("=" * 60)
