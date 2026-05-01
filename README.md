# govee-scene-web

Flask-based testing lab for designing Govee H6047 RGBIC lighting effects. Run on a laptop, control from your phone browser. Effects developed here get ported to the [govee-scene](https://github.com/fernandotorch/govee-scene) Android app.

## Setup

```bash
pip install flask
python govee_controller.py
```

Open the URL printed in the terminal on your phone. Laptop and phone must be on the same Wi-Fi network as the light bar.

**First time:** Enable LAN Control in the Govee app → select your H6047 → Settings → LAN Control → on.

## How it works

The script discovers the H6047 via UDP multicast (239.255.255.250:4001), then sends commands directly over LAN — no cloud required. Animations run as Python threads; switching scenes stops the current thread cleanly before starting the next.

The web UI auto-reloads when you save the file, so you can edit effects and see them live without restarting.

## Scenes

| Scene | Effect |
|---|---|
| **Police Siren** | Red / blue per-segment rotation at ~2 Hz |
| **Emergency Alarm** | Orange per-segment rotating beacon |
| **Techno Club** | Hot pink & neon green strobe with irregular timing |
| **Flickering Light** | Organic damaged fluorescent — random brightness/timing |
| **Disian Encounter** | Deep purple sine-wave pulse with cold white intrusions |

## Adding a new effect

1. Write a `_your_effect_loop()` function following the existing pattern
2. Add it to the `SCENES` dict and the HTML button list
3. Test from the phone browser
4. When happy, port the logic to `govee-scene` (Dart)

## Per-segment control

The H6047 has 10 physical segments — 5 per bar. Segment control uses the `ptReal` LAN API command with base64-encoded 20-byte BLE packets:

```python
LEFT_MASK  = 0x01F   # segments 0-4
RIGHT_MASK = 0x3E0   # segments 5-9
```

Swap these constants if your bars feel reversed.
