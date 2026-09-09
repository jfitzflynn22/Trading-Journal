#!/bin/bash
#
# Give the Safari web app our icon.
#
#     ./bin/set-webapp-icon.sh ["~/Applications/Some Name.app"]
#
# Safari's "Add to Dock" takes the icon from whatever favicon it had cached for
# the site at that moment, which is not reliably the one the page sets at
# runtime -- on this machine it picked up a stale icon from a different
# localhost app entirely. This attaches ours to the web app afterwards, the
# same way Finder's Get Info > paste icon does, leaving the bundle Safari
# signed untouched.
#
# Re-run it if you ever remove and re-add the web app.
set -eu

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:-${HOME}/Applications/Trading Journal.app}"
ICON="${APP_ROOT}/build/icon-preview.png"
TOOL="${APP_ROOT}/bin/set-icon"

if [ ! -f "${ICON}" ]; then
    echo "icon master missing; generating it"
    "${APP_ROOT}/.venv/bin/python" "${APP_ROOT}/bin/make-icon.py" >/dev/null
fi

if [ ! -x "${TOOL}" ]; then
    echo "building bin/set-icon"
    clang -framework Cocoa -o "${TOOL}" "${APP_ROOT}/bin/set-icon.m"
fi

if [ ! -d "${TARGET}" ]; then
    echo "no web app at: ${TARGET}" >&2
    echo "Create it first: open http://localhost:8501 in Safari, File > Add to Dock." >&2
    exit 1
fi

"${TOOL}" "${ICON}" "${TARGET}"

# Finder and the Dock cache icons; nudge both or the old one lingers.
touch "${TARGET}"
killall Dock >/dev/null 2>&1 || true

echo "Done. If the Dock still shows the old icon, drag the app out of the Dock and back in."
