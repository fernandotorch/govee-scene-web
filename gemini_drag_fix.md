# Task: Fix the stuck SFX drag, and stop drag-and-drop from re-encoding library files

Two bugs in the Studio's SFX explorer.

**Bug 1 — the drag never starts and the mouse gets stuck.** `onSfxDragStart` never calls
`e.dataTransfer.setData(...)`. Firefox refuses to begin an HTML5 drag without it, so the
mousedown is consumed but no drag begins and no `dragend` ever fires — the page is left in a
half-dragging state where clicks do nothing.

**Bug 2 — dragging a sound silently re-encodes it.** `onSfxDragStart` calls `_registerAudio`,
which POSTs to `/api/normalize-audio` for any sound not already in the current session. That
endpoint re-encodes the file **in place** at `I=-14` and replaces the original. The library's
ambient beds were deliberately normalized to `-20 LUFS` so they sit under the music; dragging a
bed into a scene silently pushes it back to `-14` and undoes that, one file at a time. The call
is also redundant — `onAmbientDrop` and the trigger drop handler already call `_registerAudio`
themselves.

Two files: `govee_controller.py` and `templates/studio.html`.

---

## Part 1 — govee_controller.py

Add a read-only duration lookup so the Studio can fill in `duration_ms` without re-encoding
anything. Put it directly after the `get_sfx_tree` route:

```python
@app.route("/api/sfx/info")
def get_sfx_info():
    rel_path = request.args.get("path", "")
    full_path = os.path.join(SFX_DIR, rel_path)
    if not os.path.abspath(full_path).startswith(os.path.abspath(SFX_DIR)):
        return jsonify({"error": "unauthorized"}), 403
    if not os.path.exists(full_path):
        return jsonify({"error": "not found"}), 404
    return jsonify({"duration_ms": int((_get_duration(full_path) or 0) * 1000)})
```

Do **not** change `/api/normalize-audio` — it stays available for deliberate use from the
Studio's normalize button. Only the automatic call from drag-and-drop is being removed.

---

## Part 2 — templates/studio.html

### 2a. `_registerAudio` — read the duration instead of re-encoding

Replace the whole function:

```javascript
function _registerAudio(audioId, path) {
  const existing = library[audioId];
  library[audioId] = { file: path, source_name: path.split("/").pop(), duration_ms: existing?.duration_ms ?? 0 };
  if (!existing) {
    fetch("/api/normalize-audio", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path })
    }).then(r => r.json()).then(data => {
      if (data.ok && data.duration_ms) library[audioId].duration_ms = data.duration_ms;
    }).catch(() => {});
  }
}
```

with:

```javascript
function _registerAudio(audioId, path) {
  const existing = library[audioId];
  library[audioId] = { file: path, source_name: path.split("/").pop(), duration_ms: existing?.duration_ms ?? 0 };
  if (!existing) {
    // Read the duration only. This used to POST to /api/normalize-audio, which
    // re-encodes the file in place at I=-14 and undid the -20 LUFS bed targets.
    fetch(`/api/sfx/info?path=${encodeURIComponent(path)}`)
      .then(r => r.json())
      .then(data => {
        if (data.duration_ms) library[audioId].duration_ms = data.duration_ms;
      }).catch(() => {});
  }
}
```

### 2b. `onSfxDragStart` — set drag data, stop registering on drag

Replace:

```javascript
function onSfxDragStart(e, audioId, path) {
  _dragAudioId = audioId; _dragAudioPath = path;
  _registerAudio(audioId, path);
  e.currentTarget.classList.add('dragging-file');
  e.dataTransfer.effectAllowed = 'copy';
}
function onSfxDragEnd(e) { e.currentTarget.classList.remove('dragging-file'); }
```

with:

```javascript
function onSfxDragStart(e, audioId, path) {
  _dragAudioId = audioId; _dragAudioPath = path;
  e.currentTarget.classList.add('dragging-file');
  e.dataTransfer.effectAllowed = 'copy';
  // Firefox will not begin a drag unless dataTransfer carries something. Without
  // this the mousedown is swallowed, no drag starts and no dragend fires, which
  // leaves the pointer stuck.
  try { e.dataTransfer.setData('text/plain', audioId); } catch (_) {}
}
function onSfxDragEnd(e) {
  e.currentTarget.classList.remove('dragging-file');
  // Clear drag state so an aborted drag cannot leak into the next drop.
  _dragAudioId = null; _dragAudioPath = null;
}
```

Registration now happens on drop, where `onAmbientDrop` and the trigger drop handler already
call `_registerAudio` themselves. `onSfxDblClick` keeps its own `_registerAudio` call.

---

## What must NOT change

- `onAmbientDrop`, the trigger sound drop handler, and `onSfxDblClick` — their `_registerAudio`
  calls stay exactly as they are.
- `/api/normalize-audio` in `govee_controller.py`.
- `renderExplorer`, `get_sfx_tree`, and the breadcrumb navigation.
- The effect and Spotify drag handlers — this task is only about the SFX explorer.

## How to sanity-check

1. Click and drag a sound from the SFX panel. The drag starts, the item dims, and the pointer
   behaves normally afterwards — clicks still work.
2. Drag a sound onto a scene's ambient slot and onto a trigger. Both still register and the
   duration appears.
3. Abort a drag by dropping on empty space. The pointer must not stick, and the next drag must
   work.
4. Double-click a sound — still assigns as ambient.
5. Confirm a dragged bed is not re-encoded: `ffmpeg -i <the bed> -af ebur128 -f null -` should
   still report about -20 LUFS after dragging it into a scene, not -14.
