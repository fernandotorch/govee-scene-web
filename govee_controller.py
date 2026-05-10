#!/usr/bin/env python3
"""
govee_controller.py — TTRPG session lighting controller + Studio Backend
"""

import base64
import socket
import json
import re
import time
import threading
import random
import math
import os
import sys
import subprocess
import hashlib
import zipfile
from flask import Flask, jsonify, request, send_from_directory, send_file

# ── Network ───────────────────────────────────────────────────────────────────

MULTICAST_IP   = "239.255.255.250"
DISCOVERY_PORT = 4001
LISTEN_PORT    = 4002
CONTROL_PORT   = 4003

_device_ip = None
_sock      = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

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
    global _sock
    if not _device_ip:
        return
    msg = json.dumps({"msg": cmd}).encode()
    try:
        _sock.sendto(msg, (_device_ip, CONTROL_PORT))
    except OSError:
        _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _sock.sendto(msg, (_device_ip, CONTROL_PORT))

# ── Primitives ────────────────────────────────────────────────────────────────

def _on():           _send({"cmd": "turn",       "data": {"value": 1}})
def _off():
    _seg_colors([(0, 0, 0, LEFT_MASK | RIGHT_MASK)])
    _send({"cmd": "turn", "data": {"value": 0}})
def _bright(v: int): _send({"cmd": "brightness", "data": {"value": max(1, min(100, v))}})
def _color(r, g, b): _send({"cmd": "colorwc",    "data": {"color": {"r": r, "g": g, "b": b}, "colorTemInKelvin": 0}})

LEFT_MASK  = 0x01F   # bits 0-4
RIGHT_MASK = 0x3E0   # bits 5-9

def _seg_packet(r: int, g: int, b: int, mask: int) -> str:
    pkt = bytearray(20)
    pkt[0] = 0x33; pkt[1] = 0x05; pkt[2] = 0x15; pkt[3] = 0x01
    pkt[4], pkt[5], pkt[6] = r, g, b
    pkt[12:19] = mask.to_bytes(7, byteorder="little")
    pkt[19] = 0
    for byte in pkt[:19]: pkt[19] ^= byte
    return base64.b64encode(bytes(pkt)).decode()

def _seg_colors(groups: list[tuple[int, int, int, int]]):
    _send({"cmd": "ptReal", "data": {"command": [_seg_packet(r, g, b, m) for r, g, b, m in groups]}})

# ── Animation engine ──────────────────────────────────────────────────────────

_stop   = threading.Event()
_thread = None

def _stop_all():
    global _thread
    _stop.set()
    if _thread and _thread.is_alive(): _thread.join(timeout=2)
    _stop.clear()

def _run(fn, *args):
    global _thread
    _stop_all()
    _thread = threading.Thread(target=fn, args=args, daemon=True)
    _thread.start()

# ── Effects ───────────────────────────────────────────────────────────────────

def _police_loop():
    _on(); _bright(100)
    while not _stop.is_set():
        _seg_colors([(255, 0, 0, LEFT_MASK), (0, 40, 255, RIGHT_MASK)])
        _stop.wait(0.25)
        _seg_colors([(0, 40, 255, LEFT_MASK), (255, 0, 0, RIGHT_MASK)])
        _stop.wait(0.25)

def _club_loop():
    PINK = (255, 0, 180); GREEN = (0, 255, 80); COLORS = [PINK, GREEN]
    PULSE_HZ = 2.0; TICK = 0.15; _on(); t0 = time.time()
    while not _stop.is_set():
        now = time.time()
        l_color = random.choice(COLORS); r_color = PINK if l_color is GREEN else GREEN
        v = (math.sin(2 * math.pi * PULSE_HZ * (now - t0)) + 1) / 2
        scale = 0.55 + 0.45 * v
        ls = tuple(round(c * scale) for c in l_color)
        rs = tuple(round(c * scale) for c in r_color)
        _seg_colors([(*ls, LEFT_MASK), (*rs, RIGHT_MASK)])
        _stop.wait(TICK)

def _flicker_loop(r, g, b):
    _on(); _seg_colors([(r, g, b, LEFT_MASK), (r, g, b, RIGHT_MASK)])
    def bar_loop(mask):
        while not _stop.is_set():
            _seg_colors([(r, g, b, mask)]); _stop.wait(random.uniform(5.0, 10.0))
            if _stop.is_set(): break
            cut = random.uniform(0.6, 1.0)
            while cut > 0.05 and not _stop.is_set():
                _seg_colors([(2, 2, 2, mask)]); _stop.wait(cut)
                if _stop.is_set(): break
                _seg_colors([(r, g, b, mask)]); _stop.wait(cut * random.uniform(0.2, 0.4))
                cut *= random.uniform(0.35, 0.55)
            if not _stop.is_set(): _seg_colors([(r, g, b, mask)])
    left = threading.Thread(target=bar_loop, args=(LEFT_MASK,), daemon=True)
    right = threading.Thread(target=bar_loop, args=(RIGHT_MASK,), daemon=True)
    left.start(); right.start(); _stop.wait(); left.join(timeout=1); right.join(timeout=1)

def _alarm_loop():
    _on(); _bright(100)
    while not _stop.is_set():
        _seg_colors([(255, 55, 0, LEFT_MASK), (10, 2, 0, RIGHT_MASK)])
        _stop.wait(0.25)
        _seg_colors([(10, 2, 0, LEFT_MASK), (255, 55, 0, RIGHT_MASK)])
        _stop.wait(0.25)

def _disian_loop():
    _on(); phase = 0.0
    while not _stop.is_set():
        phase += 0.04; v = (math.sin(phase) + 1) / 2
        if random.random() < 0.015:
            _color(200, 210, 255); _bright(85); _stop.wait(random.uniform(0.04, 0.18))
        r = int(65 + v * 45); b = int(105 + v * 95)
        _color(r, 0, b); _bright(int(22 + v * 58)); _stop.wait(0.05)

SCENES = {
    "off": lambda: (_stop_all(), _off()),
    "police": lambda: _run(_police_loop),
    "club": lambda: _run(_club_loop),
    "flicker": lambda: _run(_flicker_loop, 240, 230, 200),
    "alarm": lambda: _run(_alarm_loop),
    "disian": lambda: _run(_disian_loop),
}

BURST_DEFS = {
    'white-burst':  (255, 255, 255, 0.2),
    'orange-burst': (255, 100,   0, 0.3),
    'purple-pulse': (180,   0, 255, 0.3),
}

_burst_timer = None
_burst_gen   = 0

def _burst_end():
    _seg_colors([(0, 0, 0, LEFT_MASK | RIGHT_MASK)])

def _fire_burst(r, g, b, duration):
    global _burst_timer, _burst_gen
    if _burst_timer is not None:
        _burst_timer.cancel()
    _burst_gen += 1
    gen = _burst_gen
    _on()
    _seg_colors([(r, g, b, LEFT_MASK | RIGHT_MASK)])
    def _timed_off():
        if _burst_gen == gen:
            _burst_end()
    _burst_timer = threading.Timer(duration, _timed_off)
    _burst_timer.start()

# ── Studio Logic ──────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EFFECTS_DIR = os.path.join(BASE_DIR, "effects")
SFX_DIR = os.environ.get("SFX_LIBRARY_PATH", "/home/feru/sfx-library")
PACKS_DIR = os.path.join(BASE_DIR, "packs")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")

for d in [PACKS_DIR, UPLOADS_DIR, SESSIONS_DIR]:
    os.makedirs(d, exist_ok=True)
if not os.path.exists(SFX_DIR): os.makedirs(SFX_DIR, exist_ok=True)

def get_audio_id(category, description, source_name):
    hash_suffix = hashlib.md5(source_name.encode()).hexdigest()[:8]
    return f"{category}-{description}_{hash_suffix}"

# ── Web UI ────────────────────────────────────────────────────────────────────

app = Flask(__name__)

@app.route("/")
def index(): return send_file(os.path.join(BASE_DIR, "templates/index.html"))

@app.route("/studio")
def studio(): return send_file(os.path.join(BASE_DIR, "templates/studio.html"))

@app.route("/scene/<name>", methods=["POST"])
def set_scene(name):
    if name not in SCENES: return jsonify({"error": "unknown scene"}), 404
    SCENES[name](); return jsonify({"scene": name, "ok": True})

def _load_effects():
    descriptors = []
    if os.path.isdir(EFFECTS_DIR):
        for fname in sorted(os.listdir(EFFECTS_DIR)):
            if fname.endswith(".json"):
                with open(os.path.join(EFFECTS_DIR, fname)) as f:
                    try:
                        d = json.load(f)
                        if d.get("ref"):
                            descriptors.append(d)
                    except Exception:
                        pass
    if not descriptors:
        descriptors = [{"ref": k, "name": k.capitalize(), "color": "#555555"} for k in SCENES]
    return descriptors

@app.route("/api/effects", methods=["GET"])
def get_effects(): return jsonify(_load_effects())

@app.route("/api/effects/<ref>/preview", methods=["POST"])
def preview_burst(ref):
    defn = BURST_DEFS.get(ref)
    if not defn:
        return jsonify({"error": "unknown burst ref"}), 404
    _fire_burst(*defn)
    return jsonify({"ok": True})

@app.route("/api/sfx/config", methods=["GET", "POST"])
def sfx_config():
    global SFX_DIR
    if request.method == "POST":
        new_path = request.json.get("path")
        if new_path and os.path.isdir(new_path):
            SFX_DIR = new_path
            return jsonify({"ok": True, "path": SFX_DIR})
        return jsonify({"error": "invalid path"}), 400
    return jsonify({"path": SFX_DIR})

@app.route("/api/sfx/tree")
def get_sfx_tree():
    path = request.args.get("path", "")
    full_path = os.path.join(SFX_DIR, path)
    if not os.path.abspath(full_path).startswith(os.path.abspath(SFX_DIR)):
        return jsonify({"error": "unauthorized"}), 403
    
    items = []
    for entry in os.scandir(full_path):
        items.append({
            "name": entry.name,
            "is_dir": entry.is_dir(),
            "path": os.path.relpath(entry.path, SFX_DIR)
        })
    return jsonify(sorted(items, key=lambda x: (not x["is_dir"], x["name"])))

@app.route("/api/upload", methods=["POST"])
def upload_sfx():
    if "file" not in request.files: return jsonify({"error": "no file"}), 400
    file = request.files["file"]; category = request.form.get("category", "misc")
    description = request.form.get("description", "sound"); source_name = file.filename
    dest_dir = os.path.join(SFX_DIR, category)
    os.makedirs(dest_dir, exist_ok=True)
    
    audio_id = get_audio_id(category, description, source_name)
    output_filename = f"{audio_id}.ogg"
    output_path = os.path.join(dest_dir, output_filename)
    
    temp_path = os.path.join(UPLOADS_DIR, source_name)
    file.save(temp_path)
    
    try:
        subprocess.run(["ffmpeg", "-y", "-i", temp_path, "-c:a", "libvorbis", "-q:a", "4", output_path], check=True)
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", output_path], capture_output=True, text=True)
        duration_ms = int(float(result.stdout.strip()) * 1000)
    except Exception as e: return jsonify({"error": str(e)}), 500
    finally: os.remove(temp_path)
    
    return jsonify({"audio_id": audio_id, "filename": output_filename, "duration_ms": duration_ms, "rel_path": os.path.relpath(output_path, SFX_DIR)})

@app.route("/api/sfx/file/<path:filename>")
def get_sfx_file(filename): return send_from_directory(SFX_DIR, filename)

@app.route("/api/sessions", methods=["GET"])
def list_sessions():
    files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith(".json")]
    return jsonify(sorted(files))

@app.route("/api/sessions/<name>", methods=["GET", "POST", "DELETE"])
def manage_session(name):
    if not name.endswith(".json"): name += ".json"
    path = os.path.join(SESSIONS_DIR, name)
    if request.method == "POST":
        data = request.json
        with open(path, "w") as f: json.dump(data, f, indent=2)
        pack_name = name.replace('.json', '')
        zip_path = os.path.join(PACKS_DIR, f"{pack_name}.zip")
        session_payload = {
            "version": 1,
            "name": data.get("name", pack_name),
            "exported": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "arc": data.get("arc", []),
            "audio_manifest": data.get("audio_manifest", {})
        }
        with zipfile.ZipFile(zip_path, "w") as z:
            z.writestr("session.json", json.dumps(session_payload, indent=2))
        return jsonify({"ok": True})
    if request.method == "DELETE":
        if os.path.exists(path):
            os.remove(path)
            return jsonify({"ok": True})
        return jsonify({"error": "not found"}), 404
    if not os.path.exists(path): return jsonify({"error": "not found"}), 404
    with open(path, "r") as f: return jsonify(json.load(f))

@app.route("/api/export", methods=["POST"])
def export_pack():
    try:
        data = request.json; pack_name = data.get("name", "New Session")
        arc = data.get("arc", []); audio_manifest = data.get("audio_manifest", {})
        safe_name = re.sub(r'[^\w\s\-]', '', pack_name).strip().replace(' ', '_')
        zip_filename = f"{safe_name}.zip"; zip_path = os.path.join(PACKS_DIR, zip_filename)

        warnings = []
        with zipfile.ZipFile(zip_path, 'w') as z:
            for audio_id, info in audio_manifest.items():
                audio_path = os.path.join(SFX_DIR, info['file'])
                if not os.path.exists(audio_path):
                    warnings.append(f'Missing: {info["file"]}')
                    continue
                ext = os.path.splitext(audio_path)[1].lower()
                if ext not in ['.ogg', '.wav', '.mp3', '.flac']:
                    warnings.append(f'Unsupported format: {info["file"]}')
                    continue
                base_id = re.sub(r'\.(ogg|wav|mp3|flac)$', '', audio_id, flags=re.IGNORECASE)
                out_name = base_id + ext
                z.write(audio_path, out_name)
                info['file'] = out_name
            session_json = {
                'version': 1, 'name': pack_name,
                'exported': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'arc': arc, 'audio_manifest': audio_manifest
            }
            z.writestr('session.json', json.dumps(session_json, indent=2))

        return jsonify({"url": f"/api/packs/{zip_filename}", "warnings": warnings})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/api/packs/<filename>")
def get_pack(filename): return send_from_directory(PACKS_DIR, filename)

@app.route("/api/packs", methods=["GET"])
def list_packs():
    files = sorted(f for f in os.listdir(PACKS_DIR) if f.endswith(".zip"))
    return jsonify([{"filename": f, "display_name": f.replace('.zip', '')} for f in files])

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        print("Discovering Govee H6047...")
        _device_ip = discover()
        if _device_ip: print(f"Device found at {_device_ip}")
        try:
            local_ip = subprocess.check_output(["hostname", "-I"], text=True).split()[0]
        except Exception: local_ip = "localhost"
        print(f"\n{'─' * 40}\n  Lighting Lab: http://{local_ip}:5000\n  Studio:       http://{local_ip}:5000/studio\n{'─' * 40}\n")
    app.run(host="0.0.0.0", port=5000, use_reloader=True, threaded=True)
