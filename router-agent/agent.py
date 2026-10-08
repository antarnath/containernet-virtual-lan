"""Router Agent — tiny HTTP server on :9090 inside every M4 router container.

The backend's router_proxy (phase 03) will poll this agent every 2s
to render the live router panel (Routes / ARP / Interfaces tabs).
In phase 02 the endpoints exist but nothing polls them yet; the
agent is wired and reachable from inside the container.

Endpoint summary (see router-base.Dockerfile for the full contract):
  GET    /state/routes         text   `ip route` output
  GET    /state/neigh          text   `ip neigh`  output
  GET    /state/ifaces         text   `ip -br addr` output
  GET    /state/all            JSON   {routes, neigh, ifaces, ip_forward}
  POST   /routes               JSON   add a static route
  DELETE /routes               JSON   remove a static route
  GET    /healthz              text   200 OK

Design notes:
  * Uses Python's stdlib `http.server` so the image stays tiny
    (no aiohttp / no flask).
  * Each handler shells out to `ip ...` and returns the text or
    a tiny JSON wrapper. We do NOT parse the kernel's output —
    the UI's job is to render it monospaced, exactly as `ip`
    prints it. Parsing is the backend's job in later phases.
  * Mutations (`POST /routes`, `DELETE /routes`) return the
    resulting `ip route` so the caller can confirm. Errors
    return 4xx with the `ip` stderr.
  * The server is single-threaded (BaseHTTPRequestHandler is
    sync). For M4 v1 the load is one backend polling every 2s,
    so concurrency is fine.

Configuration is read from env vars:
  PORT     default 9090
  NODE_ID  optional, used in /healthz response for debugging
"""

from __future__ import annotations

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs


PORT = int(os.environ.get("PORT", "9090"))
NODE_ID = os.environ.get("NODE_ID", "router")


def _run(cmd: list[str], timeout: float = 5.0) -> tuple[int, str, str]:
    """Run a shell command. Returns (returncode, stdout, stderr)."""
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        return 124, "", f"timeout after {timeout}s: {exc}"


def _ip_forward() -> bool:
    try:
        with open("/proc/sys/net/ipv4/ip_forward") as f:
            return f.read().strip() == "1"
    except OSError:
        return False


class RouterHandler(BaseHTTPRequestHandler):
    server_version = "RouterAgent/1.0"

    # ─── low-level helpers ───────────────────────────────────────
    def _send_text(self, body: str, status: int = 200) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict | None:
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return None

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        # Quieter logs; the backend's poll traffic is noisy.
        # Uncomment to debug:
        # sys.stderr.write("[router-agent] " + fmt % args + "\n")
        return

    # ─── GETs ────────────────────────────────────────────────────
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/healthz":
            self._send_text("ok\n")
            return
        if self.path == "/state/routes":
            rc, out, err = _run(["ip", "route"])
            self._send_text(out if rc == 0 else f"err: {err}", 200 if rc == 0 else 500)
            return
        if self.path == "/state/neigh":
            rc, out, err = _run(["ip", "neigh"])
            self._send_text(out if rc == 0 else f"err: {err}", 200 if rc == 0 else 500)
            return
        if self.path == "/state/ifaces":
            rc, out, err = _run(["ip", "-br", "addr"])
            self._send_text(out if rc == 0 else f"err: {err}", 200 if rc == 0 else 500)
            return
        if self.path == "/state/all":
            _, routes, _ = _run(["ip", "route"])
            _, neigh, _ = _run(["ip", "neigh"])
            _, ifaces, _ = _run(["ip", "-br", "addr"])
            self._send_json({
                "node_id": NODE_ID,
                "ip_forward": _ip_forward(),
                "routes": routes,
                "neigh": neigh,
                "ifaces": ifaces,
            })
            return
        self._send_text("not found\n", 404)

    # ─── mutations ───────────────────────────────────────────────
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/routes":
            self._send_text("not found\n", 404)
            return
        body = self._read_json() or {}
        dst = body.get("dst")
        via = body.get("via")
        dev = body.get("dev")
        if not dst or not dev:
            self._send_json({"ok": False, "error": "dst and dev are required"}, 400)
            return
        cmd = ["ip", "route", "replace", dst]
        if via:
            cmd += ["via", via]
        cmd += ["dev", dev]
        rc, out, err = _run(cmd)
        if rc != 0:
            self._send_json({"ok": False, "error": err.strip() or out.strip()}, 400)
            return
        self._send_json({"ok": True, "route": " ".join(cmd[3:])})

    def do_DELETE(self) -> None:  # noqa: N802
        if self.path != "/routes":
            self._send_text("not found\n", 404)
            return
        body = self._read_json() or {}
        # `parse_qs` is the easy way to read query params for DELETE.
        params = parse_qs(self.path.split("?", 1)[1]) if "?" in self.path else {}
        dst = body.get("dst") or (params.get("dst", [None])[0])
        dev = body.get("dev") or (params.get("dev", [None])[0])
        if not dst:
            self._send_json({"ok": False, "error": "dst is required"}, 400)
            return
        cmd = ["ip", "route", "del", dst]
        if dev:
            cmd += ["dev", dev]
        rc, out, err = _run(cmd)
        if rc != 0:
            self._send_json({"ok": False, "error": err.strip() or out.strip()}, 400)
            return
        self._send_json({"ok": True})


def main() -> None:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), RouterHandler)
    print(f"[router-agent] listening on 0.0.0.0:{PORT} (node_id={NODE_ID})", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
