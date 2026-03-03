"""
Email Alert Test
================
Run this file to send a real test alert email and verify the
ALERT_EMAIL / ALERT_EMAIL_PASS / ALERT_TO_EMAIL setup works.

Usage:
    cd e:\\ordermonk\\scraping\\automatic-scrap
    python tests/email_alert_test.py
"""

import os
import sys
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from dotenv import load_dotenv

# ── Load .env from the project root (one level up from tests/)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

ALERT_FROM_EMAIL = os.getenv("ALERT_EMAIL")
ALERT_EMAIL_PASS = os.getenv("ALERT_EMAIL_PASS")
_raw_to          = os.getenv("ALERT_TO_EMAIL", ALERT_FROM_EMAIL or "")
ALERT_TO_EMAILS  = [e.strip() for e in _raw_to.split(",") if e.strip()]

# ──────────────────────────────────────────────────────────────
def check_config():
    """Validate env vars before attempting to send."""
    errors = []
    if not ALERT_FROM_EMAIL:
        errors.append("❌ ALERT_EMAIL is not set in .env")
    if not ALERT_EMAIL_PASS:
        errors.append("❌ ALERT_EMAIL_PASS is not set in .env")
    if not ALERT_TO_EMAILS:
        errors.append("❌ ALERT_TO_EMAIL is not set in .env")

    if errors:
        print("\n".join(errors))
        print("\n💡 Open your .env file and fill in the email credentials.")
        sys.exit(1)

    print("✅ Config check passed:")
    print(f"   FROM : {ALERT_FROM_EMAIL}")
    print(f"   TO   : {', '.join(ALERT_TO_EMAILS)}")
    print()


def send_test_alert():
    """Send a test failure alert email."""
    subject = "🧪 [TEST] OrderMonk Alert System — Email Test"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    body = f"""\
<html><body style="font-family:Arial,sans-serif;color:#333;">
<h2 style="color:#cc7700;">🧪 This is a Test Alert</h2>
<p>If you received this email, your alert system is configured correctly! ✅</p>
<table cellpadding="8" style="border-collapse:collapse;width:100%;max-width:600px;">
  <tr style="background:#f5f5f5;"><td><b>Category</b></td><td>Test Category</td></tr>
  <tr><td><b>Reason</b></td><td>Manual test triggered from email_alert_test.py</td></tr>
  <tr style="background:#f5f5f5;"><td><b>Time</b></td><td>{timestamp}</td></tr>
  <tr><td><b>Details</b></td><td>This is a simulated failure to verify the alert pipeline.</td></tr>
  <tr style="background:#f5f5f5;"><td><b>Recipients</b></td><td>{", ".join(ALERT_TO_EMAILS)}</td></tr>
</table>
<p style="color:#666;font-size:12px;">— OrderMonk Auto-Scraper (Test Mode)</p>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = ALERT_FROM_EMAIL
    msg["To"]      = ", ".join(ALERT_TO_EMAILS)
    msg.attach(MIMEText(body, "html"))

    print(f"📤 Connecting to Gmail SMTP (smtp.gmail.com:465)...")
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(ALERT_FROM_EMAIL, ALERT_EMAIL_PASS)
            server.sendmail(ALERT_FROM_EMAIL, ALERT_TO_EMAILS, msg.as_string())

        print(f"✅ Test alert email sent successfully!")
        print(f"   → {', '.join(ALERT_TO_EMAILS)}")
        print("\n📬 Check your inbox (and spam folder) now.")

    except smtplib.SMTPAuthenticationError:
        print("❌ Authentication failed!")
        print("   → Make sure ALERT_EMAIL_PASS is a Gmail App Password,")
        print("     NOT your normal Gmail login password.")
        print("   → Generate one at: https://myaccount.google.com/apppasswords")
        sys.exit(1)

    except smtplib.SMTPException as e:
        print(f"❌ SMTP error: {e}")
        sys.exit(1)

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


# ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("🧪  OrderMonk — Email Alert System Test")
    print("=" * 55)
    check_config()
    send_test_alert()
    print("=" * 55)
