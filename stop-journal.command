#!/bin/bash
#
# Stop a stuck journal server. Double-click from Finder, or run it directly:
#
#     ./stop-journal.command
#
# The launcher normally stops the server when its window closes; this is for
# when that did not happen -- a crash, a force quit, or a server started by
# hand from a terminal.

set -u

PORT=8501
APP_ROOT="$(cd "$(dirname "$0")" && pwd)"
STATE_DIR="${HOME}/Library/Application Support/TradingJournal"
SERVER_PID_FILE="${STATE_DIR}/server.pid"
CHROME_PID_FILE="${STATE_DIR}/chrome.pid"

killed_any=""

kill_pid() {  # $1 = pid, $2 = label
    kill -0 "$1" >/dev/null 2>&1 || return 1
    echo "  stopping $2 (pid $1)"
    kill "$1" >/dev/null 2>&1
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        kill -0 "$1" >/dev/null 2>&1 || return 0
        sleep 0.2
    done
    kill -9 "$1" >/dev/null 2>&1
    return 0
}

echo "Trading Journal - stop"
echo

# 0. the background service, if it is installed. This has to go first and it
#    has to be launchctl: the agent is KeepAlive, so killing its process only
#    prompts launchd to start another one.
LABEL="local.tradingjournal.server"
if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    echo "  stopping background service (${LABEL})"
    launchctl bootout "gui/$(id -u)/${LABEL}" >/dev/null 2>&1
    killed_any="yes"
    echo "  (it will start again at next login - bin/uninstall-service.sh to prevent that)"
fi

# 1. the pid the launcher recorded
if [ -f "${SERVER_PID_FILE}" ]; then
    pid="$(cat "${SERVER_PID_FILE}" 2>/dev/null)"
    kill_pid "${pid}" "recorded server" && killed_any="yes"
    rm -f "${SERVER_PID_FILE}"
fi

# 2. anything else still serving this app -- covers servers started from a
#    terminal, which never wrote a pid file
for pid in $(pgrep -f "streamlit run.*app\.py" 2>/dev/null); do
    kill_pid "${pid}" "streamlit" && killed_any="yes"
done

# 3. whatever still holds the port, whoever started it
for pid in $(/usr/sbin/lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN -t 2>/dev/null); do
    kill_pid "${pid}" "listener on port ${PORT}" && killed_any="yes"
done

# The app window is useless once its server is gone.
if [ -f "${CHROME_PID_FILE}" ]; then
    pid="$(cat "${CHROME_PID_FILE}" 2>/dev/null)"
    kill_pid "${pid}" "app window" >/dev/null 2>&1
    rm -f "${CHROME_PID_FILE}"
fi

echo
if [ -n "${killed_any}" ]; then
    echo "Stopped. Port ${PORT} is free."
else
    echo "Nothing was running on port ${PORT}."
fi

# Leave the result on screen when double-clicked from Finder.
if [ -t 1 ]; then
    echo
    echo "(this window can be closed)"
fi
