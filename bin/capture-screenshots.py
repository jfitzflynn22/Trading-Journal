#!/usr/bin/env python
"""Screenshot the app into docs/screenshots/, for the README.

    python bin/make-demo-data.py --db demo.db
    JOURNAL_DB=$PWD/demo.db streamlit run app.py --server.port 8600 &
    python bin/capture-screenshots.py --port 8600

Drives headless Chrome over the DevTools protocol rather than using its
--screenshot flag: Streamlit paints over a websocket after load, and that flag
fires too early, capturing the grey loading skeleton. Here each page is given
time to settle and is then captured through Page.captureScreenshot.

Standard library only -- including a ~40-line websocket client -- so it needs
nothing that is not already installed to run the app.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PAGES = [("", "dashboard"), ("journal", "journal"),
         ("analytics", "analytics"), ("new-trade", "add-trade")]


class DevTools:
    """The smallest websocket client that can drive Chrome."""

    def __init__(self, ws_url: str):
        u = urllib.parse.urlparse(ws_url)
        self.sock = socket.create_connection((u.hostname, u.port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.send(
            f"GET {u.path} HTTP/1.1\r\nHost: {u.hostname}:{u.port}\r\n"
            f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode())
        if b"101" not in self.sock.recv(4096):
            raise RuntimeError("devtools refused the websocket upgrade")
        self._id = 0

    def _send(self, payload: dict) -> None:
        data = json.dumps(payload).encode()
        mask = os.urandom(4)
        n = len(data)
        header = b"\x81"
        if n < 126:
            header += bytes([0x80 | n])
        elif n < 65536:
            header += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            header += bytes([0x80 | 127]) + struct.pack(">Q", n)
        self.sock.send(header + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _recv(self) -> dict:
        buf = b""
        while True:
            head = self.sock.recv(2)
            if not head:
                raise RuntimeError("devtools closed the connection")
            length = head[1] & 127
            if length == 126:
                length = struct.unpack(">H", self.sock.recv(2))[0]
            elif length == 127:
                length = struct.unpack(">Q", self.sock.recv(8))[0]
            chunk = b""
            while len(chunk) < length:
                chunk += self.sock.recv(length - len(chunk))
            buf += chunk
            if head[0] & 0x80:
                return json.loads(buf)

    def call(self, method: str, **params):
        self._id += 1
        want = self._id
        self._send({"id": want, "method": method, "params": params})
        while True:
            msg = self._recv()
            if msg.get("id") == want:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8600, help="port the app is on")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--settle", type=float, default=9.0,
                    help="seconds to let each page finish rendering")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent.parent
    out_dir = root / "docs" / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    if not Path(CHROME).exists():
        print(f"Google Chrome not found at {CHROME}", file=sys.stderr)
        return 1

    profile = Path("/tmp/journal-shot-profile")
    subprocess.run(["rm", "-rf", str(profile)], check=False)
    chrome = subprocess.Popen(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         "--remote-debugging-port=9222", f"--user-data-dir={profile}",
         f"--window-size={args.width},{args.height}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        ws = None
        for _ in range(40):                    # wait for devtools to come up
            time.sleep(0.5)
            try:
                targets = json.load(urllib.request.urlopen(
                    "http://127.0.0.1:9222/json", timeout=3))
            except Exception:
                continue
            pages = [t for t in targets if t["type"] == "page"]
            if pages:
                ws = pages[0]["webSocketDebuggerUrl"]
                break
        if ws is None:
            print("devtools never became available", file=sys.stderr)
            return 1

        dt = DevTools(ws)
        dt.call("Page.enable")
        for path, name in PAGES:
            url = f"http://127.0.0.1:{args.port}/{path}"
            dt.call("Page.navigate", url=url)
            time.sleep(args.settle)            # websocket render, not just load
            shot = dt.call("Page.captureScreenshot", format="png")
            target = out_dir / f"{name}.png"
            target.write_bytes(base64.b64decode(shot["data"]))
            print(f"  {target.relative_to(root)}  ({target.stat().st_size:,} bytes)")
    finally:
        chrome.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
