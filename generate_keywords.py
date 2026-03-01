import os
import time
import subprocess
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure the Gemini API
api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
if not api_key:
    print("Error: GOOGLE_GEMINI_API_KEY not found in .env file.")
    exit(1)

genai.configure(api_key=api_key)

# Initialize the model (gemini-1.5-flash = 15 RPM free tier, much more generous)
model = genai.GenerativeModel('gemini-1.5-flash')

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
    print(f"Calling Gemini for {category_name}...")
    prompt = (
        f"You are an e-commerce SEO and PPC expert. "
        f"Generate exactly 5 highly relevant e-commerce search keywords for the product category: '{category_name}'. "
        f"Return ONLY a comma-separated list of the 5 keywords, with no numbers, bullet points, or extra text."
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            text = response.text.strip()

            # Parse the comma-separated or newline-separated list
            if ',' in text:
                keywords = [kw.strip() for kw in text.split(',') if kw.strip()]
            else:
                keywords = [kw.strip() for kw in text.split('\n') if kw.strip()]

            # Clean up any potential bullet points or numbers
            clean_keywords = []
            for kw in keywords:
                kw = kw.lstrip('- *1234567890.')
                kw = kw.strip()
                if kw:
                    clean_keywords.append(kw)

            return clean_keywords[:5]

        except Exception as e:
            error_msg = str(e)

            # Check for free-tier rate limits (429 Too Many Requests)
            if "429" in error_msg or "quota" in error_msg.lower():
                # Try to extract retry_delay from the error message
                import re
                match = re.search(r'retry_delay\s*\{\s*seconds:\s*(\d+)', error_msg)
                wait_time = int(match.group(1)) + 5 if match else 65

                print(f"\n⏳ Gemini rate limit hit. Waiting {wait_time}s before retry (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait_time)
            else:
                print(f"❌ Gemini Error: {error_msg}")
                break

    print(f"❌ All retries failed for '{category_name}'. Skipping.")
    exit(1)

# ==============================
# 3️⃣ Save Keywords
# ==============================

def save_keywords(category_key, keywords):
    os.makedirs("keywords", exist_ok=True)
    file_path = f"keywords/{category_key}.txt"

    with open(file_path, "w", newline='\n', encoding='utf-8') as f:
        for kw in keywords:
            f.write(kw + "\n")

    return file_path


# ==============================
# 4️⃣ Run Scraper (Windows Native)
# ==============================

def run_scraper(keyword_file):
    print(f"Running scraper for {keyword_file}")
    
    # Run the bash script using Git Bash to avoid WSL issues on Windows
    git_bash_path = r"C:\Program Files\Git\bin\bash.exe"
    if os.path.exists(git_bash_path):
        subprocess.run([git_bash_path, "scraper.sh", keyword_file])
    else:
        # Fallback if Git Bash isn't in default location
        subprocess.run(["bash", "scraper.sh", keyword_file])



# ==============================
# 5️⃣ MAIN
# ==============================

if __name__ == "__main__":

    category_items = list(categories.items())

    for idx, (key, value) in enumerate(category_items):
        print(f"\nGenerating keywords for: {value}")

        keywords = generate_keywords(value)

        print(f"Total keywords generated: {len(keywords)}")
        print(f"Keywords: {keywords}")

        file_path = save_keywords(key, keywords)

        print(f"Saved to: {file_path}")

        # Run scraper
        run_scraper(file_path)

        # Rate limit safety: gemini-1.5-flash free tier = 15 requests/minute
        # Wait 5 seconds between calls as a safety buffer
        if idx < len(category_items) - 1:
            print(f"\n⏳ Waiting 5 seconds before next category...")
            time.sleep(5)

    print("\nAll categories processed successfully ✅")
