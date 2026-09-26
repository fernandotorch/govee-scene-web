# Task: Make the trigger library server-side and complete

**Problem.** The "Saved Triggers" panel reads from `localStorage['govee-trigger-library']`. Lights
come from `GET /api/effects` and music from `GET /api/spotify`, both server-side — triggers are
the odd one out. Consequences: the list is per-browser, it is only populated when a session is
saved *in that browser*, and it is never seeded from the sessions on disk. Triggers that exist in
the session files are simply not offerable.

**Fix.** Derive the library on the server from every session file. No curation, no stored state,
nothing to lose: the panel always shows every trigger that exists anywhere.

Two files: `govee_controller.py` and `templates/studio.html`.

---

## Part 1 — govee_controller.py

Add this route next to the `/api/spotify` route:

```python
@app.route("/api/triggers")
def list_triggers():
    """Every trigger across every session, deduped. Derived, never stored — the
    library is always exactly what exists on disk."""
    entries = {}
    for session_path in sorted(glob.glob(os.path.join(SESSIONS_DIR, "*.json"))):
        try:
            with open(session_path) as f:
                data = json.load(f)
        except Exception:
            continue
        manifest = data.get("audio_manifest", {})
        session_label = os.path.splitext(os.path.basename(session_path))[0]
        for scene in data.get("scenes", []):
            for trig in scene.get("triggers", []):
                name = (trig.get("name") or "").strip()
                if not name:
                    continue
                sound = trig.get("sound") or ""
                flash = trig.get("govee_flash") or None
                flash_ref = flash.get("ref") if isinstance(flash, dict) else None
                key = (name.lower(), sound, flash_ref or "")
                entry = entries.get(key)
                if entry is None:
                    audio = None
                    if sound and sound in manifest:
                        info = manifest[sound]
                        rel = info.get("file", "")
                        audio = {
                            "file": rel,
                            "source_name": info.get("source_name") or os.path.basename(rel),
                            "duration_ms": info.get("duration_ms", 0),
                            "missing": not os.path.exists(os.path.join(SFX_DIR, rel)),
                        }
                    entry = entries[key] = {
                        "id": "lib-" + hashlib.md5("|".join(key).encode("utf-8")).hexdigest()[:12],
                        "name": name,
                        "sound": sound,
                        "govee_flash": flash,
                        "audio": audio,
                        "sources": [],
                    }
                if session_label not in entry["sources"]:
                    entry["sources"].append(session_label)
    return jsonify(sorted(entries.values(), key=lambda e: e["name"].lower()))
```

Add `import glob` and `import hashlib` at the top of the file if they are not already there.
`json`, `os`, `SESSIONS_DIR` and `SFX_DIR` are already present.

---

## Part 2 — templates/studio.html

### 2a. Delete the localStorage layer

Delete both functions entirely:

```javascript
function _loadGlobalLibrary() {
  try { return JSON.parse(localStorage.getItem('govee-trigger-library') || '[]'); }
  catch { return []; }
}
function _saveGlobalLibrary() {
  localStorage.setItem('govee-trigger-library', JSON.stringify(triggerLibrary));
}
```

Also delete `_upsertTriggerToLibrary` and `removeLibraryTrigger` entirely — the library is
derived now, so there is nothing to upsert into and nothing to remove from.

### 2b. Add a loader

Where `_loadGlobalLibrary` used to be, add:

```javascript
// ── Trigger library (derived server-side from every session) ─────────────────
async function refreshTriggerLibrary() {
  try {
    const res = await fetch('/api/triggers');
    triggerLibrary = await res.json();
  } catch { triggerLibrary = []; }
  renderTriggerLibrary();
}
```

### 2c. Load it on init

In `init()`, replace:

```javascript
  triggerLibrary = _loadGlobalLibrary();
  renderScenes(); renderExplorer(); renderEffects();
  renderSpotifyList(); renderTriggerLibrary();
```

with:

```javascript
  renderScenes(); renderExplorer(); renderEffects();
  renderSpotifyList(); refreshTriggerLibrary();
```

### 2d. Refresh after a session save instead of harvesting locally

In the save routine, replace:

```javascript
    _dirty = false;
    for (const scene of scenes)
      for (const t of (scene.triggers || []))
        _upsertTriggerToLibrary(t);
    _saveGlobalLibrary();
    renderTriggerLibrary();
    _syncPack();
```

with:

```javascript
    _dirty = false;
    // The server derives the library from the session files, so a save is all
    // it takes for new triggers to appear.
    refreshTriggerLibrary();
    _syncPack();
```

### 2e. Render from server data, drop the remove button

Replace the whole `el.innerHTML = triggerLibrary.map(...)` block in `renderTriggerLibrary` with:

```javascript
  el.innerHTML = triggerLibrary.map(entry => {
    const soundLabel = entry.audio?.source_name || entry.sound || null;
    const flashLabel = entry.govee_flash?.ref
      ? (effects.find(e => e.ref === entry.govee_flash.ref)?.name || entry.govee_flash.ref)
      : null;
    const missing = entry.audio?.missing;
    const meta = [flashLabel, soundLabel].filter(Boolean).join(' · ');
    const title = (entry.sources || []).join(', ');
    return `<div class="tlib-card" style="${missing ? 'opacity:0.5;' : ''}">
      <span class="tlib-name" title="${(entry.name + (title ? ' — used in ' + title : '')).replace(/"/g,'&quot;')}">${missing ? '⚠ ' : ''}${entry.name}</span>
      <span class="tlib-meta" title="${meta.replace(/"/g,'&quot;')}">${meta || '—'}</span>
      <button class="icon" title="Preview trigger" onclick="previewLibraryTrigger('${entry.id}')">▶</button>
      <button class="icon" title="Add to current scene" onclick="applyLibraryTrigger('${entry.id}')">→</button>
    </div>`;
  }).join('');
```

Also change the empty-state message from
`'No triggers yet — save a session to populate the library.'`
to
`'No triggers yet — add one to a scene and save.'`

### 2f. Register the sound when adding a cross-session trigger

This matters: a trigger from another session references a sound the *current* session's manifest
does not know about, so exporting would report it missing. Replace `applyLibraryTrigger` with:

```javascript
function applyLibraryTrigger(libId) {
  if (activeSceneIndex < 0) { alert('Select a scene first.'); return; }
  const entry = triggerLibrary.find(e => e.id === libId);
  if (!entry) return;
  // The sound may come from a different session, so make sure this session's
  // manifest knows about it — otherwise the export reports it missing.
  if (entry.sound && entry.audio && !library[entry.sound]) {
    library[entry.sound] = {
      file: entry.audio.file,
      source_name: entry.audio.source_name,
      duration_ms: entry.audio.duration_ms || 0
    };
  }
  scenes[activeSceneIndex].triggers.push({
    id: `trigger-${Date.now()}`, name: entry.name,
    sound: entry.sound || "", govee_flash: entry.govee_flash || null
  });
  _dirty = true;
  renderEditor();
}
```

### 2g. Make preview work for cross-session sounds

In `previewLibraryTrigger`, replace:

```javascript
  if (entry.sound && library[entry.sound]) {
    const path = library[entry.sound].file;
```

with:

```javascript
  const audioPath = library[entry.sound]?.file || entry.audio?.file;
  if (entry.sound && audioPath) {
    const path = audioPath;
```

Leave the rest of that function as it is.

---

## What must NOT change

- `/api/effects`, `/api/spotify`, `/api/sessions`, `/api/export` and the SFX routes.
- `renderExplorer`, the drag handlers, `_registerAudio`.
- The session save request itself — only the post-save library handling changes.
- `triggerLibrary` stays a module-level array; only where it is filled from changes.

## How to sanity-check

Restart the Flask server first — the new route will not exist until then.

1. `curl -s localhost:5000/api/triggers` lists ten triggers including `pistol`, `auto-fire`,
   `shotgun`, `bloodburst`, each with a `sources` list.
2. Open the Studio in a browser that has never had the trigger library — all ten show up.
3. Open Disruption, select the Emporium scene, click → on `pistol`. It is added, and after
   saving, an export reports no missing files.
4. Click ▶ on a trigger from a session that is not open. It previews.
5. A trigger whose sound file is missing shows dimmed with a ⚠.
