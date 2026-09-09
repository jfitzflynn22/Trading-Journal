#!/bin/bash
#
# Double-click this from Finder to open the journal as a desktop app.
#
# It is a thin shim over bin/journal-launch.sh. The reason this exists
# alongside the .app bundle: macOS blocks an unsigned app bundle from running
# anything inside ~/Documents (TCC, the "Documents Folder" permission), and it
# does so silently. Run from Terminal, the same script inherits Terminal's own
# file access and just works. See README-launcher.md.
exec "$(cd "$(dirname "$0")" && pwd)/bin/journal-launch.sh"
