# Running the journal as a desktop app

## The Safari web app (recommended)

A Safari web app is a real application: its own icon in the Dock **and in the
Cmd-Tab switcher**, its own window, no browser chrome. That last part is why it
beats the Chrome launcher below, where the window belongs to Chrome and Cmd-Tab
shows Chrome's icon.

Safari can only open a URL, though — it cannot start the server. So the server
runs as a background service, installed once:

```bash
./bin/install-service.sh
```

That starts it now and at every login, and restarts it if it ever dies. Then:

1. Open **http://localhost:8501** in Safari.
2. **File → Add to Dock**, name it *Trading Journal*, click Add.
3. Give it the right icon:

```bash
./bin/set-webapp-icon.sh
```

Safari takes a web app's icon from whatever favicon it had cached for the site
at that moment — which is not reliably the one the page sets at runtime. Here it
picked up a stale icon from a different localhost app. That script attaches ours
afterwards, the same way Finder's *Get Info → paste icon* does, leaving the
bundle Safari signed untouched. Re-run it if you ever remove and re-add the web
app.

From then on: click the Dock icon, the window opens instantly against the
already-running server; close it and the window goes away. The server stays up
in the background, which is what makes the next open instant. It is one idle
Python process.

**To stop the server:** `stop-journal.command` (stops it until next login) or
`./bin/uninstall-service.sh` (stops it and removes it from login).

## Alternative: the Chrome launcher

`Trading Journal.app` opens the journal in a Chrome window and stops the
server when you close it. Its drawback is the one that led to the Safari route
above: the window belongs to Chrome, so Cmd-Tab shows Chrome's icon, not this
app's. It needs one permission before it will run — a consequence of where the project lives, not
of how the launcher is built (see "Why the permission" below).

1. Double-click `Trading Journal.app`. It will tell you it cannot read its
   folder and offer **Open Settings**.
2. In **Privacy & Security → Full Disk Access**, press **+**, choose
   `Trading Journal.app` from the `trading-journal` folder, and switch it on.
3. Launch it again. From then on it is a normal Dock app: click, window opens,
   close the window, server stops. No Terminal at any point.

Drag the app to the left-hand side of the Dock to keep it there.

## The no-permission alternative

**Double-click `start-journal.command`.** Identical behaviour, no permission
needed, but a Terminal window stays open alongside the app window. To keep this
one in the Dock, drag it to the right-hand side (next to the Trash), where
Finder keeps documents.

It will:

1. Check port 8501. If the app is already running, focus the existing window and
   exit — it never starts a second server.
2. Otherwise start Streamlit from `.venv` with `--server.headless true`, so no
   browser tab is opened behind your back.
3. Poll `http://127.0.0.1:8501/_stcore/health` until the server actually answers
   (up to 30s), rather than sleeping a fixed amount and hoping.
4. Open the app in a Chrome window with `--app=`, so there is no tab strip and
   no address bar, using a dedicated profile at
   `~/Library/Application Support/TradingJournal/chrome-profile`. That gives the
   window its own Dock tile and keeps cookies and history away from your normal
   browsing. Without Chrome it falls back to your default browser and says so.
5. Stop the server when you close the window. Nothing is left on the port.

The window opens at 1440 × 810 (16:9) the first time. Resize it however you
like — Chrome remembers the size and position in the dedicated profile, so it
comes back the same way next launch.

Launched from `start-journal.command`, a Terminal window opens alongside and
prints progress; it closes when you close the app window. Launched from the
`.app`, there is no Terminal at all.

## If the server gets stuck

**Double-click `stop-journal.command`**, or run it:

```bash
./stop-journal.command
```

It kills the recorded server pid, any other `streamlit run` for this app, and
whatever else holds port 8501 — so it also cleans up a server you started by
hand from a terminal. It then closes the app window, which is useless without
its server.

## Why the permission

This project lives under `~/Documents`, which macOS protects (TCC). An app
bundle gets to *run* when you double-click it, but every read and exec it then
attempts inside that folder is refused, and for a locally built bundle it is
refused **silently** -- no prompt offering to grant it. Probed from inside a
bundle:

```
read app.py:      DENIED
list dir:         DENIED
read journal.db:  DENIED
```

So Streamlit could never load `app.py`, let alone the database.

**The trap, if you ever rebuild this:** granting Full Disk Access is not enough
on its own while the bundle's main executable is a *shell script*. macOS execs
the interpreter, attributes the file access to `/bin/bash` -- which is not the
thing you granted -- and keeps refusing, with the grant sitting there looking
correct. That is why `Contents/MacOS/TradingJournal` is a compiled binary
(`bin/launcher.c`): a Mach-O main executable is what the grant attaches to, and
its children inherit it. The binary does nothing but hand over to
`bin/journal-launch.sh`.

`start-journal.command` sidesteps all of this because Terminal already holds
the file access and the script inherits it.

The other way out, if you would rather not grant permissions at all: move the
`trading-journal` folder out of `~/Documents` (say to `~/TradingJournal`). TCC
does not guard the home directory itself. Both launchers derive their paths
from their own location, so nothing needs editing after a move.

### Note on the `.app` and the Dock

`LSUIElement` is set, so the launcher process itself stays out of the Dock and
the menu bar — the only Dock tile is the app window's, which is what you switch
to. It is ad-hoc code signed so it has a stable identity for the permission
grant to attach to.

## Layout

| Path | What it is |
|---|---|
| `Trading Journal.app` | Dock app (**use this**, after the one-time grant) |
| `bin/install-service.sh`, `bin/uninstall-service.sh` | The background server the Safari web app needs |
| `stop-journal.command` | Kill a stuck server (handles the service too) |
| `bin/journal-launch.sh` | All the logic; both entry points call it |
| `bin/launcher.c`, `bin/build-launcher.sh` | The bundle's compiled entry point, and its rebuild script |
| `bin/make-icon.py` | Draws the icon and builds `AppIcon.icns` |
| `bin/set-webapp-icon.sh`, `bin/set-icon.m` | Puts that icon on the Safari web app |
| `build/` | Icon preview and the intermediate `.iconset` (regenerable) |
| `start-journal.command` | Same thing via Terminal; needs no permission |
| `assets/app-icon.png` | The favicon, which is where the Safari web app's icon comes from |
| `~/Library/Application Support/TradingJournal/` | Chrome profile, pid files, `server.log`, `launcher.log`, `service.log` |

Server output goes to `server.log` in that folder, and the launcher's own
decisions to `launcher.log` — the first places to look if a launch goes nowhere.
The `.app` has no terminal, so `launcher.log` is the only record it leaves.

## Notes

- The port is pinned to 8501 in the launcher and the stop script. Change it in
  both (`PORT=`) if you ever need to.
- The Terminal window is what holds the launcher process, and the launcher is
  what stops the server when the window closes. Closing that Terminal window
  early also stops the server — that is the intended tie, not a bug.
- The Chrome profile is created on first run. Deleting that folder resets the
  window's size, position and zoom.

## The icon

`bin/make-icon.py` draws it and builds `Contents/Resources/AppIcon.icns` — four
ascending candles, one red, on the app's own dark card grey with the same green
and red the calendar uses. Rerun it after editing, then `bin/build-launcher.sh`
to re-sign:

```bash
.venv/bin/python bin/make-icon.py && ./bin/build-launcher.sh
```

`build/icon-preview.png` is the 1024px master if you want to see it full size.
If the Dock or Finder keeps showing the old icon, `touch "Trading Journal.app"`
and `killall Dock`.

## How the background service gets past the permission wall

`bin/install-service.sh` does not point launchd at `streamlit` directly, even
though that would be the obvious thing. launchd's processes have no file access
under `~/Documents`, so that fails exactly like everything else did:

```
/bin/sh: .../.venv/bin/streamlit: Operation not permitted
```

The service instead runs `Trading Journal.app/Contents/MacOS/TradingJournal
--server-only`. That binary carries the app's code signature, and therefore the
Full Disk Access grant attached to it, so the server it starts can read the
project. It is the same binary the Dock icon uses; `--server-only` just means
"start the server in the foreground and open no window", which is the shape
launchd wants.

Consequence worth knowing: if you rebuild the launcher and the grant stops
matching, the background service stops working too. `service.log` in the state
folder will say `Operation not permitted`.
