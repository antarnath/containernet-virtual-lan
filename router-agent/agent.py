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

  PUT    /dhcp                 JSON   configure DHCP on one interface
                                     (writes /etc/dnsmasq.d/<iface>.conf
                                      and SIGHUPs dnsmasq)
  GET    /dhcp/leases          JSON   [{mac, ip, expires_at, hostname}]
                                     parsed from
                                     /var/lib/misc/dnsmasq.leases

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
  PORT             default 9090
  NODE_ID          optional, used in /healthz response for debugging
  DHCP_ENABLED     "1" if any interface on this router has DHCP
                   enabled (the backend computes this from the
                   project state and passes it at spawn time).
                   When "0", the agent never starts dnsmasq even
                   if a /dhcp request arrives.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs


PORT = int(os.environ.get("PORT", "9090"))
NODE_ID = os.environ.get("NODE_ID", "router")
# M5-01 / 1.2 — set by the backend to "1" when ANY interface on this
# router has DHCP enabled, "0" otherwise. If "0", PUT /dhcp returns
# 403 (the project says this interface doesn't have a DHCP server).
DHCP_ENABLED_ANY = os.environ.get("DHCP_ENABLED", "0") == "1"

# Dnsmasq config dir (one file per interface, name = interface name).
DNSMASQ_CONF_DIR = "/etc/dnsmasq.d"
DNSMASQ_LEASES = "/var/lib/misc/dnsmasq.leases"
DNSMASQ_PIDFILE = "/var/run/dnsmasq.pid"


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


# ─── DHCP helpers (M5-01 / 1.2) ──────────────────────────────────────────
def _dnsmasq_running() -> bool:
    """True if a dnsmasq process is alive (pidfile + kill -0)."""
    try:
        with open(DNSMASQ_PIDFILE) as f:
            pid = int(f.read().strip())
    except (OSError, ValueError):
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _iface_has_ip(iface: str) -> bool:
    """True if ``iface`` has any IPv4 in the container's netns.

    Used right before we start dnsmasq: a freshly-spawned
    container's veth often shows up without an IP (Docker's
    ``net.connect(ipv4_address=...)`` reliably sets the IP on
    the bridge endpoint but the veth inside the netns is
    frequently empty). Without an IP on the iface, dnsmasq
    refuses to bind with "unknown interface" or "no address
    range available".
    """
    rc, out, _ = _run(["ip", "-4", "-o", "addr", "show", "dev", iface])
    if rc != 0:
        return False
    return "inet " in out


def _iface_cidr(iface: str) -> str | None:
    """Return the first IPv4 CIDR on ``iface`` (e.g. ``10.0.0.1/24``)."""
    rc, out, _ = _run(["ip", "-4", "-o", "addr", "show", "dev", iface])
    if rc != 0:
        return None
    for line in out.splitlines():
        # "3: eth1    inet 10.0.0.1/24 brd 10.0.0.255 scope global eth1"
        parts = line.split()
        if "inet" in parts:
            i = parts.index("inet")
            if i + 1 < len(parts):
                return parts[i + 1]
    return None


def _ensure_iface_ip(iface: str, expected_cidr: str | None) -> tuple[bool, str]:
    """Make sure ``iface`` has ``expected_cidr`` (or any IPv4) set.

    The backend passes the user's pinned IP+mask in
    ``expected_cidr`` (e.g. ``10.0.0.1/24``). If the veth inside
    the container's netns is empty (a known Docker bug — see
    ``_ensure_veth_ip`` in node_service.py), we add it
    ourselves. The container has CAP_NET_ADMIN, so this works
    even from a non-root agent process.

    Returns (ok, message). Best-effort: a failure here just
    bubbles up so the agent can return 500 to the backend.
    """
    if _iface_has_ip(iface):
        return True, "iface already has ip"
    if not expected_cidr:
        return False, f"iface {iface} has no ip and no expected_cidr given"
    rc, _, err = _run(["ip", "addr", "add", expected_cidr, "dev", iface])
    if rc != 0:
        return False, f"ip addr add {expected_cidr} dev {iface} failed: {err.strip()}"
    return True, f"added {expected_cidr} to {iface}"


def _start_dnsmasq() -> tuple[bool, str]:
    """Start dnsmasq in the background.

    Returns (ok, message). Idempotent — if already running, returns
    (True, "already running"). The binary needs to read all of
    /etc/dnsmasq.d/*.conf, so this must be called AFTER at least
    one interface's config has been written.
    """
    if _dnsmasq_running():
        return True, "already running"
    # Ensure the conf dir exists.
    os.makedirs(DNSMASQ_CONF_DIR, exist_ok=True)
    # Ensure the leases file exists (dnsmasq will not create it on
    # its own if there's no client yet, and GET /dhcp/leases would
    # return 404 — we want a stable file path).
    os.makedirs(os.path.dirname(DNSMASQ_LEASES), exist_ok=True)
    if not os.path.exists(DNSMASQ_LEASES):
        open(DNSMASQ_LEASES, "a").close()
    # dnsmasq flags:
    #   -k  : don't fork (we manage the background ourselves; the
    #         agent's setsid makes the daemon survive us)
    #         (we actually use no -k, with & we just detach)
    #   --conf-dir : pull in /etc/dnsmasq.d/*.conf
    # We invoke without -k and double-fork via subprocess.Popen +
    # setsid; the agent's parent doesn't wait.
    cmd = [
        "dnsmasq",
        "--conf-dir=" + DNSMASQ_CONF_DIR + ",*.conf",
        "--pid-file=" + DNSMASQ_PIDFILE,
        "--dhcp-leasefile=" + DNSMASQ_LEASES,
        "--log-queries",
        "--log-dhcp",
    ]
    try:
        # Detach into its own session so it survives if the agent
        # is reloaded. We capture stderr to a temp file so we can
        # surface the real reason if dnsmasq fails to start
        # (typically "unknown interface" because the veth IP is
        # missing, or "address already in use" because port 67
        # is bound elsewhere).
        import tempfile
        err_fd, err_path = tempfile.mkstemp(prefix="dnsmasq-err-", suffix=".log")
        os.close(err_fd)
        with open(err_path, "wb") as err_f:
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=err_f,
                stderr=err_f,
                start_new_session=True,
            )
        # Give dnsmasq up to 5s to write its pidfile. It usually
        # takes ~50ms but on a busy machine binding port 67 can
        # race with iptables rebuilds.
        for _ in range(50):
            if _dnsmasq_running():
                try:
                    os.remove(err_path)
                except OSError:
                    pass
                return True, f"started pid={proc.pid}"
            time.sleep(0.1)
        # Surface dnsmasq's actual error before the generic
        # timeout message so the backend can log a useful reason.
        try:
            with open(err_path) as f:
                err_text = f.read().strip()
        except OSError:
            err_text = ""
        try:
            os.remove(err_path)
        except OSError:
            pass
        detail = f": {err_text[:200]}" if err_text else ""
        return False, f"dnsmasq did not write pidfile within 5s{detail}"
    except OSError as exc:
        return False, f"failed to start dnsmasq: {exc}"


def _sighup_dnsmasq() -> tuple[bool, str]:
    """Send SIGHUP to dnsmasq so it re-reads /etc/dnsmasq.d/*.conf.

    Returns (ok, message). If dnsmasq is not running, starts it.
    """
    if not _dnsmasq_running():
        # First-time start: at least one conf file should already
        # be on disk (the caller writes the conf before calling
        # SIGHUP). If none, dnsmasq would start with no config.
        return _start_dnsmasq()
    try:
        with open(DNSMASQ_PIDFILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, signal.SIGHUP)
        return True, "SIGHUP sent"
    except (OSError, ValueError) as exc:
        return False, f"failed to SIGHUP dnsmasq: {exc}"


def _write_dhcp_conf(
    iface: str,
    pool_start: str,
    pool_end: str,
    lease_time: int,
    dns: str | None,
) -> tuple[bool, str]:
    """Write /etc/dnsmasq.d/<iface>.conf with the DHCP range.

    ``lease_time`` is in seconds. ``dns`` is a comma-separated list
    of IPv4 servers (the dnsmasq option takes the same form).
    """
    if not iface or "/" in iface or iface.startswith("."):
        return False, f"invalid interface name: {iface!r}"
    path = os.path.join(DNSMASQ_CONF_DIR, f"{iface}.conf")
    lines = [
        f"# Auto-generated by router-agent for interface {iface}",
        f"interface={iface}",
        "bind-interfaces",
        f"dhcp-range={pool_start},{pool_end},{lease_time}",
    ]
    if dns:
        # dhcp-option=6,<ip>[,<ip>...]
        lines.append(f"dhcp-option=6,{dns}")
    try:
        os.makedirs(DNSMASQ_CONF_DIR, exist_ok=True)
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        return True, f"wrote {path}"
    except OSError as exc:
        return False, f"failed to write {path}: {exc}"


def _remove_dhcp_conf(iface: str) -> tuple[bool, str]:
    """Remove the dnsmasq config file for this interface (if any)."""
    path = os.path.join(DNSMASQ_CONF_DIR, f"{iface}.conf")
    try:
        if os.path.exists(path):
            os.remove(path)
            return True, f"removed {path}"
        return True, "no conf to remove"
    except OSError as exc:
        return False, f"failed to remove {path}: {exc}"


def _read_leases() -> list[dict]:
    """Parse /var/lib/misc/dnsmasq.leases.

    dnsmasq's lease format (one per line):
        <expires_at_epoch> <mac> <ip> <hostname> <client_id>

    We return ``[{mac, ip, expires_at, hostname}, ...]`` with empty
    / missing fields normalized to empty strings. If the file is
    missing or empty, return [].
    """
    out: list[dict] = []
    try:
        with open(DNSMASQ_LEASES) as f:
            raw = f.read()
    except OSError:
        return out
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            expires_at = int(parts[0])
        except ValueError:
            continue
        out.append({
            "mac": parts[1],
            "ip": parts[2],
            "hostname": parts[3] if len(parts) > 3 else "",
            "expires_at": expires_at,
        })
    return out


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
        if self.path == "/dhcp/leases":
            # M5-01 / 1.2 — the backend polls this every 5s while
            # the project is running to render the leases table.
            self._send_json({
                "leases": _read_leases(),
                "dhcp_enabled_any": DHCP_ENABLED_ANY,
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
        if not dst:
            self._send_json({"ok": False, "error": "dst is required"}, 400)
            return
        if not via and not dev:
            # The kernel can resolve either the next-hop via or the
            # outgoing interface, but needs at least one of them to
            # make sense of the destination.
            self._send_json(
                {"ok": False, "error": "via or dev is required"}, 400,
            )
            return
        cmd = ["ip", "route", "replace", dst]
        if via:
            cmd += ["via", via]
        if dev:
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

    # ─── M5-01 / 1.2 — DHCP config (PUT /dhcp) ─────────────────────
    def do_PUT(self) -> None:  # noqa: N802
        if self.path != "/dhcp":
            self._send_text("not found\n", 404)
            return
        body = self._read_json() or {}
        iface = body.get("interface")
        enabled = bool(body.get("enabled"))
        # M5-01 / 1.2 — backend passes the user-pinned IP+mask as
        # ``expected_cidr`` (e.g. ``10.0.0.1/24``). If the veth
        # inside the container's netns is empty (a known Docker
        # race — net.connect sets the IP on the bridge endpoint
        # but the veth is often missing the IP), we add it here so
        # dnsmasq can bind. This is the most reliable layer to
        # fix it: the agent runs in the netns with full caps and
        # can call ``ip addr add`` directly.
        expected_cidr = body.get("expected_cidr")
        if not iface:
            self._send_json({"ok": False, "error": "interface is required"}, 400)
            return
        if enabled:
            pool_start = body.get("pool_start")
            pool_end = body.get("pool_end")
            lease_time = body.get("lease_time", 43200)
            dns = body.get("dns")
            if not pool_start or not pool_end:
                self._send_json(
                    {"ok": False, "error": "pool_start and pool_end required"}, 400
                )
                return
            # Defensive: ensure the iface has an IP before we ask
            # dnsmasq to bind to it. Without this, dnsmasq exits
            # with "unknown interface" / "no address range
            # available" because the veth is empty.
            ok, msg = _ensure_iface_ip(iface, expected_cidr)
            if not ok:
                self._send_json({"ok": False, "error": msg}, 500)
                return
            ok, msg = _write_dhcp_conf(iface, pool_start, pool_end, lease_time, dns)
            if not ok:
                self._send_json({"ok": False, "error": msg}, 500)
                return
        else:
            ok, msg = _remove_dhcp_conf(iface)
            if not ok:
                self._send_json({"ok": False, "error": msg}, 500)
                return
        # If this router has DHCP enabled on any iface, start /
        # SIGHUP dnsmasq. If not, leave dnsmasq alone (it'll just
        # have an empty config dir, which is fine — it never
        # bound port 67).
        if DHCP_ENABLED_ANY:
            ok, msg = _sighup_dnsmasq()
            if not ok:
                self._send_json({"ok": False, "error": msg}, 500)
                return
        self._send_json({
            "ok": True,
            "interface": iface,
            "enabled": enabled,
        })


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
