#!/bin/bash
#
# Install the journal server as a background LaunchAgent.
#
# Why this exists: a Safari "Add to Dock" web app is only a window -- it opens a
# URL and cannot start anything. So the server has to be up before the icon is
# clicked. launchd starts it at login and restarts it if it ever dies, which is
# what makes the web app feel like a native app: click, window, instant.
#
#   ./bin/install-service.sh      install and start
#   ./bin/uninstall-service.sh    stop and remove
#
# It costs one idle Python process. stop-journal.command stops it properly
# (a plain kill would just be undone by launchd).
set -eu

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="local.tradingjournal.server"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"
STATE_DIR="${HOME}/Library/Application Support/TradingJournal"
PORT=8501

# The service runs through the app bundle's binary, not straight at streamlit.
# launchd has no file access under ~/Documents; that binary carries the app's
# code signature and therefore the Full Disk Access you granted it, so this is
# what lets the background server read the project at all.
LAUNCHER_BIN="${APP_ROOT}/Trading Journal.app/Contents/MacOS/TradingJournal"
if [ ! -x "${LAUNCHER_BIN}" ]; then
    echo "error: ${LAUNCHER_BIN} not found - run ./bin/build-launcher.sh first" >&2
    exit 1
fi

mkdir -p "${HOME}/Library/LaunchAgents" "${STATE_DIR}"

cat > "${PLIST}" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${LAUNCHER_BIN}</string>
        <string>--server-only</string>
    </array>
    <key>WorkingDirectory</key>
    <string>${APP_ROOT}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${STATE_DIR}/service.log</string>
    <key>StandardErrorPath</key>
    <string>${STATE_DIR}/service.log</string>
</dict>
</plist>
PLISTEOF

# bootout first so a re-run reloads cleanly rather than erroring on a duplicate.
launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "${PLIST}"

printf 'waiting for the server'
for _ in $(seq 1 60); do
    if /usr/bin/curl -sf --max-time 2 "http://127.0.0.1:${PORT}/_stcore/health" >/dev/null 2>&1; then
        echo
        echo "Server is up on http://localhost:${PORT} and will start at login."
        echo
        echo "Next: open that URL in Safari, then File > Add to Dock."
        exit 0
    fi
    printf '.'
    sleep 0.5
done

echo
echo "The server did not answer within 30s. Log:"
tail -n 15 "${STATE_DIR}/service.log" 2>/dev/null
exit 1
