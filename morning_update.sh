#!/bin/bash
# morning_update.sh — fetch fresh GC stats and push data.json
# Runs every 10 min via launchd; marker prevents re-running once it succeeds today.

PYTHON=/Users/leviblack/.vit/venv/bin/python
GIT=/usr/bin/git
DIR=/Users/leviblack/grizzlies-stats
MARKER=$DIR/.last_update
LOG=$DIR/morning_update.log
TODAY=$(date +%F)

# ── Already ran successfully today → no-op ───────────────────────────────────
if [ -f "$MARKER" ] && [ "$(cat "$MARKER")" = "$TODAY" ]; then
    exit 0
fi

echo "$(date '+%Y-%m-%d %H:%M:%S')  starting" >> "$LOG"
cd "$DIR" || { echo "$(date '+%Y-%m-%d %H:%M:%S')  ERROR: cd failed" >> "$LOG"; exit 0; }

# ── Get fresh token (opens visible browser briefly) ──────────────────────────
TOKEN=$("$PYTHON" get_token.py 2>>"$LOG")
if [ -z "$TOKEN" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S')  no token (screen locked or session expired) — will retry" >> "$LOG"
    exit 0
fi
echo "$(date '+%Y-%m-%d %H:%M:%S')  token captured (${#TOKEN} chars)" >> "$LOG"

# ── Fetch stats ───────────────────────────────────────────────────────────────
GC_TOKEN="$TOKEN" "$PYTHON" run.py >> "$LOG" 2>&1
if [ $? -ne 0 ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S')  ERROR: run.py failed — will retry" >> "$LOG"
    exit 0
fi

# ── Push if data.json changed ─────────────────────────────────────────────────
if "$GIT" diff --quiet data.json; then
    echo "$(date '+%Y-%m-%d %H:%M:%S')  data.json unchanged — no push needed" >> "$LOG"
else
    "$GIT" add data.json
    "$GIT" commit -m "Stats update $TODAY" >> "$LOG" 2>&1
    "$GIT" push >> "$LOG" 2>&1
    if [ $? -ne 0 ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S')  ERROR: git push failed — will retry" >> "$LOG"
        exit 0
    fi
    echo "$(date '+%Y-%m-%d %H:%M:%S')  pushed data.json" >> "$LOG"
fi

# ── Write marker ONLY on full success ────────────────────────────────────────
echo "$TODAY" > "$MARKER"
echo "$(date '+%Y-%m-%d %H:%M:%S')  done" >> "$LOG"
