import os
import json
import time
import shutil
import subprocess
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv
import csv

load_dotenv()

# ─────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────
BASE_INPUT_DIR      = "input_keywords"          # Root keyword folder
PENDING_DIR         = os.path.join(BASE_INPUT_DIR, "pending")    # 🔵 Not yet scraped
SCRAPED_DIR         = os.path.join(BASE_INPUT_DIR, "scraped")    # ✅ Successfully scraped
FAILED_DIR          = os.path.join(BASE_INPUT_DIR, "failed")     # ❌ Scrape failed (retry later)

KEYWORD_MAPPINGS_DIR = "keyword_mappings"       # JSON snapshots per category
AUDIT_LOG_FILE       = "audit_log.json"         # Rich audit trail (optional, lightweight)

BATCH_SIZE = 5                                  # Max files to process per run

# ─────────────────────────────────────────────────────────────
#  EMAIL ALERT CONFIGURATION  (loaded from .env / GitHub Secrets)
# ─────────────────────────────────────────────────────────────
ALERT_FROM_EMAIL = os.getenv("ALERT_EMAIL")          # Gmail address that sends alerts
ALERT_EMAIL_PASS = os.getenv("ALERT_EMAIL_PASS")     # Gmail App Password (NOT your login password)
# Comma-separated list of recipients, e.g. "a@gmail.com,b@gmail.com"
_raw_to           = os.getenv("ALERT_TO_EMAIL", ALERT_FROM_EMAIL or "")
ALERT_TO_EMAILS  = [e.strip() for e in _raw_to.split(",") if e.strip()]

# ─────────────────────────────────────────────────────────────
#  BOOTSTRAP DIRECTORIES
# ─────────────────────────────────────────────────────────────
for d in [PENDING_DIR, SCRAPED_DIR, FAILED_DIR, KEYWORD_MAPPINGS_DIR]:  # type: ignore
    os.makedirs(d, exist_ok=True)


# ─────────────────────────────────────────────────────────────
#  EMAIL ALERT SENDER
# ─────────────────────────────────────────────────────────────
def send_alert_email(category_name: str, reason: str, details: str = ""):
    """
    Send a failure alert email via Gmail SMTP.
    Silently skips if email credentials are not configured.
    """
    if not ALERT_FROM_EMAIL or not ALERT_EMAIL_PASS or not ALERT_TO_EMAILS:
        print("  ⚠️  Email alert skipped (ALERT_EMAIL / ALERT_EMAIL_PASS / ALERT_TO_EMAIL not set).")
        return

    subject = f"❌ OrderMonk Scraper FAILED — {category_name}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    body = f"""\
<html><body style="font-family:Arial,sans-serif;color:#333;">
<h2 style="color:#cc0000;">❌ Scraping Failure Alert</h2>
<table cellpadding="8" style="border-collapse:collapse;width:100%;max-width:600px;">
  <tr style="background:#f5f5f5;"><td><b>Category</b></td><td>{category_name}</td></tr>
  <tr><td><b>Reason</b></td><td>{reason}</td></tr>
  <tr style="background:#f5f5f5;"><td><b>Time</b></td><td>{timestamp}</td></tr>
  <tr><td><b>Details</b></td><td>{details if details else 'N/A'}</td></tr>
  <tr style="background:#f5f5f5;"><td><b>Retry</b></td><td>Move the .txt file from <code>failed/</code> back to <code>pending/</code> and push to GitHub.</td></tr>
</table>
<p style="color:#666;font-size:12px;">— OrderMonk Auto-Scraper</p>
</body></html>"""

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = ALERT_FROM_EMAIL
        msg["To"]      = ", ".join(ALERT_TO_EMAILS)   # shows all recipients in To: header
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(ALERT_FROM_EMAIL, ALERT_EMAIL_PASS)
            server.sendmail(ALERT_FROM_EMAIL, ALERT_TO_EMAILS, msg.as_string())  # list → sends to all

        print(f"  📧 Alert email sent to: {', '.join(ALERT_TO_EMAILS)}")
    except Exception as e:
        print(f"  ⚠️  Could not send alert email: {e}")


# ─────────────────────────────────────────────────────────────
#  GEMINI KEYWORD GENERATOR
# ─────────────────────────────────────────────────────────────
def generate_keywords_with_gemini(category_name: str) -> list:
    """Uses Gemini API to generate exactly 4 search keywords for a category."""
    try:
        from google import genai
        
        api_key = os.getenv("GOOGLE_GEMINI_API_KEY")
        if not api_key:
            print("      ⚠️  GOOGLE_GEMINI_API_KEY not found in environment.")
            return []
            
        client = genai.Client(api_key=api_key)
        prompt = (f"Generate a comprehensive list of at least 120 highly relevant and diverse search keywords/phrases to find "
                  f"'{category_name}' products on Amazon. Include variations, sub-categories, specific brands, "
                  f"use cases, features, and long-tail keywords.\n"
                  f"Return ONLY the keywords, one per line.\n"
                  f"No numbers, no bullet points, no asterisks, no extra text.")
                  
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        # Clean lines
        lines = [line.strip().lstrip("*-1234567890. ") for line in response.text.split('\n')]
        keywords = [line for line in lines if line]
        return keywords
        
    except Exception as e:
        print(f"      ⚠️  Gemini Error: {e}")
        return []


# ─────────────────────────────────────────────────────────────
#  AUDIT LOG  (replaces tracker.json for status tracking)
#  Stores only SUCCESS/FAILURE records for history — not used
#  for loop decisions (filesystem folders do that job now).
# ─────────────────────────────────────────────────────────────
def load_audit_log() -> dict:
    if os.path.exists(AUDIT_LOG_FILE):
        with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_audit_log(data: dict):
    with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


# ─────────────────────────────────────────────────────────────
#  SCRAPER RUNNER
# ─────────────────────────────────────────────────────────────
def run_scraper(keyword_file_path: str) -> bool:
    """Invoke scraper.sh with the given keyword file. Returns True on success."""
    print(f"  🚀 Running scraper for: {keyword_file_path}")
    if os.name == "nt":
        git_bash_path = r"C:\Program Files\Git\bin\bash.exe"
        if os.path.exists(git_bash_path):
            cmd = [git_bash_path, "scraper.sh", keyword_file_path]
        else:
            cmd = ["bash", "scraper.sh", keyword_file_path]
    else:
        os.chmod("scraper.sh", 0o755)
        cmd = ["./scraper.sh", keyword_file_path]

    result = subprocess.run(cmd)
    return result.returncode == 0


# ─────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────
def move_file(src: str, dest_dir: str) -> str:
    """Move src file into dest_dir. Returns the new path."""
    dest_path = os.path.join(dest_dir, os.path.basename(src))
    # If a file with the same name already exists in dest, add timestamp suffix
    if os.path.exists(dest_path):
        name, ext = os.path.splitext(os.path.basename(src))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_path = os.path.join(dest_dir, f"{name}__{timestamp}{ext}")
    shutil.move(src, dest_path)
    return dest_path


def save_keyword_mapping(category_name: str, keywords: list) -> str:
    """Persist a JSON snapshot of keywords for this category. Returns filepath."""
    safe_name = re.sub(r"[^A-Za-z0-9]", "_", category_name)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    filename = f"{timestamp}_{safe_name}.json"
    filepath = os.path.join(KEYWORD_MAPPINGS_DIR, filename)
    data = {
        "category": category_name,
        "keywords_count": len(keywords),
        "mapped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "keywords": keywords,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    return filepath


def print_summary(audit: dict):
    """Print a quick stats block at the end of every run."""
    total_scraped = sum(1 for v in audit.values() if v.get("status") == "scraped")
    total_failed  = sum(1 for v in audit.values() if v.get("status") == "failed")
    pending_count = len(os.listdir(PENDING_DIR))
    scraped_count = len(os.listdir(SCRAPED_DIR))
    failed_count  = len(os.listdir(FAILED_DIR))

    print("\n" + "=" * 60)
    print("📊  Run Summary")
    print("=" * 60)
    print(f"  📁 pending/  → {pending_count} file(s) remaining")
    print(f"  ✅ scraped/  → {scraped_count} file(s) done")
    print(f"  ❌ failed/   → {failed_count} file(s) to retry")
    print(f"  📜 Audit log → {total_scraped} scraped | {total_failed} failed (all-time)")
    print("=" * 60)


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────
def main():
    print("=" * 60)
    print("🤖  OrderMonk Scraper — Folder-Based Workflow")
    print("=" * 60)

    # ── Migrate legacy files: if any .txt files sit directly in
    #    input_keywords/ (old layout) move them to pending/ first
    legacy_files = [
        f for f in os.listdir(BASE_INPUT_DIR)
        if f.endswith(".txt") and os.path.isfile(os.path.join(BASE_INPUT_DIR, f))
    ]
    if legacy_files:
        print(f"\n⚙️  Migrating {len(legacy_files)} legacy file(s) → pending/")
        for lf in legacy_files:
            shutil.move(os.path.join(BASE_INPUT_DIR, lf), os.path.join(PENDING_DIR, lf))
            print(f"   ↳ {lf}")

    # ── 1. Discover existing PENDING files
    pending_files = sorted(f for f in os.listdir(PENDING_DIR) if f.endswith(".txt"))

    # ── 2. Auto-Generate missing pending files if under BATCH_SIZE
    audit = load_audit_log()
    if len(pending_files) < BATCH_SIZE:
        csv_path = "ultra_deep_marketplace_taxonomy_1000_plus.csv"
        target_new = BATCH_SIZE - len(pending_files)
        
        if os.path.exists(csv_path):
            print(f"\n✨ Currently {len(pending_files)} pending file(s). Auto-generating {target_new} more using Gemini...")
            generated_count = 0
            try:
                with open(csv_path, "r", encoding="utf-8") as csvfile:
                    reader = csv.reader(csvfile)
                    next(reader, None)  # skip header
                    for row in reader:
                        if len(row) >= 4:
                            cat = row[3].strip()
                            # skip if already scraped in audit log
                            if cat in audit and audit[cat].get("status") == "scraped":
                                continue
                            
                            # skip if a file already exists in any subfolder
                            if (os.path.exists(os.path.join(PENDING_DIR, f"{cat}.txt")) or 
                                os.path.exists(os.path.join(SCRAPED_DIR, f"{cat}.txt")) or 
                                os.path.exists(os.path.join(FAILED_DIR, f"{cat}.txt"))):
                                continue
                                
                            # Safe to generate!
                            print(f"  🧠 Generating keywords for '{cat}'...")
                            keywords = generate_keywords_with_gemini(cat)
                            
                            if keywords:
                                target_path = os.path.join(PENDING_DIR, f"{cat}.txt")
                                with open(target_path, "w", encoding="utf-8") as f:
                                    f.write("\n".join(keywords) + "\n")
                                print(f"      ↳ Saved {len(keywords)} keywords to pending/")
                                generated_count += 1
                                
                                if generated_count >= target_new:
                                    break
                                time.sleep(1) # Safety delay
                            else:
                                print(f"      ↳ Failed to generate keywords, skipping.")
                                
            except Exception as e:
                print(f"  ⚠️  Error reading taxonomy CSV or generating: {e}")
                
            # Re-fetch pending files list after generation:
            pending_files = sorted(f for f in os.listdir(PENDING_DIR) if f.endswith(".txt"))
        else:
            print(f"\n⚠️  Taxonomy CSV '{csv_path}' not found. Cannot auto-generate.")

    # ── 3. Check what we have now to process
    if not pending_files:
        print(f"\n✅ No pending keyword files and no un-scraped categories left in CSV.")
        print_summary(audit)
        return

    print(f"\n📋 Found {len(pending_files)} pending file(s). Processing up to {BATCH_SIZE} this run.\n")

    processed_count = 0

    for file_name in pending_files:
        if processed_count >= BATCH_SIZE:
            print(f"\n⏸️  Batch limit ({BATCH_SIZE}) reached. Remaining files stay in pending/ for next run.")
            break

        category_name = file_name.replace(".txt", "").strip()
        src_path = os.path.join(PENDING_DIR, file_name)

        print(f"─" * 60)
        print(f"📂 [{processed_count + 1}/{min(BATCH_SIZE, len(pending_files))}] Processing: '{category_name}'")

        # Read keywords
        with open(src_path, "r", encoding="utf-8") as f:
            keywords = [line.strip() for line in f if line.strip()]

        if not keywords:
            reason = "File is empty — no keywords to scrape"
            print(f"  ⚠️  {reason}. Moving to failed/")
            new_path = move_file(src_path, FAILED_DIR)
            audit[category_name] = {
                "status": "failed",
                "reason": "empty file",
                "failed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "file": new_path,
            }
            save_audit_log(audit)
            send_alert_email(category_name, reason, f"File moved to: {new_path}")
            processed_count += 1
            continue

        print(f"  📝 {len(keywords)} keyword(s) found.")

        # ── Run the scraper
        success = run_scraper(src_path)

        if success:
            # 1. Save keyword mapping JSON
            mapping_path = save_keyword_mapping(category_name, keywords)

            # 2. Move .txt → scraped/  (this is how we know it's done — no JSON lookup needed)
            new_path = move_file(src_path, SCRAPED_DIR)

            # 3. Update audit log
            audit[category_name] = {
                "status": "scraped",
                "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "keywords_count": len(keywords),
                "keywords_file": mapping_path,
                "scraped_txt": new_path,
            }
            save_audit_log(audit)
            print(f"  ✅ Done! Moved → scraped/{os.path.basename(new_path)}")
        else:
            # Move .txt → failed/ so operators can inspect and retry
            new_path = move_file(src_path, FAILED_DIR)
            audit[category_name] = {
                "status": "failed",
                "failed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "keywords_count": len(keywords),
                "failed_txt": new_path,
            }
            save_audit_log(audit)
            print(f"  ❌ Scraper failed! Moved → failed/{os.path.basename(new_path)}")
            send_alert_email(
                category_name,
                reason="scraper.sh returned non-zero exit code",
                details=f"Keywords: {len(keywords)} | File moved to: {new_path}",
            )

        processed_count += 1
        time.sleep(3)

    print_summary(audit)


if __name__ == "__main__":
    main()
