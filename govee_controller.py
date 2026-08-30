#!/usr/bin/env python3
"""
govee_controller.py - TTRPG session lighting controller + Studio Backend
"""

import base64
import copy
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
import tempfile
from flask import Flask, jsonify, request, send_from_directory, send_file

# ── Network ───────────────────────────────────────────────────────────────────

MULTICAST_IP   = "239.255.255.250"
DISCOVERY_PORT = 4001
LISTEN_PORT    = 4002
CONTROL_PORT   = 4003

_device_ip = os.environ.get("GOVEE_DEVICE_IP") or None
_sock      = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
_last_send_time = 0.0

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
    global _sock, _last_send_time
    if not _device_ip:
        return
    now = time.time()
    if (now - _last_send_time) * 1000 < 40:
        return
    _last_send_time = now
    msg = json.dumps({"msg": cmd}).encode()
    try:
        _sock.sendto(msg, (_device_ip, CONTROL_PORT))
    except OSError:
        _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        _sock.sendto(msg, (_device_ip, CONTROL_PORT))

_export_progress = {"status": "idle", "current": 0, "total": 0, "file": "", "file_percent": 0}
_export_result = None

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
    r, g, b = max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b)))
    pkt = bytearray(20)
    pkt[0] = 0x33; pkt[1] = 0x05; pkt[2] = 0x15; pkt[3] = 0x01
    pkt[4], pkt[5], pkt[6] = r, g, b
    pkt[12:19] = mask.to_bytes(7, byteorder="little")
    pkt[19] = 0
    for byte in pkt[:19]: pkt[19] ^= byte
    return base64.b64encode(bytes(pkt)).decode()

def _seg_colors(groups: list[tuple[int, int, int, int]]):
    global _last_left, _last_right
    if not _burst_active:
        for r, g, b, mask in groups:
            if mask & LEFT_MASK:
                _last_left = (r, g, b)
            if mask & RIGHT_MASK:
                _last_right = (r, g, b)
    _send({"cmd": "ptReal", "data": {"command": [_seg_packet(r, g, b, m) for r, g, b, m in groups]}})

# ── Animation engine ──────────────────────────────────────────────────────────


_stop        = threading.Event()
_thread      = None
_session_id  = 0
_burst_timer = None
_burst_gen   = 0
_last_left    = None   # last (r,g,b) sent to LEFT_MASK by an animation
_last_right   = None   # last (r,g,b) sent to RIGHT_MASK by an animation
_burst_active = False  # True while a burst flash is in progress
_current_scene = None

def _stop_all():
    global _thread, _session_id, _burst_timer, _burst_active
    _burst_active = False
    _session_id += 1
    _stop.set()
    if _thread and _thread.is_alive(): _thread.join(timeout=1.0)
    if _burst_timer: 
        _burst_timer.cancel()
        _burst_timer = None
    _stop.clear()

def _run(fn, *args):
    global _thread
    _stop_all()
    _thread = threading.Thread(target=fn, args=args, daemon=True)
    _thread.start()

# ── Effects ───────────────────────────────────────────────────────────────────

def _burst_end():
    restore = []
    if _last_left:
        restore.append((*_last_left, LEFT_MASK))
    if _last_right:
        restore.append((*_last_right, RIGHT_MASK))
    if restore:
        _seg_colors(restore)
    else:
        _seg_colors([(0, 0, 0, LEFT_MASK | RIGHT_MASK)])

def _fire_burst(r, g, b, duration):
    global _burst_timer, _burst_gen, _burst_active
    if _burst_timer is not None:
        _burst_timer.cancel()
    _burst_gen += 1
    gen = _burst_gen
    _burst_active = True
    _on()
    _seg_colors([(r, g, b, LEFT_MASK | RIGHT_MASK)])
    def _timed_off():
        global _burst_active
        _burst_active = False
        if _burst_gen == gen:
            _burst_end()
    _burst_timer = threading.Timer(duration, _timed_off)
    _burst_timer.start()

import importlib
import effect_defs as _effect_defs
_effect_defs._init(sys.modules[__name__])
SCENES = _effect_defs.SCENES
BURST_DEFS = _effect_defs.BURST_DEFS

# ── Studio Logic ──────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EFFECTS_DIR = os.path.join(BASE_DIR, "effects")
SFX_DIR = os.environ.get("SFX_LIBRARY_PATH", "/home/feru/sfx-library")
PACKS_DIR = os.path.join(BASE_DIR, "packs")
UPLOADS_DIR = os.path.join(BASE_DIR, "uploads")
SESSIONS_DIR = os.path.join(BASE_DIR, "sessions")
SPOTIFY_FILE = os.path.join(BASE_DIR, "spotify_playlists.json")

def _load_spotify_playlists():
    if os.path.exists(SPOTIFY_FILE):
        try:
            with open(SPOTIFY_FILE) as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    return []

def _save_spotify_playlists(playlists):
    with open(SPOTIFY_FILE, "w") as f:
        json.dump(playlists, f, indent=2)

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
    global _current_scene
    if name not in SCENES: return jsonify({"error": "unknown scene"}), 404
    _current_scene = name
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
    fn = BURST_DEFS.get(ref)
    if not fn:
        return jsonify({"error": "unknown burst ref"}), 404
    fn()
    return jsonify({"ok": True})

@app.route("/api/reload", methods=["POST"])
def reload_effects():
    global SCENES, BURST_DEFS
    importlib.reload(_effect_defs)
    _effect_defs._init(sys.modules[__name__])
    SCENES = _effect_defs.SCENES
    BURST_DEFS = _effect_defs.BURST_DEFS
    return jsonify({"ok": True, "scenes": len(SCENES), "bursts": len(BURST_DEFS)})

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

@app.route("/api/spotify", methods=["GET", "POST"])
def spotify_playlists():
    if request.method == "POST":
        data = request.json
        if not isinstance(data, list):
            return jsonify({"error": "expected a list"}), 400
        _save_spotify_playlists(data)
        return jsonify(data)
    return jsonify(_load_spotify_playlists())

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
        subprocess.run([
            "ffmpeg", "-y", "-i", temp_path,
            "-af", "loudnorm=I=-14:TP=-1:LRA=11",
            "-c:a", "libvorbis", "-q:a", "4",
            output_path
        ], check=True, preexec_fn=os.setsid)
        result = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", output_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        duration_ms = int(float(result.stdout.strip()) * 1000)
    except Exception as e:
        _export_progress = {"status": "idle", "current": 0, "total": 0, "file": "", "file_percent": 0}
        return jsonify({"error": str(e)}), 500
    finally: os.remove(temp_path)
    return jsonify({"audio_id": audio_id, "filename": output_filename, "duration_ms": duration_ms, "rel_path": os.path.relpath(output_path, SFX_DIR)})

@app.route("/api/normalize-audio", methods=["POST"])
def normalize_audio():
    rel_path = request.json.get("path", "")
    abs_path = os.path.join(SFX_DIR, rel_path)
    if not os.path.exists(abs_path):
        return jsonify({"error": "not found"}), 404
    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in [".ogg", ".wav", ".mp3", ".flac", ".aiff", ".aif", ".m4a"]:
        return jsonify({"error": "unsupported"}), 400
    tmp_path = abs_path + ".norm.tmp.ogg"
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", abs_path,
             "-af", "loudnorm=I=-14:TP=-1:LRA=11",
             "-c:a", "libvorbis", "-q:a", "4", tmp_path],
            capture_output=True, timeout=60
        )
        if r.returncode != 0:
            if os.path.exists(tmp_path): os.remove(tmp_path)
            return jsonify({"error": "ffmpeg failed"}), 500
        duration_ms = int((_get_duration(tmp_path) or 0) * 1000)
        os.replace(tmp_path, abs_path if ext == ".ogg" else os.path.splitext(abs_path)[0] + ".ogg")
        return jsonify({"ok": True, "duration_ms": duration_ms})
    except Exception as e:
        if os.path.exists(tmp_path): os.remove(tmp_path)
        return jsonify({"error": str(e)}), 500

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
        return jsonify({"ok": True})
    if request.method == "DELETE":
        if os.path.exists(path):
            os.remove(path)
            return jsonify({"ok": True})
        return jsonify({"error": "not found"}), 404
    if not os.path.exists(path): return jsonify({"error": "not found"}), 404
    with open(path, "r") as f: return jsonify(json.load(f))


@app.route("/api/export/status")
def export_status():
    result = dict(_export_progress)
    if _export_progress.get('status') in ('done', 'error') and _export_result:
        result.update(_export_result)
    return jsonify(result)

def _get_duration(path):
    try:
        res = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', path], capture_output=True, text=True)
        return float(res.stdout.strip())
    except: return 0

def _run_ffmpeg_with_progress(in_path, out_path, duration):
    global _export_progress
    cmd = [
        'ffmpeg', '-y', '-progress', 'pipe:1', '-i', in_path,
        '-af', 'loudnorm=I=-14:TP=-1:LRA=11',
        '-c:a', 'libvorbis', '-q:a', '4',
        out_path
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, preexec_fn=os.setsid)
    while True:
        line = process.stdout.readline()
        if not line: break
        if 'out_time_ms=' in line:
            try:
                ms = int(line.split('=')[1].strip())
                if duration > 0:
                    _export_progress['file_percent'] = min(100, int((ms / 1000000) / duration * 100))
            except: pass
    process.wait()

def _do_export(data):
    global _export_progress, _export_result
    try:
        pack_name = data.get("name", "New Session")
        scenes = data.get("scenes", []); audio_manifest = data.get("audio_manifest", {})
        safe_name = re.sub(r'[^\w\s\-]', '', pack_name).strip().replace(' ', '_')
        zip_filename = f"{safe_name}.zip"; zip_path = os.path.join(PACKS_DIR, zip_filename)
        warnings = []
        zip_manifest = copy.deepcopy(audio_manifest)
        with zipfile.ZipFile(zip_path, 'w', allowZip64=True) as z:
            for i, (audio_id, info) in enumerate(zip_manifest.items()):
                _export_progress["current"] = i + 1
                _export_progress["file"] = info.get("file", audio_id)
                audio_path = os.path.join(SFX_DIR, info['file'])
                if not os.path.exists(audio_path):
                    search_targets = set()
                    search_targets.add(audio_id)
                    for ext in ['.ogg', '.wav', '.mp3', '.flac', '.aiff', '.aif', '.m4a']:
                        search_targets.add(audio_id + ext)
                    for k in ['file', 'source_name']:
                        if info.get(k):
                            base = os.path.basename(info[k])
                            search_targets.add(base)
                            search_targets.add(re.sub(r'\.(ogg|wav|mp3|flac|aiff|aif|m4a)$', '.ogg', base, flags=re.IGNORECASE))
                    print(f'Attempting recovery for {audio_id}. Targets: {search_targets}')
                    found_path = None
                    for root, _, files in os.walk(SFX_DIR):
                        for f in files:
                            if f in search_targets:
                                found_path = os.path.join(root, f); break
                        if found_path: break
                    if found_path:
                        print(f'Recovered {info.get("file")} -> {found_path}')
                        audio_path = found_path
                        new_rel = os.path.relpath(found_path, SFX_DIR)
                        new_base = os.path.basename(found_path)
                        info['file'] = new_rel; info['source_name'] = new_base
                        if audio_id in audio_manifest:
                            audio_manifest[audio_id]['file'] = new_rel
                            audio_manifest[audio_id]['source_name'] = new_base
                    else:
                        warnings.append(f'Missing: {info["file"]}'); continue
                ext = os.path.splitext(audio_path)[1].lower()
                if ext not in ['.ogg', '.wav', '.mp3', '.flac', '.aiff', '.aif', '.m4a']:
                    warnings.append(f'Unsupported format: {info["file"]}'); continue
                file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
                if file_size_mb > 20 and ext == ".ogg":
                    warnings.append(f"Large OGG ({file_size_mb:.0f} MB): {info['file']} - consider shorter loop")
                base_id = re.sub(r'\.(ogg|wav|mp3|flac|aiff|aif|m4a)$', '', audio_id, flags=re.IGNORECASE)
                if ext == '.ogg':
                    _export_progress['file_percent'] = 100
                    z.write(audio_path, base_id + '.ogg'); info['file'] = base_id + '.ogg'
                else:
                    final_ogg_path = os.path.join(os.path.dirname(audio_path), base_id + '.ogg')
                    try:
                        duration = _get_duration(audio_path)
                        _run_ffmpeg_with_progress(audio_path, final_ogg_path, duration)
                        if os.path.exists(final_ogg_path):
                            os.remove(audio_path)
                            info['file'] = base_id + '.ogg'; info['source_name'] = base_id + '.ogg'
                            if audio_id in audio_manifest:
                                audio_manifest[audio_id]['file'] = base_id + '.ogg'
                                audio_manifest[audio_id]['source_name'] = base_id + '.ogg'
                            z.write(final_ogg_path, base_id + '.ogg')
                            new_size_mb = os.path.getsize(final_ogg_path) / (1024 * 1024)
                            if new_size_mb > 20:
                                warnings.append(f"Still large after conversion ({new_size_mb:.0f} MB): {info['file']}")
                        else:
                            warnings.append(f"Conversion failed: {info['file']}")
                    except Exception as e:
                        warnings.append(f"Conversion error {info['file']}: {str(e)}")
            z.writestr('session.json', json.dumps({
                'version': 1, 'name': pack_name,
                'exported': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'scenes': scenes, 'audio_manifest': zip_manifest
            }, indent=2))
        session_path = os.path.join(SESSIONS_DIR, pack_name + '.json')
        if os.path.exists(session_path):
            try:
                with open(session_path, 'r') as f: disk_session = json.load(f)
                if 'audio_manifest' not in disk_session: disk_session['audio_manifest'] = {}
                disk_session['audio_manifest'].update(audio_manifest)
                with open(session_path, 'w') as f: json.dump(disk_session, f, indent=2)
            except: pass
        _export_result = {"url": f"/api/packs/{zip_filename}", "warnings": warnings, "audio_manifest": audio_manifest}
        _export_progress = {"status": "done", "current": 0, "total": 0, "file": "", "file_percent": 0}
    except Exception as e:
        _export_result = {"error": str(e)}
        _export_progress = {"status": "error", "current": 0, "total": 0, "file": "", "file_percent": 0}

@app.route("/api/export", methods=["POST"])
def export_pack():
    global _export_progress, _export_result
    if _export_progress.get('status') == 'busy':
        return jsonify({'error': 'export already in progress'}), 409
    _export_result = None
    data = request.json
    _export_progress = {"status": "busy", "current": 0, "total": len(data.get('audio_manifest', {})), "file": "", "file_percent": 0}
    threading.Thread(target=_do_export, args=(data,), daemon=True).start()
    return jsonify({"status": "started"})

@app.route("/api/packs/<filename>")
def get_pack(filename): return send_from_directory(PACKS_DIR, filename)

@app.route("/api/packs", methods=["GET"])
def list_packs():
    files = sorted(f for f in os.listdir(PACKS_DIR) if f.endswith(".zip"))
    return jsonify([{"filename": f, "display_name": f.replace('.zip', '')} for f in files])

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not _device_ip:
        print("GOVEE_DEVICE_IP not set, running discovery...")
        _device_ip = discover()
        if _device_ip:
            print(f"Device found at {_device_ip}")
        else:
            print("Warning: Govee device not found. Set GOVEE_DEVICE_IP env var.")
    else:
        print(f"Using device IP from env: {_device_ip}")

    print('SFX_DIR:', SFX_DIR)
    try:
        local_ip = subprocess.check_output(['hostname', '-I'], text=True).split()[0]
    except Exception: local_ip = 'localhost'
    print('\n' + ('─' * 40))
    print('  Lighting Lab: http://' + local_ip + ':5000')
    print('  Studio:       http://' + local_ip + ':5000/studio')
    print(('─' * 40) + '\n')
    app.run(host='0.0.0.0', port=5000, use_reloader=False, threaded=True)
