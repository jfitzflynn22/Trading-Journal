#!/bin/bash
#
# Stop the background server and remove it from login. The Safari web app icon
# will still be in the Dock afterwards, but clicking it will find nothing --
# run bin/install-service.sh again, or use start-journal.command.
set -u

LABEL="local.tradingjournal.server"
PLIST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

if launchctl print "gui/$(id -u)/${LABEL}" >/dev/null 2>&1; then
    launchctl bootout "gui/$(id -u)/${LABEL}" && echo "service stopped"
else
    echo "service was not loaded"
fi

if [ -f "${PLIST}" ]; then
    rm -f "${PLIST}"
    echo "removed ${PLIST}"
fi

sleep 1
if /usr/sbin/lsof -nP -iTCP:8501 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "note: something is still listening on 8501 - run stop-journal.command"
else
    echo "port 8501 is free"
fi
