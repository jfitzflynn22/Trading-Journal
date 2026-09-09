#!/bin/bash
#
# Desktop launcher for the trading journal. Shared by both entry points:
# start-journal.command (double-click from Finder) and the .app bundle.
#
# Starts the Streamlit server if it is not already up, waits for it to actually
# answer, and opens it in a chrome-less Chrome window that owns its own Dock
# tile. Closing that window stops the server -- this script blocks on Chrome
# and cleans up on the way out, so nothing is left listening on the port.
#
# Absolute paths throughout: launched from Finder this inherits a minimal PATH,
# so /usr/bin/curl is not necessarily the curl an interactive shell finds (here
# that one is Anaconda's), and the venv is never "activated" in the shell sense
# -- calling its binaries directly is the same thing without the ceremony.

set -u

PORT=8501
URL="http://127.0.0.1:${PORT}"
HEALTH="${URL}/_stcore/health"

# bin/journal-launch.sh -> the project directory. Derived, not hardcoded, so
# the folder can be moved or renamed without editing this file.
APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

VENV_PY="${APP_ROOT}/.venv/bin/python"
STREAMLIT="${APP_ROOT}/.venv/bin/streamlit"
ENTRY="${APP_ROOT}/app.py"

STATE_DIR="${HOME}/Library/Application Support/TradingJournal"
CHROME_PROFILE="${STATE_DIR}/chrome-profile"
SERVER_PID_FILE="${STATE_DIR}/server.pid"
CHROME_PID_FILE="${STATE_DIR}/chrome.pid"
LOG="${STATE_DIR}/server.log"
# Separate from the server's own output: launched from the .app there is no
# terminal, so this is the only record of why a launch went nowhere.
LAUNCH_LOG="${STATE_DIR}/launcher.log"

CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# First-run window geometry, 16:9. Chrome stores whatever you resize it to in
# the profile afterwards, so this only sets the shape of the first window.
# 1440x810 fits both a 1920x1080 display and a 1440x900 laptop screen.
WIN_W=1440
WIN_H=810
WIN_X=140
WIN_Y=90

mkdir -p "${STATE_DIR}"

note() {  # to the terminal if there is one, and always as a dialog: launched
          # from the .app there is nowhere to print
    echo "$1"
    /usr/bin/osascript -e "display dialog \"$1\" buttons {\"OK\"} default button 1 with title \"Trading Journal\"" >/dev/null 2>&1
}

say() {  # progress, only useful when run from a terminal
    [ -t 1 ] && echo "$1"
}

port_open() {
    /usr/bin/nc -z 127.0.0.1 "${PORT}" >/dev/null 2>&1
}

server_answers() {
    # Listening is not the same as ready: Streamlit accepts the connection
    # before it can serve. The health endpoint is the real signal.
    /usr/bin/curl -sf --max-time 2 "${HEALTH}" >/dev/null 2>&1
}

alive() {  # $1 = pid
    [ -n "${1:-}" ] && kill -0 "$1" >/dev/null 2>&1
}

read_pid() {  # $1 = pid file
    [ -f "$1" ] && cat "$1" 2>/dev/null
}

# --- 0. can we even read the project? ----------------------------------------
# Launched from the .app bundle this is the failure that actually happens: the
# project sits under ~/Documents, which macOS protects, and a locally built
# bundle is refused *silently* -- no prompt, no error the user would ever see.
# Streamlit would then fail to import app.py and the only symptom would be a
# server that never comes up. Checked up front so the dialog can say what to do.
if [ ! -r "${ENTRY}" ]; then
    echo "$(date '+%F %T')  cannot read ${ENTRY} - Full Disk Access not granted" >> "${LAUNCH_LOG}"
    ANSWER="$(/usr/bin/osascript \
        -e 'display dialog "Trading Journal cannot read its own folder.

macOS protects ~/Documents, and this launcher has not been granted access. Grant it once:

1. Privacy & Security > Full Disk Access
2. Press +
3. Choose Trading Journal.app in the trading-journal folder
4. Switch it on, then launch again

Or use start-journal.command, which needs no permission." buttons {"Open Settings", "Cancel"} default button 1 with title "Trading Journal" with icon caution' 2>>"${LAUNCH_LOG}")"
    echo "$(date '+%F %T')  dialog answer: ${ANSWER:-<none>}" >> "${LAUNCH_LOG}"
    case "${ANSWER}" in
        *"Open Settings"*) /usr/bin/open "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles" ;;
    esac
    exit 1
fi

# --- 0b. service mode -------------------------------------------------------
# Used by the LaunchAgent (see bin/install-service.sh): run the server in the
# foreground and nothing else -- no window, no cleanup trap, because launchd
# owns this process and restarts it if it exits. exec so the pid launchd
# watches is Streamlit's own.
if [ "${1:-}" = "--server-only" ]; then
    cd "${APP_ROOT}" || exit 1
    # fileWatcherType none: config.toml turns runOnSave on, which is right for a
    # server you start while editing and wrong for one that runs all day. It
    # costs a little idle CPU polling for changes (0.83% of a core against 0.63%
    # measured), and it would rerun the page under you mid-session if a file
    # changed. Restart the service to pick up code changes.
    exec "${STREAMLIT}" run "${ENTRY}" \
        --server.headless true \
        --server.port "${PORT}" \
        --server.fileWatcherType none
fi

# --- 1. already running? focus it rather than starting a second server -------
if port_open; then
    say "Already running on port ${PORT} - focusing the existing window."
    CHROME_PID="$(read_pid "${CHROME_PID_FILE}")"
    if alive "${CHROME_PID}"; then
        # Raise the existing app window by process id. Targeting the pid matters:
        # the dedicated profile runs its own Chrome instance, so telling
        # "Google Chrome" would address whichever instance AppleScript picks.
        /usr/bin/osascript -e "tell application \"System Events\" to set frontmost of (first process whose unix id is ${CHROME_PID}) to true" >/dev/null 2>&1
        exit 0
    fi
    # Server is up but its window is gone (window closed without the launcher
    # running, or a dev server started from a terminal). Give it a window back.
    if [ -x "${CHROME}" ]; then
        "${CHROME}" --app="${URL}" --user-data-dir="${CHROME_PROFILE}" \
            --window-size="${WIN_W},${WIN_H}" --window-position="${WIN_X},${WIN_Y}" \
            --no-first-run --no-default-browser-check >/dev/null 2>&1 &
        echo $! > "${CHROME_PID_FILE}"
        wait $!
    else
        /usr/bin/open "${URL}"
    fi
    exit 0
fi

# --- 2. start the server -----------------------------------------------------
if [ ! -x "${STREAMLIT}" ]; then
    note "The virtual environment is missing.\n\nExpected: ${STREAMLIT}\n\nCreate it with:  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

cd "${APP_ROOT}" || exit 1
: > "${LOG}"
say "Starting the server..."
# --server.headless true: no auto-opened browser tab, since the window below is
# the point. The port is pinned so the health check and the stop script agree.
"${STREAMLIT}" run "${ENTRY}" \
    --server.headless true \
    --server.port "${PORT}" \
    >>"${LOG}" 2>&1 &
SERVER_PID=$!
echo "${SERVER_PID}" > "${SERVER_PID_FILE}"

# --- 5. stop the server on the way out, however we leave ---------------------
cleanup() {
    SP="$(read_pid "${SERVER_PID_FILE}")"
    if alive "${SP}"; then
        kill "${SP}" >/dev/null 2>&1
        # Give it a moment to close the port, then insist.
        for _ in 1 2 3 4 5 6 7 8 9 10; do
            alive "${SP}" || break
            sleep 0.2
        done
        alive "${SP}" && kill -9 "${SP}" >/dev/null 2>&1
    fi
    rm -f "${SERVER_PID_FILE}" "${CHROME_PID_FILE}"
}
trap cleanup EXIT INT TERM

# --- 3. wait for it to actually answer, rather than sleeping and hoping ------
READY=""
for _ in $(seq 1 150); do          # 150 x 0.2s = 30s ceiling
    if ! alive "${SERVER_PID}"; then break; fi
    if port_open && server_answers; then READY="yes"; break; fi
    sleep 0.2
done

if [ -z "${READY}" ]; then
    note "The server did not come up within 30 seconds.\n\nLast lines of the log:\n\n$(tail -n 12 "${LOG}" 2>/dev/null | sed 's/"/\\"/g')"
    exit 1
fi

# --- 4. open it in its own window -------------------------------------------
if [ -x "${CHROME}" ]; then
    # --app= drops the tab strip, omnibox and the rest; --user-data-dir gives
    # this window its own Chrome instance, so it has a separate Dock tile and
    # shares no cookies, history or session with normal browsing.
    say "Ready. Opening the window - close it to stop the server."
    "${CHROME}" --app="${URL}" --user-data-dir="${CHROME_PROFILE}" \
        --window-size="${WIN_W},${WIN_H}" --window-position="${WIN_X},${WIN_Y}" \
        --no-first-run --no-default-browser-check >/dev/null 2>&1 &
    CHROME_PID=$!
    echo "${CHROME_PID}" > "${CHROME_PID_FILE}"
    # Blocking here is what ties the two together: Chrome exits when its last
    # window in this profile closes, and the EXIT trap then stops the server.
    wait "${CHROME_PID}"
    say "Window closed - stopping the server."
else
    note "Google Chrome was not found, so the journal has been opened in your default browser instead. It will have normal browser chrome (tabs and address bar), and closing the tab will NOT stop the server -- run stop-journal.command when you are done."
    /usr/bin/open "${URL}"
    # Nothing to wait on, so leave the server up rather than killing the page
    # the user was just sent to.
    trap - EXIT INT TERM
fi

exit 0
