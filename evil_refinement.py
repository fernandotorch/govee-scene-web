def _purple_evil_loop():
    _on(); _bright(100); t = 0.0
    while not _stop.is_set():
        t += 0.3
        packet = []
        
        # SLIGHTLY REDUCED TERROR CHANCE: 6% (was 11%)
        if random.random() < 0.06:
            roll = random.random()
            
            # Weights remain the same (Sequence-heavy)
            if roll < 0.40:
                _seg_colors([(0, 0, 0, LEFT_MASK | RIGHT_MASK)])
                _stop.wait(random.uniform(0.3, 0.6))
                if _stop.is_set(): break
                _seg_colors([(255, 0, 0, LEFT_MASK | RIGHT_MASK)])
                _stop.wait(random.uniform(0.2, 0.4))
                continue
            elif roll < 0.70:
                _seg_colors([(255, 0, 0, LEFT_MASK | RIGHT_MASK)])
                _stop.wait(random.uniform(0.15, 0.3))
                if _stop.is_set(): break
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
