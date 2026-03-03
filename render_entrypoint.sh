#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# OrderMonk — Render Cron Job Entrypoint
#
# Required environment variables (set in Render dashboard):
#   GOOGLE_GEMINI_API_KEY  — Gemini API key
#   OXYLABS_USER           — Oxylabs username
#   OXYLABS_PASS           — Oxylabs password
#   GIT_TOKEN              — GitHub Personal Access Token (repo scope)
#   GIT_EMAIL              — Git commit email
#   GIT_NAME               — Git commit author name
#   GIT_REPO               — GitHub repo slug, e.g. "youruser/yourrepo"
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

echo "=============================="
echo "🤖 OrderMonk Render — Start"
echo "   $(date '+%Y-%m-%d %H:%M:%S UTC')"
echo "=============================="

# ── Make scripts executable
chmod +x scraper.sh

# ── Install Python dependencies
echo ""
echo "📦 Installing dependencies..."
pip install -r requirements.txt --quiet

# ── Run the folder-based scraper
echo ""
echo "🚀 Running scraper..."
python main.py

# ── Push results (scraped/ + failed/ moves + audit_log) back to GitHub
echo ""
echo "=============================="
echo "📤 Pushing results to GitHub..."
echo "=============================="

git config user.email "${GIT_EMAIL}"
git config user.name "${GIT_NAME}"

# Stage changes: moved files in scraped/, failed/, and the audit log
git add input_keywords/scraped/ input_keywords/failed/ audit_log.json 2>/dev/null || true

# Only commit if there are actual changes
if git diff --cached --quiet; then
    echo "ℹ️  No changes to commit (no files were moved this run)."
else
    git commit -m "🤖 Auto-scrape: $(date '+%Y-%m-%d %H:%M') UTC"
    git remote set-url origin "https://${GIT_TOKEN}@github.com/${GIT_REPO}.git"
    git push origin HEAD
    echo "✅ Results pushed to GitHub."
fi

echo ""
echo "=============================="
echo "✅ Render run complete."
echo "=============================="
