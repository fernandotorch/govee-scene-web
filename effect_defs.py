import math, random, threading, time
_gc = None

def _init(gc_module):
    global _gc
    _gc = gc_module

def _police_loop():
    _gc._on(); _gc._bright(100)
    session = _gc._session_id
    while not _gc._stop.is_set() and _gc._session_id == session:
        _gc._seg_colors([(255, 0, 0, _gc.LEFT_MASK), (0, 40, 255, _gc.RIGHT_MASK)])
        _gc._stop.wait(0.25)
        _gc._seg_colors([(0, 40, 255, _gc.LEFT_MASK), (255, 0, 0, _gc.RIGHT_MASK)])
        _gc._stop.wait(0.25)

def _club_loop():
    PINK = (255, 0, 180); GREEN = (0, 255, 80); COLORS = [PINK, GREEN]
    PULSE_HZ = 2.0; TICK = 0.15; _gc._on(); t0 = time.time()
    session = _gc._session_id
    while not _gc._stop.is_set() and _gc._session_id == session:
        now = time.time()
        l_color = random.choice(COLORS); r_color = PINK if l_color is GREEN else GREEN
        v = (math.sin(2 * math.pi * PULSE_HZ * (now - t0)) + 1) / 2
        scale = 0.55 + 0.45 * v
        ls = tuple(round(c * scale) for c in l_color)
        rs = tuple(round(c * scale) for c in r_color)
        _gc._seg_colors([(*ls, _gc.LEFT_MASK), (*rs, _gc.RIGHT_MASK)])
        _gc._stop.wait(TICK)

def _flicker_loop(r, g, b, on_min=5.0, on_max=10.0, cut_min=0.6, cut_max=1.0):
    _gc._on(); _gc._seg_colors([(r, g, b, _gc.LEFT_MASK), (r, g, b, _gc.RIGHT_MASK)])
    def bar_loop(mask):
        session = _gc._session_id
        while not _gc._stop.is_set() and _gc._session_id == session:
            _gc._seg_colors([(r, g, b, mask)]); _gc._stop.wait(random.uniform(on_min, on_max))
            if _gc._stop.is_set() or _gc._session_id != session: break
            cut = random.uniform(cut_min, cut_max)
            while cut > 0.05 and not _gc._stop.is_set() and _gc._session_id == session:
                _gc._seg_colors([(2, 2, 2, mask)]); _gc._stop.wait(cut)
                if _gc._stop.is_set() or _gc._session_id != session: break
                _gc._seg_colors([(r, g, b, mask)]); _gc._stop.wait(cut * random.uniform(0.2, 0.4))
                cut *= random.uniform(0.35, 0.55)
            if not _gc._stop.is_set(): _gc._seg_colors([(r, g, b, mask)])
    left = threading.Thread(target=bar_loop, args=(_gc.LEFT_MASK,), daemon=True)
    right = threading.Thread(target=bar_loop, args=(_gc.RIGHT_MASK,), daemon=True)
    left.start(); right.start(); _gc._stop.wait(); left.join(timeout=1); right.join(timeout=1)

def _flicker_split_loop(r1, g1, b1, r2, g2, b2, on_min=5.0, on_max=10.0, cut_min=0.6, cut_max=1.0):
    _gc._on(); _gc._seg_colors([(r1, g1, b1, _gc.LEFT_MASK), (r2, g2, b2, _gc.RIGHT_MASK)])
    def bar_loop(r, g, b, mask):
        session = _gc._session_id
        while not _gc._stop.is_set() and _gc._session_id == session:
            _gc._seg_colors([(r, g, b, mask)]); _gc._stop.wait(random.uniform(on_min, on_max))
            if _gc._stop.is_set() or _gc._session_id != session: break
            cut = random.uniform(cut_min, cut_max)
            while cut > 0.05 and not _gc._stop.is_set() and _gc._session_id == session:
                _gc._seg_colors([(2, 2, 2, mask)]); _gc._stop.wait(cut)
                if _gc._stop.is_set() or _gc._session_id != session: break
                _gc._seg_colors([(r, g, b, mask)]); _gc._stop.wait(cut * random.uniform(0.2, 0.4))
                cut *= random.uniform(0.35, 0.55)
            if not _gc._stop.is_set(): _gc._seg_colors([(r, g, b, mask)])
    left = threading.Thread(target=bar_loop, args=(r1, g1, b1, _gc.LEFT_MASK), daemon=True)
    right = threading.Thread(target=bar_loop, args=(r2, g2, b2, _gc.RIGHT_MASK), daemon=True)
    left.start(); right.start(); _gc._stop.wait(); left.join(timeout=1); right.join(timeout=1)

def _alarm_loop():
    _gc._on(); _gc._bright(100)
    session = _gc._session_id
    while not _gc._stop.is_set() and _gc._session_id == session:
        _gc._seg_colors([(255, 55, 0, _gc.LEFT_MASK), (10, 2, 0, _gc.RIGHT_MASK)])
        _gc._stop.wait(0.25)
        _gc._seg_colors([(10, 2, 0, _gc.LEFT_MASK), (255, 55, 0, _gc.RIGHT_MASK)])
        _gc._stop.wait(0.25)

def _brave_sea_loop():
    _gc._on(); _gc._bright(100); t = 0.0
    session = _gc._session_id
    while not _gc._stop.is_set() and _gc._session_id == session:
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
        
        _gc._seg_colors(packet) # Stable single packet
        _gc._stop.wait(0.12)

def _torch_fire_loop():
    _gc._on(); _gc._bright(100); t = 0.0
    session = _gc._session_id
    while not _gc._stop.is_set() and _gc._session_id == session:
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
        _gc._seg_colors(packet)
        _gc._stop.wait(0.12)


def _purple_evil_loop():
    _gc._on(); _gc._bright(100); t = 0.0
    session = _gc._session_id
    while not _gc._stop.is_set() and _gc._session_id == session:
        t += 0.3
        packet = []
        
        # SLIGHTLY REDUCED TERROR CHANCE: 11% (was 15%)
        if random.random() < 0.06:
            roll = random.random()
            
            # Weights remain the same (Sequence-heavy)
            if roll < 0.40:
                _gc._seg_colors([(0, 0, 0, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
                _gc._stop.wait(random.uniform(0.3, 0.6))
                if _gc._stop.is_set() or _gc._session_id != session: break
                _gc._seg_colors([(255, 0, 0, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
                _gc._stop.wait(random.uniform(0.2, 0.4))
                continue
            elif roll < 0.70:
                _gc._seg_colors([(255, 0, 0, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
                _gc._stop.wait(random.uniform(0.15, 0.3))
                if _gc._stop.is_set() or _gc._session_id != session: break
                _gc._seg_colors([(0, 0, 0, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
                _gc._stop.wait(random.uniform(0.4, 0.8))
                continue
            elif roll < 0.90:
                _gc._seg_colors([(255, 0, 0, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
                _gc._stop.wait(random.uniform(0.2, 0.5))
                continue
            else:
                _gc._seg_colors([(0, 0, 0, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
                _gc._stop.wait(random.uniform(0.3, 0.7))
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
        
        _gc._seg_colors(packet)
        _gc._stop.wait(0.12)


def _disian_loop():
    _gc._on(); phase = 0.0
    session = _gc._session_id
    while not _gc._stop.is_set() and _gc._session_id == session:
        phase += 0.04; v = (math.sin(phase) + 1) / 2
        if random.random() < 0.015:
            _gc._color(200, 210, 255); _gc._bright(85); _gc._stop.wait(random.uniform(0.04, 0.18))
        r = int(65 + v * 45); b = int(105 + v * 95)
        _gc._color(r, 0, b); _gc._bright(int(22 + v * 58)); _gc._stop.wait(0.08)


def _amber_breathe_loop(g_delta=120, b_delta=130):
    _gc._on(); _gc._bright(100)
    session = _gc._session_id; t0 = time.time()
    while not _gc._stop.is_set() and _gc._session_id == session:
        if not _gc._burst_active:
            v = (math.sin(2 * math.pi * (time.time() - t0) / 12.0) + 1) / 2
            r = int(200 + 55 * v)
            g = int(90 + g_delta * v)
            b = int(b_delta * v)
            _gc._seg_colors([(r, g, b, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
        _gc._stop.wait(0.05)


def _risties_deep_loop():
    _keyframes = [
        (200, 90,  0),   # amber
        (255, 115, 75),  # rose
        (255,  85,  93), # deep pink
    ]
    _gc._on(); _gc._bright(100)
    session = _gc._session_id; t0 = time.time()
    cycle = 18.0
    while not _gc._stop.is_set() and _gc._session_id == session:
        if not _gc._burst_active:
            t = ((time.time() - t0) % cycle) / cycle
            seg = t * 3
            i = int(seg) % 3
            frac = (1 - math.cos((seg - int(seg)) * math.pi)) / 2
            c0 = _keyframes[i]; c1 = _keyframes[(i + 1) % 3]
            r = int(c0[0] + (c1[0] - c0[0]) * frac)
            g = int(c0[1] + (c1[1] - c0[1]) * frac)
            b = int(c0[2] + (c1[2] - c0[2]) * frac)
            _gc._seg_colors([(r, g, b, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
        _gc._stop.wait(0.05)


def _rich_district_loop():
    _gc._on(); _gc._bright(100)
    session = _gc._session_id; t0 = time.time()
    next_flicker = t0 + random.uniform(20.0, 45.0)
    while not _gc._stop.is_set() and _gc._session_id == session:
        now = time.time()
        if not _gc._burst_active:
            v = (math.sin(2 * math.pi * (now - t0) / 12.0) + 1) / 2
            r = 255
            g = int(80 * v)
            b = int(180 - 90 * v)
            if now >= next_flicker:
                cut = random.uniform(0.05, 0.12)
                _gc._seg_colors([(0, 0, 0, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
                _gc._stop.wait(cut)
                if _gc._stop.is_set() or _gc._session_id != session: break
                next_flicker = time.time() + random.uniform(20.0, 45.0)
                continue
            _gc._seg_colors([(r, g, b, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
        _gc._stop.wait(0.05)


def _corp_lab_loop():
    _gc._on(); _gc._bright(100)
    session = _gc._session_id; t0 = time.time()
    while not _gc._stop.is_set() and _gc._session_id == session:
        if not _gc._burst_active:
            v = (math.sin(2 * math.pi * (time.time() - t0) / 14.0) + 1) / 2 * 0.65
            r = int(165 + 90 * v)
            g = int(195 - 110 * v)
            b = int(255 - 162 * v)
            _gc._seg_colors([(r, g, b, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
        _gc._stop.wait(0.05)


def _bus_stop_loop():
    _gc._on(); _gc._bright(100)
    session = _gc._session_id
    t0 = time.time()
    next_sweep = t0 + random.uniform(8.0, 15.0)
    next_neon = t0 + random.uniform(15.0, 30.0)
    sweep_start = None
    sweep_dir = 1
    sweep_duration = 0.75
    neon_start = None
    neon_side = None
    neon_duration = 3.0
    shimmer_phase = [random.uniform(0, 6.28) for _ in range(10)]
    while not _gc._stop.is_set() and _gc._session_id == session:
        if _gc._burst_active:
            _gc._stop.wait(0.05); continue
        now = time.time()
        t = now - t0

        base = []
        for i in range(10):
            shimmer = (math.sin(t * 0.9 + shimmer_phase[i]) + 1) / 2
            scale = 0.75 + 0.35 * shimmer
            base.append([int(55 * scale), int(70 * scale), int(100 * scale)])

        if neon_start is None and now >= next_neon:
            neon_start = now
            neon_side = random.choice([range(0, 5), range(5, 10)])
        if neon_start is not None:
            nt = now - neon_start
            if nt >= neon_duration:
                neon_start = None
                next_neon = now + random.uniform(15.0, 30.0)
            else:
                envelope = math.sin(math.pi * nt / neon_duration)
                blend = 0.55 * envelope
                for i in neon_side:
                    base[i][0] = int(base[i][0] + (180 - base[i][0]) * blend)
                    base[i][1] = int(base[i][1] + (15 - base[i][1]) * blend)
                    base[i][2] = int(base[i][2] + (20 - base[i][2]) * blend)

        if sweep_start is None and now >= next_sweep:
            sweep_start = now
            sweep_dir = random.choice([1, -1])
        if sweep_start is not None:
            st = now - sweep_start
            if st >= sweep_duration:
                sweep_start = None
                next_sweep = now + random.uniform(8.0, 15.0)
            else:
                progress = st / sweep_duration
                pos = progress * 9 if sweep_dir == 1 else (1 - progress) * 9
                for i in range(10):
                    dist = abs(i - pos)
                    if dist < 1.6:
                        v = max(0.0, 1.0 - dist / 1.6)
                        base[i][0] = int(base[i][0] + (225 - base[i][0]) * v)
                        base[i][1] = int(base[i][1] + (225 - base[i][1]) * v)
                        base[i][2] = int(base[i][2] + (210 - base[i][2]) * v)

        packet = [(base[i][0], base[i][1], base[i][2], 1 << i) for i in range(10)]
        _gc._seg_colors(packet)
        _gc._stop.wait(0.08)


def _static_loop(r, g, b, brightness=100):
    _gc._on(); _gc._bright(brightness)
    session = _gc._session_id
    while not _gc._stop.is_set() and _gc._session_id == session:
        _gc._seg_colors([(r, g, b, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
        _gc._stop.wait(2.0)


def _draconis_hb_loop(r, g, b):
    _gc._on(); _gc._bright(100)
    session = _gc._session_id
    base = (r // 6, g // 6, b // 6)
    dub  = (r * 3 // 4, g * 3 // 4, b * 3 // 4)
    while not _gc._stop.is_set() and _gc._session_id == session:
        _gc._seg_colors([(r, g, b, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
        _gc._stop.wait(0.10)
        if _gc._stop.is_set() or _gc._session_id != session: break
        _gc._seg_colors([(*base, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
        _gc._stop.wait(0.18)
        if _gc._stop.is_set() or _gc._session_id != session: break
        _gc._seg_colors([(*dub, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
        _gc._stop.wait(0.10)
        if _gc._stop.is_set() or _gc._session_id != session: break
        _gc._seg_colors([(*base, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
        _gc._stop.wait(1.6 + random.uniform(-0.2, 0.4))


def _draconis_pulse_loop(r, g, b, period=3.5, min_s=0.12, max_s=0.55):
    _gc._on(); _gc._bright(100)
    session = _gc._session_id
    t0 = time.time()
    PERIOD = period
    MIN_S, MAX_S = min_s, max_s
    while not _gc._stop.is_set() and _gc._session_id == session:
        v = (math.sin(2 * math.pi * (time.time() - t0) / PERIOD) + 1) / 2
        s = MIN_S + (MAX_S - MIN_S) * v
        _gc._seg_colors([(round(r * s), round(g * s), round(b * s), _gc.LEFT_MASK | _gc.RIGHT_MASK)])
        _gc._stop.wait(0.05)

def _smg_burst():
    if _gc._burst_timer is not None: _gc._burst_timer.cancel()
    _gc._burst_gen += 1; gen = _gc._burst_gen
    _gc._burst_active = True; _gc._on()
    def _step(n):
        if _gc._burst_gen != gen: return
        if n >= 8:
            _gc._burst_active = False; _gc._burst_end(); return
        color = (255, 240, 180) if n % 2 == 0 else (255, 150, 10)
        _gc._seg_colors([(color[0], color[1], color[2], _gc.LEFT_MASK | _gc.RIGHT_MASK)])
        _gc._burst_timer = threading.Timer(0.105, lambda: _step(n + 1))
        _gc._burst_timer.start()
    _step(0)

def _pulse_rifle_burst():
    if _gc._burst_timer is not None: _gc._burst_timer.cancel()
    _gc._burst_gen += 1; gen = _gc._burst_gen
    _gc._burst_active = True; _gc._on()
    _gc._seg_colors([(30, 90, 255, _gc.LEFT_MASK | _gc.RIGHT_MASK)])   # blue charge
    def _boom():
        if _gc._burst_gen != gen: return
        _gc._seg_colors([(230, 255, 255, _gc.LEFT_MASK | _gc.RIGHT_MASK)])  # white-cyan crack
        def _afterglow():
            if _gc._burst_gen != gen: return
            _gc._seg_colors([(0, 255, 80, _gc.LEFT_MASK | _gc.RIGHT_MASK)])    # green afterglow
            def _done():
                if _gc._burst_gen != gen: return
                _gc._burst_active = False; _gc._burst_end()
            _gc._burst_timer = threading.Timer(0.20, _done); _gc._burst_timer.start()
        _gc._burst_timer = threading.Timer(0.15, _afterglow); _gc._burst_timer.start()
    _gc._burst_timer = threading.Timer(0.60, _boom); _gc._burst_timer.start()

def _flamethrower_burst():
    if _gc._burst_timer is not None: _gc._burst_timer.cancel()
    _gc._burst_gen += 1; gen = _gc._burst_gen
    _gc._burst_active = True; _gc._on()
    flicker = [
        (255,  80,  0), (255, 160, 20), (255,  55,  0),
        (255, 175, 25), (255,  65,  0), (255, 145, 10),
        (220,  45,  0), (255, 110,  5),
    ]
    def _run_flicker(on_done, speed=1.0):
        _gc._seg_colors([(255, 220, 80, _gc.LEFT_MASK | _gc.RIGHT_MASK)])   # ignition flash
        def _step(n):
            if _gc._burst_gen != gen: return
            if n >= len(flicker):
                on_done(); return
            _gc._seg_colors([(flicker[n][0], flicker[n][1], flicker[n][2], _gc.LEFT_MASK | _gc.RIGHT_MASK)])
            _gc._burst_timer = threading.Timer(0.115 * speed, lambda: _step(n + 1)); _gc._burst_timer.start()
        _gc._burst_timer = threading.Timer(0.08 * speed, lambda: _step(0)); _gc._burst_timer.start()
    def _second():
        if _gc._burst_gen != gen: return
        def _do_gap():
            if _gc._burst_gen != gen: return
            _gc._seg_colors([(20, 5, 0, _gc.LEFT_MASK | _gc.RIGHT_MASK)])   # near-dark gap
            def _start():
                if _gc._burst_gen != gen: return
                def _done():
                    if _gc._burst_gen != gen: return
                    _gc._seg_colors([(150, 18, 0, _gc.LEFT_MASK | _gc.RIGHT_MASK)])  # dying ember
                    def _end():
                        if _gc._burst_gen != gen: return
                        _gc._burst_active = False; _gc._burst_end()
                    _gc._burst_timer = threading.Timer(0.375, _end); _gc._burst_timer.start()
                _run_flicker(_done, speed=1.5)
            _gc._burst_timer = threading.Timer(0.28, _start); _gc._burst_timer.start()
        _gc._burst_timer = threading.Timer(0.10, _do_gap); _gc._burst_timer.start()
    _run_flicker(_second)


def _bio_burst():
    if _gc._burst_timer is not None: _gc._burst_timer.cancel()
    _gc._burst_gen += 1; gen = _gc._burst_gen
    _gc._burst_active = True; _gc._on()
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
        # Phase 2 — low simmer → compression → rapid red/dark finale → fade (6.2s)
        (150,   0,  10, 400),   # lower fire: second squish begins
        (200,   0,  15, 450),   # building
        (230,   5,  15, 350),   # peak
        (175,   0,  12, 300),   # ebb 1
        (230,   5,  15, 350),   # rise 1
        (178,   0,  12, 300),   # ebb 2
        (228,   5,  15, 350),   # rise 2
        (175,   0,  11, 300),   # ebb 3 (slightly dimmer)
        (220,   5,  14, 250),   # rise 3
        ( 15,   0,   3, 200),   # compression beat
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
        if _gc._burst_gen != gen: return
        if n >= len(steps):
            _gc._burst_active = False; _gc._burst_end(); return
        r, g, b, delay = steps[n]
        _gc._seg_colors([(r, g, b, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
        _gc._burst_timer = threading.Timer(delay / 1000.0, lambda: _step(n + 1))
        _gc._burst_timer.start()
    _step(0)


def _rose_pulse_burst():
    if _gc._burst_timer is not None: _gc._burst_timer.cancel()
    _gc._burst_gen += 1
    gen = _gc._burst_gen
    _gc._burst_active = True
    _gc._on()
    steps = [
        (255, 85,  93, 200),
        ( 89, 30,  33, 300),
        (255, 85,  93, 230),
    ]
    def _step(n):
        if _gc._burst_gen != gen: return
        if n >= len(steps):
            _gc._burst_active = False; _gc._burst_end(); return
        r, g, b, delay = steps[n]
        _gc._seg_colors([(r, g, b, _gc.LEFT_MASK | _gc.RIGHT_MASK)])
        _gc._burst_timer = threading.Timer(delay / 1000.0, lambda: _step(n + 1))
        _gc._burst_timer.start()
    _step(0)

SCENES = {
    'off': lambda: (_gc._stop_all(), _gc._off()),
    'police': lambda: _gc._run(_police_loop),
    'club': lambda: _gc._run(_club_loop),
    'flicker': lambda: _gc._run(_flicker_loop, 240, 230, 200),
    'alarm': lambda: _gc._run(_alarm_loop),
    'brave-sea': lambda: _gc._run(_brave_sea_loop),
    'torch-fire': lambda: _gc._run(_torch_fire_loop),
    'evil': lambda: _gc._run(_purple_evil_loop),
    'disian': lambda: _gc._run(_disian_loop),
    'flicker-slow':     lambda: _gc._run(_flicker_loop, 240, 230, 200, 20.0, 45.0, 0.2, 0.5),
    'flicker-pink':        lambda: _gc._run(_flicker_loop, 255, 0, 180, 20.0, 45.0, 0.2, 0.5),
    'neon-motel': lambda: _gc._run(_flicker_split_loop, 0, 60, 255, 160, 0, 255, 4.0, 10.0, 0.06, 0.15),

    'risties': lambda: _gc._run(_risties_deep_loop),
    'rich-district': lambda: _gc._run(_rich_district_loop),
    'corp-lab': lambda: _gc._run(_corp_lab_loop),
    'bus-stop': lambda: _gc._run(_bus_stop_loop),
    'calm-blue':        lambda: _gc._run(_static_loop, 165, 195, 255),
    'draconis':  lambda: _gc._run(_draconis_hb_loop,   80, 200,  10),
    'autodestruct': lambda: _gc._run(_draconis_pulse_loop, 255, 80, 0, 1.8, 0.05, 1.0),
}

BURST_DEFS = {
    'white-burst':    lambda: _gc._fire_burst(255, 255, 255, 0.20),
    'orange-burst':   lambda: _gc._fire_burst(255, 100,   0, 0.30),
    'fire-spark':     lambda: _gc._fire_burst(255, 200,  50, 0.30),
    'blue-spark':     lambda: _gc._fire_burst( 50, 150, 255, 0.30),
    'red-spark':      lambda: _gc._fire_burst(255,  30,  20, 0.30),
    'green-spark':    lambda: _gc._fire_burst(  0, 255,  80, 0.30),
    'smg-burst':      _smg_burst,
    'pulse-rifle':    _pulse_rifle_burst,
    'flamethrower':   _flamethrower_burst,
    'bio-burst':      _bio_burst,
    'rose-pulse':   _rose_pulse_burst,
}
