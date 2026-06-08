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

_device_ip = "YOUR_GOVEE_DEVICE_IP" # Hardcoded for stability
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

def _police_loop():
    _on(); _bright(100)
    session = _session_id
    while not _stop.is_set() and _session_id == session:
        _seg_colors([(255, 0, 0, LEFT_MASK), (0, 40, 255, RIGHT_MASK)])
        _stop.wait(0.25)
        _seg_colors([(0, 40, 255, LEFT_MASK), (255, 0, 0, RIGHT_MASK)])
        _stop.wait(0.25)

def _club_loop():
    PINK = (255, 0, 180); GREEN = (0, 255, 80); COLORS = [PINK, GREEN]
    PULSE_HZ = 2.0; TICK = 0.15; _on(); t0 = time.time()
    session = _session_id
    while not _stop.is_set() and _session_id == session:
        now = time.time()
        l_color = random.choice(COLORS); r_color = PINK if l_color is GREEN else GREEN
        v = (math.sin(2 * math.pi * PULSE_HZ * (now - t0)) + 1) / 2
        scale = 0.55 + 0.45 * v
        ls = tuple(round(c * scale) for c in l_color)
        rs = tuple(round(c * scale) for c in r_color)
        _seg_colors([(*ls, LEFT_MASK), (*rs, RIGHT_MASK)])
        _stop.wait(TICK)

def _flicker_loop(r, g, b, on_min=5.0, on_max=10.0, cut_min=0.6, cut_max=1.0):
    _on(); _seg_colors([(r, g, b, LEFT_MASK), (r, g, b, RIGHT_MASK)])
    def bar_loop(mask):
        session = _session_id
        while not _stop.is_set() and _session_id == session:
            _seg_colors([(r, g, b, mask)]); _stop.wait(random.uniform(on_min, on_max))
            if _stop.is_set() or _session_id != session: break
            cut = random.uniform(cut_min, cut_max)
            while cut > 0.05 and not _stop.is_set() and _session_id == session:
                _seg_colors([(2, 2, 2, mask)]); _stop.wait(cut)
                if _stop.is_set() or _session_id != session: break
                _seg_colors([(r, g, b, mask)]); _stop.wait(cut * random.uniform(0.2, 0.4))
                cut *= random.uniform(0.35, 0.55)
            if not _stop.is_set(): _seg_colors([(r, g, b, mask)])
    left = threading.Thread(target=bar_loop, args=(LEFT_MASK,), daemon=True)
    right = threading.Thread(target=bar_loop, args=(RIGHT_MASK,), daemon=True)
    left.start(); right.start(); _stop.wait(); left.join(timeout=1); right.join(timeout=1)

def _alarm_loop():
    _on(); _bright(100)
    session = _session_id
    while not _stop.is_set() and _session_id == session:
        _seg_colors([(255, 55, 0, LEFT_MASK), (10, 2, 0, RIGHT_MASK)])
        _stop.wait(0.25)
        _seg_colors([(10, 2, 0, LEFT_MASK), (255, 55, 0, RIGHT_MASK)])
        _stop.wait(0.25)

def _brave_sea_loop():
    _on(); _bright(100); t = 0.0
    session = _session_id
    while not _stop.is_set() and _session_id == session:
        t += 0.6  
        packet = []
        crest_base = (t % 3.5) - 1.5
        splash = (random.random() < 0.15)
        for i in range(10):
            mask = 1 << i
            idx = i % 5
            crest_pos = crest_base if i < 5 else ((t * 1.1 + 1.5) % 3.2) - 1.5
            dist = abs(idx - crest_pos)
            r, g, b = (0, 2, 30)
            if dist < 1.0:
                v = max(0.0, 1.0 - dist)
                r = int(r + (200 - r) * v)
                g = int(g + (240 - g) * v)
                b = int(b + (255 - b) * v)
            if splash and random.random() < 0.4: r, g, b = (230, 250, 255)
            packet.append((r, g, b, mask))
        
        _seg_colors(packet) # Stable single packet
        _stop.wait(0.12)

def _torch_fire_loop():
    _on(); _bright(100); t = 0.0
    session = _session_id
    while not _stop.is_set() and _session_id == session:
        t += 0.25
        packet = []
        wind = 0.8 * math.sin(t * 1.2) + 0.4 * math.sin(t * 2.8)
        for h in range(5):
            if h == 0:   br, bg, bb = (180, 15, 0)
            elif h == 1: br, bg, bb = (220, 55, 0)
            elif h == 2: br, bg, bb = (255, 120, 0)
            elif h == 3: br, bg, bb = (255, 190, 40)
            else:        br, bg, bb = (255, 240, 150)
            for is_right in [False, True]:
                mask = (1 << (h + 5)) if is_right else (1 << h)
                bar_phase = 2.5 if is_right else 0.0
                flicker = math.sin(t * 2.5 + bar_phase + h * 0.8)
                sway = wind if is_right else -wind
                if h >= 3:
                    snap = 0.0 if ((is_right and wind < -0.5) or (not is_right and wind > 0.5)) else 1.0
                    agitation = (flicker * 0.7 + 0.3) * snap
                    intensity = agitation * (1.0 + abs(sway) * 0.5)
                else:
                    glow = (flicker * 0.3 + 0.7) 
                    intensity = glow * (0.9 + abs(sway) * 0.1)
                if h >= 2 and random.random() < 0.12: intensity *= random.uniform(1.3, 1.7)
                r, g, b = int(br * intensity), int(bg * intensity), int(bb * intensity)
                packet.append((r, g, b, mask))
        
        # Combined packet to prevent congestion
        _seg_colors(packet)
        _stop.wait(0.12)


def _purple_evil_loop():
    _on(); _bright(100); t = 0.0
    session = _session_id
    while not _stop.is_set() and _session_id == session:
        t += 0.3
        packet = []
        
        # SLIGHTLY REDUCED TERROR CHANCE: 11% (was 15%)
        if random.random() < 0.06:
            roll = random.random()
            
            # Weights remain the same (Sequence-heavy)
            if roll < 0.40:
                _seg_colors([(0, 0, 0, LEFT_MASK | RIGHT_MASK)])
                _stop.wait(random.uniform(0.3, 0.6))
                if _stop.is_set() or _session_id != session: break
                _seg_colors([(255, 0, 0, LEFT_MASK | RIGHT_MASK)])
                _stop.wait(random.uniform(0.2, 0.4))
                continue
            elif roll < 0.70:
                _seg_colors([(255, 0, 0, LEFT_MASK | RIGHT_MASK)])
                _stop.wait(random.uniform(0.15, 0.3))
                if _stop.is_set() or _session_id != session: break
                _seg_colors([(0, 0, 0, LEFT_MASK | RIGHT_MASK)])
                _stop.wait(random.uniform(0.4, 0.8))
                continue
            elif roll < 0.90:
                _seg_colors([(255, 0, 0, LEFT_MASK | RIGHT_MASK)])
                _stop.wait(random.uniform(0.2, 0.5))
                continue
            else:
                _seg_colors([(0, 0, 0, LEFT_MASK | RIGHT_MASK)])
                _stop.wait(random.uniform(0.3, 0.7))
                continue

        wind = 0.8 * math.sin(t * 1.2) + 0.4 * math.sin(t * 2.8)
        
        for h in range(5):
            if h == 0:   br, bg, bb = (40, 0, 90)    # Deep Purple Base
            elif h == 1: br, bg, bb = (100, 0, 200)  # Vibrant Purple
            elif h == 2: br, bg, bb = (255, 0, 150)  # Neon Magenta
            elif h == 3: br, bg, bb = (230, 230, 255) # Cold White
            else:        br, bg, bb = (255, 10, 0)   # Crackling Red Top
            
            for is_right in [False, True]:
                mask = (1 << (h + 5)) if is_right else (1 << h)
                bar_phase = 2.5 if is_right else 0.0
                flicker = math.sin(t * 2.5 + bar_phase + h * 0.8)
                sway = wind if is_right else -wind
                
                if h >= 3:
                    snap = 0.0 if ((is_right and wind < -0.5) or (not is_right and wind > 0.5)) else 1.0
                    agitation = (flicker * 0.7 + 0.3) * snap
                    intensity = agitation * (1.0 + abs(sway) * 0.5)
                else:
                    glow = (flicker * 0.3 + 0.7) 
                    intensity = glow * (0.9 + abs(sway) * 0.1)
                
                if h >= 2 and random.random() < 0.12: intensity *= random.uniform(1.3, 1.7)
                
                r, g, b = int(br * intensity), int(bg * intensity), int(bb * intensity)
                packet.append((r, g, b, mask))
        
        _seg_colors(packet)
        _stop.wait(0.12)


def _disian_loop():
    _on(); phase = 0.0
    session = _session_id
    while not _stop.is_set() and _session_id == session:
        phase += 0.04; v = (math.sin(phase) + 1) / 2
        if random.random() < 0.015:
            _color(200, 210, 255); _bright(85); _stop.wait(random.uniform(0.04, 0.18))
        r = int(65 + v * 45); b = int(105 + v * 95)
        _color(r, 0, b); _bright(int(22 + v * 58)); _stop.wait(0.08)


def _static_loop(r, g, b, brightness=100):
    _on(); _bright(brightness)
    session = _session_id
    while not _stop.is_set() and _session_id == session:
        _seg_colors([(r, g, b, LEFT_MASK | RIGHT_MASK)])
        _stop.wait(2.0)


def _draconis_hb_loop(r, g, b):
    _on(); _bright(100)
    session = _session_id
    base = (r // 6, g // 6, b // 6)
    dub  = (r * 3 // 4, g * 3 // 4, b * 3 // 4)
    while not _stop.is_set() and _session_id == session:
        _seg_colors([(r, g, b, LEFT_MASK | RIGHT_MASK)])
        _stop.wait(0.10)
        if _stop.is_set() or _session_id != session: break
        _seg_colors([(*base, LEFT_MASK | RIGHT_MASK)])
        _stop.wait(0.18)
        if _stop.is_set() or _session_id != session: break
        _seg_colors([(*dub, LEFT_MASK | RIGHT_MASK)])
        _stop.wait(0.10)
        if _stop.is_set() or _session_id != session: break
        _seg_colors([(*base, LEFT_MASK | RIGHT_MASK)])
        _stop.wait(1.6 + random.uniform(-0.2, 0.4))


def _draconis_pulse_loop(r, g, b, period=3.5, min_s=0.12, max_s=0.55):
    _on(); _bright(100)
    session = _session_id
    t0 = time.time()
    PERIOD = period
    MIN_S, MAX_S = min_s, max_s
    while not _stop.is_set() and _session_id == session:
        v = (math.sin(2 * math.pi * (time.time() - t0) / PERIOD) + 1) / 2
        s = MIN_S + (MAX_S - MIN_S) * v
        _seg_colors([(round(r * s), round(g * s), round(b * s), LEFT_MASK | RIGHT_MASK)])
        _stop.wait(0.05)


SCENES = {
    'off': lambda: (_stop_all(), _off()),
    'police': lambda: _run(_police_loop),
    'club': lambda: _run(_club_loop),
    'flicker': lambda: _run(_flicker_loop, 240, 230, 200),
    'alarm': lambda: _run(_alarm_loop),
    'brave-sea': lambda: _run(_brave_sea_loop),
    'torch-fire': lambda: _run(_torch_fire_loop),
    'evil': lambda: _run(_purple_evil_loop),
    'disian': lambda: _run(_disian_loop),
    'flicker-slow':     lambda: _run(_flicker_loop, 240, 230, 200, 20.0, 45.0, 0.2, 0.5),
    'cronus':           lambda: _run(_static_loop, 165, 195, 255),
    'draconis':  lambda: _run(_draconis_hb_loop,   80, 200,  10),
    'autodestruct': lambda: _run(_draconis_pulse_loop, 255, 80, 0, 1.8, 0.05, 1.0),
}

def _smg_burst():
    global _burst_timer, _burst_gen, _burst_active
    if _burst_timer is not None: _burst_timer.cancel()
    _burst_gen += 1; gen = _burst_gen
    _burst_active = True; _on()
    def _step(n):
        global _burst_timer, _burst_active
        if _burst_gen != gen: return
        if n >= 8:
            _burst_active = False; _burst_end(); return
        color = (255, 240, 180) if n % 2 == 0 else (255, 150, 10)
        _seg_colors([(color[0], color[1], color[2], LEFT_MASK | RIGHT_MASK)])
        _burst_timer = threading.Timer(0.105, lambda: _step(n + 1))
        _burst_timer.start()
    _step(0)

def _pulse_rifle_burst():
    global _burst_timer, _burst_gen, _burst_active
    if _burst_timer is not None: _burst_timer.cancel()
    _burst_gen += 1; gen = _burst_gen
    _burst_active = True; _on()
    _seg_colors([(30, 90, 255, LEFT_MASK | RIGHT_MASK)])   # blue charge
    def _boom():
        global _burst_timer, _burst_active
        if _burst_gen != gen: return
        _seg_colors([(230, 255, 255, LEFT_MASK | RIGHT_MASK)])  # white-cyan crack
        def _afterglow():
            global _burst_timer, _burst_active
            if _burst_gen != gen: return
            _seg_colors([(0, 255, 80, LEFT_MASK | RIGHT_MASK)])    # green afterglow
            def _done():
                global _burst_active
                if _burst_gen != gen: return
                _burst_active = False; _burst_end()
            _burst_timer = threading.Timer(0.20, _done); _burst_timer.start()
        _burst_timer = threading.Timer(0.15, _afterglow); _burst_timer.start()
    _burst_timer = threading.Timer(0.60, _boom); _burst_timer.start()

def _flamethrower_burst():
    global _burst_timer, _burst_gen, _burst_active
    if _burst_timer is not None: _burst_timer.cancel()
    _burst_gen += 1; gen = _burst_gen
    _burst_active = True; _on()
    flicker = [
        (255,  80,  0), (255, 160, 20), (255,  55,  0),
        (255, 175, 25), (255,  65,  0), (255, 145, 10),
        (220,  45,  0), (255, 110,  5),
    ]
    def _run_flicker(on_done, speed=1.0):
        _seg_colors([(255, 220, 80, LEFT_MASK | RIGHT_MASK)])   # ignition flash
        def _step(n):
            global _burst_timer
            if _burst_gen != gen: return
            if n >= len(flicker):
                on_done(); return
            _seg_colors([(flicker[n][0], flicker[n][1], flicker[n][2], LEFT_MASK | RIGHT_MASK)])
            _burst_timer = threading.Timer(0.115 * speed, lambda: _step(n + 1)); _burst_timer.start()
        _burst_timer = threading.Timer(0.08 * speed, lambda: _step(0)); _burst_timer.start()
    def _second():
        if _burst_gen != gen: return
        def _do_gap():
            if _burst_gen != gen: return
            _seg_colors([(20, 5, 0, LEFT_MASK | RIGHT_MASK)])   # near-dark gap
            def _start():
                if _burst_gen != gen: return
                def _done():
                    global _burst_active
                    if _burst_gen != gen: return
                    _seg_colors([(150, 18, 0, LEFT_MASK | RIGHT_MASK)])  # dying ember
                    def _end():
                        global _burst_active
                        if _burst_gen != gen: return
                        _burst_active = False; _burst_end()
                    _burst_timer = threading.Timer(0.375, _end); _burst_timer.start()
                _run_flicker(_done, speed=1.5)
            _burst_timer = threading.Timer(0.28, _start); _burst_timer.start()
        _burst_timer = threading.Timer(0.10, _do_gap); _burst_timer.start()
    _run_flicker(_second)


def _bio_burst():
    global _burst_timer, _burst_gen, _burst_active
    if _burst_timer is not None: _burst_timer.cancel()
    _burst_gen += 1; gen = _burst_gen
    _burst_active = True; _on()
    steps = [
        # Phase 1 — pressure build → white-pink burst → first decay (1.6s)
        (130,   0,  15, 200),
        (180,   5,  20, 200),
        (230,  10,  25, 200),
        ( 15,   0,   5, 100),
        (255, 180, 160, 100),
        (255,   0,  10, 100),
        ( 20,   0,   5, 100),
        (210,   0,  15, 100),
        ( 15,   0,   3, 200),
        ( 70,   0,  10, 300),
        # Phase 2 — low simmer → compression → rapid red/dark finale → fade (4.3s)
        (150,   0,  10, 300),   # lower fire: second squish begins
        (200,   0,  15, 300),   # building
        (230,   5,  15, 200),   # more intense
        (180,   0,  12, 150),   # slight ebb
        (225,   5,  15, 200),   # back up
        ( 15,   0,   3, 150),   # compression beat
        (255,   0,  10,  80),   # SMG-like finale: red
        ( 10,   0,   2,  80),   # dark
        (255,   0,  10,  80),   # red
        ( 10,   0,   2,  80),   # dark
        (240,   0,   8,  80),   # red dimming
        ( 10,   0,   2,  80),   # dark
        (220,   0,   8,  80),   # red dimmer
        ( 10,   0,   2,  80),   # dark
        (200,   0,   6, 100),   # slower
        ( 10,   0,   2, 100),   # dark
        (170,   0,   5, 120),   # dimmer
        ( 10,   0,   2, 120),   # dark
        (130,   0,   4, 300),   # fade
        ( 10,   0,   2, 350),   # dark
        ( 80,   0,   3, 400),   # dimmer fade
        ( 10,   0,   2, 400),   # dark
        ( 30,   0,   1, 500),   # nearly done
        (  8,   0,   0, 700),   # almost out
        ( 15,   0,   0, 700),   # last ember
        (  4,   0,   0, 600),   # nearly gone
        ( 10,   0,   0, 700),   # final flicker
        (  2,   0,   0, 700),   # gone
    ]
    def _step(n):
        global _burst_timer, _burst_active
        if _burst_gen != gen: return
        if n >= len(steps):
            _burst_active = False; _burst_end(); return
        r, g, b, delay = steps[n]
        _seg_colors([(r, g, b, LEFT_MASK | RIGHT_MASK)])
        _burst_timer = threading.Timer(delay / 1000.0, lambda: _step(n + 1))
        _burst_timer.start()
    _step(0)


BURST_DEFS = {
    'white-burst':    lambda: _fire_burst(255, 255, 255, 0.20),
    'orange-burst':   lambda: _fire_burst(255, 100,   0, 0.30),
    'purple-pulse':   lambda: _fire_burst(180,   0, 255, 0.30),
    'fire-spark':     lambda: _fire_burst(255, 200,  50, 0.30),
    'smg-burst':      _smg_burst,
    'pulse-rifle':    _pulse_rifle_burst,
    'flamethrower':   _flamethrower_burst,
    'bio-burst':      _bio_burst,
}


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
                    for ext in ['.ogg', '.wav', '.mp3', '.flac', '.aiff', '.aif']:
                        search_targets.add(audio_id + ext)
                    for k in ['file', 'source_name']:
                        if info.get(k):
                            base = os.path.basename(info[k])
                            search_targets.add(base)
                            search_targets.add(re.sub(r'\.(ogg|wav|mp3|flac|aiff|aif)$', '.ogg', base, flags=re.IGNORECASE))
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
                if ext not in ['.ogg', '.wav', '.mp3', '.flac', '.aiff', '.aif']:
                    warnings.append(f'Unsupported format: {info["file"]}'); continue
                file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
                if file_size_mb > 20 and ext == ".ogg":
                    warnings.append(f"Large OGG ({file_size_mb:.0f} MB): {info['file']} - consider shorter loop")
                base_id = re.sub(r'\.(ogg|wav|mp3|flac|aiff|aif)$', '', audio_id, flags=re.IGNORECASE)
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

if __name__ == '__main__':
    print('SFX_DIR:', SFX_DIR)
    print('Discovering Govee H6047...')
    if _device_ip: print('Device found at', _device_ip)
    try:
        local_ip = subprocess.check_output(['hostname', '-I'], text=True).split()[0]
    except Exception: local_ip = 'localhost'
    print('\n' + ('─' * 40))
    print('  Lighting Lab: http://' + local_ip + ':5000')
    print('  Studio:       http://' + local_ip + ':5000/studio')
    print(('─' * 40) + '\n')
    app.run(host='0.0.0.0', port=5000, use_reloader=False, threaded=True)
