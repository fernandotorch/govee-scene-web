# Task: Fix the remaining stuck drags (scenes, effects, playlists, trigger cards)

The SFX explorer's drag was fixed by adding `dataTransfer.setData()`. The Studio has four other
draggable types and **none of them call `setData`**, so they all have the same defect.

**Why it sticks.** Firefox refuses to begin an HTML5 drag unless `dataTransfer` carries data. The
mousedown is consumed, no drag begins, and — critically — **no `dragend` ever fires**.

**Why it then stays broken.** Every panel keeps its own module-level drag variable, and each one
is cleared in its `dragend` handler. When `dragend` never fires, that variable stays set forever.
`onScenesDragOver` and `onScenesDrop` both bail out early if `_dragEffectRef` or `_dragSpotifyUri`
is non-null:

```javascript
if (_dragAudioId !== null || _dragEffectRef !== null || _dragSpotifyUri !== null) return;
```

So one half-failed effect or playlist drag silently disables scene reordering for the rest of the
page's life. That is the "stuck when I try to move a scene up and down" symptom: the scene drag
itself is also broken, and even after fixing it, stale state from an earlier failed drag would
keep refusing the drop.

Fix both halves: give every drag source `setData`, and have every drag start from a known-clean
state.

One file: `templates/studio.html`.

---

## Edit 1 — add a drag-state reset helper

Next to the drag variable declarations (`_dragAudioId`, `_dragAudioPath`, `_dragIndex`,
`_dragTriggerIndex`, `_dragEffectRef`, `_dragSpotifyUri`), add:

```javascript
// Every drag source clears all drag state before setting its own. Without this,
// a drag that failed to start leaves its variable set and silently blocks the
// scene reorder drop checks for the rest of the session.
function _resetDragState() {
  _dragAudioId = null; _dragAudioPath = null; _dragIndex = null;
  _dragTriggerIndex = null; _dragEffectRef = null; _dragSpotifyUri = null;
}
```

## Edit 2 — scenes

Replace:

```javascript
function onScenesDragStart(e, index) {
  _dragIndex = index; _dragAudioId = null;
  e.currentTarget.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
}
```

with:

```javascript
function onScenesDragStart(e, index) {
  _resetDragState();
  _dragIndex = index;
  e.currentTarget.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  try { e.dataTransfer.setData('text/plain', 'scene:' + index); } catch (_) {}
}
```

And replace:

```javascript
function onScenesDragEnd(e) { e.currentTarget.classList.remove('dragging'); _dragIndex = null; }
```

with:

```javascript
function onScenesDragEnd(e) {
  e.currentTarget.classList.remove('dragging');
  document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
  _dragIndex = null;
}
```

## Edit 3 — effects

Replace:

```javascript
function onEffectDragStart(e, ref) {
  _dragEffectRef = ref; _dragAudioId = null;
  e.currentTarget.classList.add('dragging-file');
  e.dataTransfer.effectAllowed = 'copy';
}
```

with:

```javascript
function onEffectDragStart(e, ref) {
  _resetDragState();
  _dragEffectRef = ref;
  e.currentTarget.classList.add('dragging-file');
  e.dataTransfer.effectAllowed = 'copy';
  try { e.dataTransfer.setData('text/plain', 'effect:' + ref); } catch (_) {}
}
```

## Edit 4 — Spotify playlists

This handler currently receives the element, not the event, so it has no way to reach
`dataTransfer`. Change the signature and the markup together.

Replace:

```javascript
function onSpotifyDragStart(el) { _dragSpotifyUri = el.dataset.uri; el.classList.add('dragging-spotify'); }
```

with:

```javascript
function onSpotifyDragStart(e, el) {
  _resetDragState();
  _dragSpotifyUri = el.dataset.uri;
  el.classList.add('dragging-spotify');
  e.dataTransfer.effectAllowed = 'copy';
  try { e.dataTransfer.setData('text/plain', el.dataset.uri); } catch (_) {}
}
```

In `renderSpotifyList`, update the call site. Replace:

```
         ondragstart="onSpotifyDragStart(this)" ondragend="onSpotifyDragEnd()"
```

with:

```
         ondragstart="onSpotifyDragStart(event, this)" ondragend="onSpotifyDragEnd()"
```

Leave `onSpotifyDragEnd` as it is — it already clears `_dragSpotifyUri`.

## Edit 5 — trigger cards

In `renderTriggerCard`, replace the `ondragstart` attribute:

```
         ondragstart="_dragTriggerIndex=${i}; _dragAudioId=null; _dragEffectRef=null; this.classList.add('dragging');"
```

with:

```
         ondragstart="_resetDragState(); _dragTriggerIndex=${i}; this.classList.add('dragging'); event.dataTransfer.effectAllowed='move'; try{event.dataTransfer.setData('text/plain','trigger:${i}');}catch(_){}"
```

Leave the `ondragend`, `ondragover`, `ondragleave` and `ondrop` attributes on that element exactly
as they are.

## Edit 6 — SFX explorer, for consistency

`onSfxDragStart` already calls `setData`. Add the reset so it matches the others. Replace:

```javascript
function onSfxDragStart(e, audioId, path) {
  _dragAudioId = audioId; _dragAudioPath = path;
```

with:

```javascript
function onSfxDragStart(e, audioId, path) {
  _resetDragState();
  _dragAudioId = audioId; _dragAudioPath = path;
```

Leave the rest of that function, and `onSfxDragEnd`, unchanged.

---

## What must NOT change

- `onScenesDragOver`, `onScenesDragLeave`, `onScenesDrop` — their guard conditions stay as they
  are. They are correct; they were being fed stale state.
- `onTriggerDrop`, `onAmbientDrop`, `_registerAudio`, `onSfxDblClick`.
- `onSpotifyDragEnd`, `onEffectDragEnd`, and the trigger card's `ondragend`.
- Anything in `govee_controller.py`. This is a front-end-only change.

## How to sanity-check

Hard-refresh the Studio after restarting Flask.

1. Drag a scene up and down in the list. It reorders, and the pointer behaves normally after.
2. Drag an effect onto a scene, then immediately try to reorder scenes. Reordering still works —
   this is the case that was permanently broken before.
3. Same with a Spotify playlist: drag one, then reorder scenes.
4. Start a drag of each type and drop it on empty space. After each aborted drag, scene
   reordering must still work.
5. Reorder trigger cards within a scene.
6. SFX drag onto an ambient slot and onto a trigger still works.
