#!/bin/bash
#
# Rebuild the .app's main executable and re-sign the bundle.
#
# Run this after editing bin/launcher.c. Note that re-signing changes the
# bundle's code hash, which is the identity Full Disk Access is granted to --
# so after a rebuild the app must be removed from that list and re-added.
set -eu

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUNDLE="${APP_ROOT}/Trading Journal.app"
EXE="${BUNDLE}/Contents/MacOS/TradingJournal"

# The compiled binary is not committed, so its directory may not exist yet.
mkdir -p "${BUNDLE}/Contents/MacOS" "${BUNDLE}/Contents/Resources"

echo "compiling launcher.c ..."
clang -O2 -Wall -o "${EXE}" "${APP_ROOT}/bin/launcher.c"
chmod +x "${EXE}"

echo "signing bundle ..."
codesign --force --deep -s - "${BUNDLE}"

echo
file "${EXE}"
codesign -dv "${BUNDLE}" 2>&1 | grep -E "Identifier|CDHash=|Signature"
echo
echo "Done. If the app was already in Full Disk Access, remove and re-add it:"
echo "  System Settings > Privacy & Security > Full Disk Access"
