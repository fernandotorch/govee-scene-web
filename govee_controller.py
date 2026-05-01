#!/usr/bin/env python3
"""
govee_controller.py — TTRPG session lighting controller
Govee H6047 via LAN API. Run once before your session, control from phone.

Setup:
  1. Enable LAN Control in the Govee app (Device Settings → LAN Control)
  2. pip install flask
  3. python govee_controller.py
  4. Open the URL shown on your phone browser
"""

import base64
import socket
import json
import time
import threading
import random
import math
from flask import Flask, jsonify

# ── Network ───────────────────────────────────────────────────────────────────

MULTICAST_IP   = "239.255.255.250"
DISCOVERY_PORT = 4001
LISTEN_PORT    = 4002
CONTROL_PORT   = 4003

_device_ip = None

def discover() -> str | None:
    recv = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    recv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    recv.bind(("", LISTEN_PORT))
    recv.settimeout(5)

    send = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    send.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    msg = json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}})
    send.sendto(msg.encode(), (MULTICAST_IP, DISCOVERY_PORT))

    try:
        _, addr = recv.recvfrom(4096)
        return addr[0]
    except socket.timeout:
        return None
    finally:
        recv.close()
        send.close()

def _send(cmd: dict):
    if not _device_ip:
        return
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.sendto(json.dumps({"msg": cmd}).encode(), (_device_ip, CONTROL_PORT))
    sock.close()

# ── Primitives ────────────────────────────────────────────────────────────────

def _on():           _send({"cmd": "turn",       "data": {"value": 1}})
def _off():          _send({"cmd": "turn",       "data": {"value": 0}})
def _bright(v: int): _send({"cmd": "brightness", "data": {"value": max(1, min(100, v))}})
def _color(r, g, b): _send({"cmd": "colorwc",    "data": {"color": {"r": r, "g": g, "b": b}, "colorTemInKelvin": 0}})

# Per-segment control via ptReal (BLE-over-LAN, base64-encoded 20-byte packets).
# H6047: 10 physical segments — segments 0-4 on left bar, 5-9 on right bar.
# Swap LEFT_MASK / RIGHT_MASK if the bars feel reversed.
LEFT_MASK  = 0x01F   # bits 0-4
RIGHT_MASK = 0x3E0   # bits 5-9

def _seg_packet(r: int, g: int, b: int, mask: int) -> str:
    """One 20-byte BLE color packet for the given segment bitmask, base64-encoded."""
    pkt = bytearray(20)
    pkt[0] = 0x33
    pkt[1] = 0x05
    pkt[2] = 0x15  # color mode
    pkt[3] = 0x01  # RGB
    pkt[4], pkt[5], pkt[6] = r, g, b
    pkt[12:19] = mask.to_bytes(7, byteorder="little")
    pkt[19] = 0
    for byte in pkt[:19]:
        pkt[19] ^= byte
    return base64.b64encode(bytes(pkt)).decode()

def _seg_colors(groups: list[tuple[int, int, int, int]]):
    """Set multiple segment groups at once. groups: [(r, g, b, mask), ...]"""
    _send({"cmd": "ptReal", "data": {"command": [_seg_packet(r, g, b, m) for r, g, b, m in groups]}})

# ── Animation engine ──────────────────────────────────────────────────────────

_stop   = threading.Event()
_thread = None

def _stop_all():
    global _thread
    _stop.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=2)
    _stop.clear()

def _run(fn, *args):
    global _thread
    _stop_all()
    _thread = threading.Thread(target=fn, args=args, daemon=True)
    _thread.start()

# ── Effects ───────────────────────────────────────────────────────────────────

def _police_loop():
    """
    Left bar red / right bar blue, then swap — true rotation across both bars.
    Uses per-segment ptReal control so both colors are visible simultaneously.
    """
    _on()
    _bright(100)
    while not _stop.is_set():
        _seg_colors([(255, 0, 0, LEFT_MASK), (0, 40, 255, RIGHT_MASK)])
        _stop.wait(0.25)
        _seg_colors([(0, 40, 255, LEFT_MASK), (255, 0, 0, RIGHT_MASK)])
        _stop.wait(0.25)

def _club_loop():
    """
    Techno club: hot pink + neon green base, occasional purple/cyan/white.
    Irregular timing so it breathes rather than ticks.
    """
    palette = [
        (255, 0, 140),   # hot pink
        (255, 0, 140),   # hot pink (weighted heavier)
        (0, 255, 100),   # neon green
        (0, 255, 100),   # neon green (weighted heavier)
        (160, 0, 255),   # purple accent
        (0, 200, 255),   # cyan accent
    ]
    _on()
    while not _stop.is_set():
        r, g, b = random.choice(palette)
        _color(r, g, b)
        _bright(random.randint(55, 100))
        _stop.wait(random.uniform(0.06, 0.28))
        # Rare white flash — bass drop moment
        if random.random() < 0.07:
            _color(255, 255, 255)
            _bright(100)
            _stop.wait(0.04)

def _flicker_loop(r, g, b):
    """
    Failing fluorescent: stable white base, then random burst events of rapid on/off.
    Stable periods last 2-8s. Each burst has 3-7 rapid cuts, with occasional
    longer pauses mid-burst so the tube seems to struggle before recovering.
    """
    _on()
    _color(r, g, b)
    _bright(100)
    while not _stop.is_set():
        # Stable — lights on, wait for next burst
        _stop.wait(random.uniform(2.0, 8.0))
        if _stop.is_set():
            break

        # Flicker burst
        for _ in range(random.randint(3, 7)):
            _bright(1)                                  # cut
            _stop.wait(random.uniform(0.02, 0.07))
            _bright(random.randint(75, 100))            # recover
            _stop.wait(random.uniform(0.03, 0.09))
            # Occasional longer struggle — tube can't quite hold on
            if random.random() < 0.25:
                _bright(1)
                _stop.wait(random.uniform(0.12, 0.45))
                _bright(random.randint(80, 100))
                _stop.wait(random.uniform(0.03, 0.07))

        # Settle back to stable
        _color(r, g, b)
        _bright(100)

def _alarm_loop():
    """
    Orange rotating beacon — left then right at police-siren frequency.
    """
    _on()
    _bright(100)
    while not _stop.is_set():
        _seg_colors([(255, 55, 0, LEFT_MASK), (10, 2, 0, RIGHT_MASK)])
        _stop.wait(0.25)
        _seg_colors([(10, 2, 0, LEFT_MASK), (255, 55, 0, RIGHT_MASK)])
        _stop.wait(0.25)

def _disian_loop():
    """
    Disian encounter: deep purple sine-wave pulse with random cold white intrusions.
    The white flashes are short and wrong — things bleeding through from Dis.
    """
    _on()
    phase = 0.0
    while not _stop.is_set():
        phase += 0.04
        v = (math.sin(phase) + 1) / 2          # 0.0 → 1.0 smooth
        # Occasional cold intrusion from the metaplane
        if random.random() < 0.015:
            _color(200, 210, 255)
            _bright(85)
            _stop.wait(random.uniform(0.04, 0.18))
        r = int(65 + v * 45)
        b = int(105 + v * 95)
        _color(r, 0, b)
        _bright(int(22 + v * 58))
        _stop.wait(0.05)

# ── Scene dispatcher ──────────────────────────────────────────────────────────

SCENES = {
    "off":     lambda: (_stop_all(), _off()),
    "police":  lambda: _run(_police_loop),
    "club":    lambda: _run(_club_loop),
    "flicker": lambda: _run(_flicker_loop, 240, 230, 200),
    "alarm":   lambda: _run(_alarm_loop),
    "disian":  lambda: _run(_disian_loop),
}

# ── Web UI ────────────────────────────────────────────────────────────────────

app = Flask(__name__)

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Govee</title>
<style>
  * { box-sizing: border-box; }
  body {
    background: #0e0e0e;
    color: #eee;
    font-family: -apple-system, sans-serif;
    padding: 24px 16px;
    max-width: 420px;
    margin: 0 auto;
  }
  h1 { font-size: 1em; color: #666; margin: 0 0 24px; letter-spacing: 0.05em; }
  .btn {
    display: block;
    width: 100%;
    padding: 24px 16px;
    margin: 10px 0;
    font-size: 1.05em;
    font-weight: 600;
    border: none;
    border-radius: 12px;
    cursor: pointer;
    text-align: left;
    transition: opacity 0.1s;
  }
  .btn:active { opacity: 0.7; }
  .btn small { display: block; font-weight: 400; font-size: 0.8em; opacity: 0.7; margin-top: 2px; }
  .off     { background: #2a2a2a; color: #aaa; }
  .police  { background: linear-gradient(120deg, #cc0000 0%, #0033dd 100%); color: #fff; }
  .club    { background: linear-gradient(120deg, #cc006e 0%, #00cc66 100%); color: #fff; }
  .flicker { background: #3a3020; color: #d4c080; }
  .alarm   { background: #7a2800; color: #ffaa44; }
  .disian  { background: linear-gradient(120deg, #1a0033 0%, #330055 100%); color: #ccaaff; }
  #status  { margin-top: 24px; font-size: 0.8em; color: #555; text-align: center; }
</style>
</head>
<body>
<h1>SESSION LIGHTING</h1>

<button class="btn off" onclick="scene('off')">
  Off
  <small>Kill all effects</small>
</button>

<button class="btn police" onclick="scene('police')">
  Police Siren
  <small>Red / blue emergency lights</small>
</button>

<button class="btn club" onclick="scene('club')">
  Techno Club
  <small>Hot pink &amp; neon green strobe</small>
</button>

<button class="btn flicker" onclick="scene('flicker')">
  Flickering Light
  <small>Damaged fluorescent — space station</small>
</button>

<button class="btn alarm" onclick="scene('alarm')">
  Emergency Alarm
  <small>Orange rotating beacon</small>
</button>

<button class="btn disian" onclick="scene('disian')">
  Disian Encounter
  <small>Deep purple pulse, cold intrusions</small>
</button>

<div id="status">—</div>

<script>
function scene(name) {
  fetch('/scene/' + name, { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      document.getElementById('status').textContent = 'Active: ' + d.scene;
    });
}
</script>
</body>
</html>"""

@app.route("/")
def index():
    return HTML

@app.route("/scene/<name>", methods=["POST"])
def set_scene(name):
    if name not in SCENES:
        return jsonify({"error": "unknown scene"}), 404
    SCENES[name]()
    return jsonify({"scene": name, "ok": True})

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import os
    import sys
    import subprocess

    # Werkzeug's reloader spawns a child process (the actual server) with
    # WERKZEUG_RUN_MAIN=true. Discovery only runs there — not in the watcher.
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        print("Discovering Govee H6047 on local network...")
        _device_ip = discover()

        if not _device_ip:
            print("\nDevice not found.")
            print("→ Open the Govee app → your device → Settings → LAN Control → Enable")
            print("→ Make sure your laptop and the light bar are on the same Wi-Fi network")
            sys.exit(1)

        print(f"Device found at {_device_ip}")

        try:
            local_ip = subprocess.check_output(
                ["hostname", "-I"], text=True
            ).split()[0]
        except Exception:
            local_ip = "your-laptop-ip"

        print(f"\n{'─' * 40}")
        print(f"  Open on your phone:")
        print(f"  http://{local_ip}:5000")
        print(f"{'─' * 40}\n")

    app.run(host="0.0.0.0", port=5000, use_reloader=True)
