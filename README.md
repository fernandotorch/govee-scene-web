# govee-scene-web

Flask Studio for authoring TTRPG session packs for the [govee-scene](https://github.com/fernandotorch/govee-scene) Android app. Author session packs — light effects, Spotify playlists, ambient loops, and trigger sounds — then export a ZIP the phone loads directly.

## Setup

```bash
pip install flask requests
python govee_controller.py
```

Open `http://<laptop-ip>:5000/studio` on any browser. Laptop and phone must be on the same network as the H6047.

**First time:** Enable LAN Control in the Govee app → select your H6047 → Settings → LAN Control → on.

Set your SFX library path in Studio (gear icon) — this is the folder the file browser reads from.

## Studio workflow

### Building a session

1. **Name** your session in the header
2. **Add scenes** — each scene gets:
   - A **Govee effect** (drag from the Effects panel) — previews on the light bar
   - A **Spotify URI** and volume (playlist or album URL)
   - An **ambient loop** (drag an audio file from the SFX browser) and volume
   - **Triggers** — buttons that fire a one-shot sound + optional light flash
3. **Sync** — exports a ZIP to `packs/` and shows any warnings (missing files, oversized audio)
4. **Download on phone** — open Studio Browser in the app, connect to the laptop IP, pick the pack

### SFX browser

- Navigate your SFX library folder tree
- **Drag** a file onto an ambient slot or trigger slot to assign it
- **Click** the play icon to preview; click again to stop
- Supported formats: OGG, WAV, MP3, FLAC, M4A (recommended: OGG or MP3 under 20 MB; non-OGG formats are auto-converted to OGG)

### Burst effects

Light bursts (white, orange, purple) can be previewed from the Bursts panel — click fires a timed flash on the bar without interrupting the current ambient effect. Assign bursts to trigger buttons in the session.

## How it works

### Lighting

The controller discovers the H6047 via UDP multicast (239.255.255.250:4001) and sends commands directly over LAN — no cloud required. Animations run as Python threads; switching scenes stops the current thread cleanly.

Per-segment colour uses the `ptReal` LAN API with base64-encoded 20-byte packets:

```python
LEFT_MASK  = 0x01F   # segments 0-4
RIGHT_MASK = 0x3E0   # segments 5-9
```

Bursts use `ptReal` (not `colorwc`) so they work regardless of which effect is active.

### Session pack export

`POST /api/export` assembles a ZIP containing:
- `session.json` — scenes list, audio manifest, version
- Audio files referenced in the session (flat naming, original format)

Only audio IDs actually used in the session are included. Files over 20 MB are skipped with a warning.

### Flask setup

```
govee_controller.py   ← lighting engine + Studio backend
templates/
  studio.html         ← Studio UI (single-page)
  index.html          ← simple effect switcher (legacy)
effects/              ← JSON effect descriptors
packs/                ← exported session ZIPs
sessions/             ← saved session state (JSON)
```

The server runs with `use_reloader=True, threaded=True` — live-reload on file save, concurrent burst and ambient requests.
