import os
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

# Initialize the model
model = genai.GenerativeModel('gemini-2.5-flash')

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
        print(f"❌ Gemini Error: {e}")
        return [category_name.lower()] * 5 # Fallback to category name if it fails

# ==============================
# 3️⃣ Save Keywords
# ==============================

def save_keywords(category_key, keywords):
    os.makedirs("keywords", exist_ok=True)
    file_path = f"keywords/{category_key}.txt"

    with open(file_path, "w") as f:
        for kw in keywords:
            f.write(kw + "\n")

    return file_path


# ==============================
# 4️⃣ Run Scraper (Windows Native)
# ==============================

def run_scraper(keyword_file):
    print(f"Running scraper for {keyword_file}")
    
    # Read the keywords from the file
    with open(keyword_file, "r") as f:
        keywords = f.read().splitlines()
        
    for kw in keywords:
        # Run python scrape.py "YOUR KEYWORD" directly in Windows
        subprocess.run(["python", "scrape.py", kw])


# ==============================
# 5️⃣ MAIN
# ==============================

if __name__ == "__main__":

    for key, value in categories.items():
        print(f"\nGenerating keywords for: {value}")

        keywords = generate_keywords(value)

        print(f"Total keywords generated: {len(keywords)}")
        print(f"Keywords: {keywords}")

        file_path = save_keywords(key, keywords)

        print(f"Saved to: {file_path}")

        # Run scraper
        run_scraper(file_path)

    print("\nAll categories processed successfully ✅")
