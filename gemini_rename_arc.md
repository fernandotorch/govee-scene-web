# Task: Rename `arc` → `scenes` across govee_controller.py, studio.html, session JSON files, and README.md

The word "arc" was the old name for the list of scenes inside a session pack. Rename it to `scenes` throughout. The JSON key `"arc"` in session files and API payloads also becomes `"scenes"`.

---

## 1. govee_controller.py

Find:
```python
        arc = data.get("arc", []); audio_manifest = data.get("audio_manifest", {})
```
Replace with:
```python
        scenes = data.get("scenes", []); audio_manifest = data.get("audio_manifest", {})
```

Find:
```python
                'arc': arc, 'audio_manifest': audio_manifest
```
Replace with:
```python
                'scenes': scenes, 'audio_manifest': audio_manifest
```

---

## 2. templates/studio.html

### 2a. CSS ID
Find: `#arc-panel { width: 240px; }`
Replace: `#scenes-panel { width: 240px; }`

Find: `/* Arc scene cards */`
Replace: `/* Scene cards */`

### 2b. HTML panel
Find: `<div class="panel" id="arc-panel">`
Replace: `<div class="panel" id="scenes-panel">`

Find: `<h2>Arc</h2>`
Replace: `<h2>Scenes</h2>`

Find: `<div class="panel-content" id="arc-list"></div>`
Replace: `<div class="panel-content" id="scenes-list"></div>`

### 2c. JS variable declaration
Find: `let effects = [], library = {}, arc = [], activeSceneIndex = -1, sessionName = "New Session";`
Replace: `let effects = [], library = {}, scenes = [], activeSceneIndex = -1, sessionName = "New Session";`

Find: `let _dragIndex = null;    // arc scene index being reordered`
Replace: `let _dragIndex = null;    // scene index being reordered`

### 2d. JS comment block
Find: `// ── Arc ───────────────────────────────────────────────────────────────────────`
Replace: `// ── Scenes ──────────────────────────────────────────────────────────────────`

### 2e. JS — use replace_all to rename the `arc` variable in all JS expressions. Replace every occurrence of `arc.` with `scenes.` and every occurrence of `arc[` with `scenes[` and every occurrence of `arc =` with `scenes =` (being careful: only where `arc` is the variable, not part of other words).

More precisely, make these targeted replacements (use replace_all where each pattern is unambiguous):

- `arc.push(` → `scenes.push(`
- `arc.splice(` → `scenes.splice(`
- `arc.length` → `scenes.length`
- `arc.map(` → `scenes.map(`
- `arc[activeSceneIndex]` → `scenes[activeSceneIndex]`
- `for (const scene of arc)` → `for (const scene of scenes)`
- `arc = data.arc` → `scenes = data.scenes`
- `arc = [];` → `scenes = [];`
- `arc, audio_manifest` → `scenes, audio_manifest` (in the save/export fetch body)

### 2f. JS — rename the JSON key in the export body
Find: `body: JSON.stringify({ name: sessionName, arc, audio_manifest: usedLibrary })`
Replace: `body: JSON.stringify({ name: sessionName, scenes, audio_manifest: usedLibrary })`

### 2g. JS — drag handler function references in HTML (inside template literals and event handlers)
Replace all occurrences of `onArcDragStart` → `onScenesDragStart`
Replace all occurrences of `onArcDragOver` → `onScenesDragOver`
Replace all occurrences of `onArcDragLeave` → `onScenesDragLeave`
Replace all occurrences of `onArcDrop` → `onScenesDrop`
Replace all occurrences of `onArcDragEnd` → `onScenesDragEnd`

### 2h. JS — rename the function definitions
Find: `function renderArc()` → `function renderScenes()`
Find: `function onArcDragStart(e, index)` → `function onScenesDragStart(e, index)`
Find: `function onArcDragOver(e)` → `function onScenesDragOver(e)`
Find: `function onArcDragLeave(e)` → `function onScenesDragLeave(e)`
Find: `function onArcDrop(e, targetIndex)` → `function onScenesDrop(e, targetIndex)`
Find: `function onArcDragEnd(e)` → `function onScenesDragEnd(e)`

### 2i. JS — all calls to renderArc()
Replace all occurrences of `renderArc()` → `renderScenes()`

### 2j. JS — getElementById
Find: `document.getElementById('arc-list')` → `document.getElementById('scenes-list')`

---

## 3. Session JSON files

Update the JSON key in both session files. In `sessions/Disruption.json` and `sessions/Hope's Last Day.json`, find the top-level key `"arc"` and rename it to `"scenes"`. Do not change any content inside the array — only the key name.

---

## 4. README.md

Find:
```
Design full arcs — light effects, Spotify playlists, ambient loops, and trigger sounds — then export a ZIP the phone loads directly.
```
Replace with:
```
Author session packs — light effects, Spotify playlists, ambient loops, and trigger sounds — then export a ZIP the phone loads directly.
```

Find:
```
### Building an arc
```
Replace with:
```
### Building a session
```

Find:
```
3. **Sync** — exports a ZIP to `packs/` and shows any warnings (missing files, oversized audio)
```
Leave unchanged.

Find in the "How it works / Session pack export" section:
```
- `session.json` — arc structure, audio manifest, version
```
Replace with:
```
- `session.json` — scenes list, audio manifest, version
```

---

## What must NOT change
- Any effect, trigger, ambient, or Spotify logic
- The `audio_manifest` key — leave it
- All other keys in the JSON files
- The `archive` Python import or any zip-handling code
