# Task: Stop drop handlers from destroying the drag source before the drag ends

**Evidence.** Driving the real page over the DevTools Protocol, a scene reorder produces:

```
mousedown <- SPAN
dragstart <- item active
dragover  <- SPAN
drop      <- SPAN
mouseup   <- SPAN
```

`dragstart` and `drop` fire. **`dragend` never does.**

**Cause.** `onScenesDrop` calls `renderScenes()` synchronously inside the `drop` handler.
`renderScenes` replaces `scenes-list`'s `innerHTML`, which destroys the element the drag started
from — while the drag is still in progress. With its source node gone, the browser has nothing to
fire `dragend` on, so the drag session is never terminated: the drag image keeps following the
pointer and clicks are swallowed. The page looks frozen even though it is fine.

**Fix.** Mutate the data synchronously, but defer the re-render to the next macrotask so the
browser finishes the drag and fires `dragend` against a node that still exists.

One file: `templates/studio.html`.

---

## Edit 1 — scenes

Replace:

```javascript
function onScenesDrop(e, targetIndex) {
  e.preventDefault(); e.currentTarget.classList.remove('drag-over');
  if (_dragAudioId !== null || _dragEffectRef !== null || _dragSpotifyUri !== null || _dragIndex === null || _dragIndex === targetIndex) return;
  const moved = scenes.splice(_dragIndex, 1)[0];
  scenes.splice(targetIndex, 0, moved);
  activeSceneIndex = targetIndex; _dragIndex = null;
  renderScenes();
}
```

with:

```javascript
function onScenesDrop(e, targetIndex) {
  e.preventDefault(); e.currentTarget.classList.remove('drag-over');
  if (_dragAudioId !== null || _dragEffectRef !== null || _dragSpotifyUri !== null || _dragIndex === null || _dragIndex === targetIndex) return;
  const moved = scenes.splice(_dragIndex, 1)[0];
  scenes.splice(targetIndex, 0, moved);
  activeSceneIndex = targetIndex; _dragIndex = null;
  // Deferred: re-rendering here would destroy the drag source mid-drag, so
  // dragend would never fire and the drag session would never end.
  setTimeout(renderScenes, 0);
}
```

## Edit 2 — ambient drop

Replace:

```javascript
function onAmbientDrop(e) {
  e.preventDefault();
  if (!_dragAudioId) return;
  _registerAudio(_dragAudioId, _dragAudioPath);
  _dirty = true;
  updateScene('ambient', _dragAudioId);
  _dragAudioId = null; _dragAudioPath = null;
  renderEditor();
}
```

with:

```javascript
function onAmbientDrop(e) {
  e.preventDefault();
  if (!_dragAudioId) return;
  _registerAudio(_dragAudioId, _dragAudioPath);
  _dirty = true;
  // updateScene() re-renders, so set the field directly and defer the renders.
  scenes[activeSceneIndex].ambient = _dragAudioId;
  _dragAudioId = null; _dragAudioPath = null;
  setTimeout(() => { renderScenes(); renderEditor(); }, 0);
}
```

## Edit 3 — trigger drop

Replace:

```javascript
function onTriggerDrop(e, index) {
  e.preventDefault();
  if (_dragTriggerIndex !== null && _dragTriggerIndex !== index) {
    const triggers = scenes[activeSceneIndex].triggers;
    const moved = triggers.splice(_dragTriggerIndex, 1)[0];
    triggers.splice(index, 0, moved);
    _dragTriggerIndex = null;
    _dirty = true;
    renderEditor();
    return;
  }
  _dragTriggerIndex = null;
  if (_dragAudioId) {
    _registerAudio(_dragAudioId, _dragAudioPath);
    _dirty = true;
    scenes[activeSceneIndex].triggers[index].sound = _dragAudioId;
    _dragAudioId = null; _dragAudioPath = null;
    renderEditor();
  }
  if (_dragEffectRef) {
    scenes[activeSceneIndex].triggers[index].govee_flash = { ref: _dragEffectRef };
    _dirty = true;
    renderEditor();
  }
}
```

with:

```javascript
function onTriggerDrop(e, index) {
  e.preventDefault();
  // Every re-render below is deferred: doing it inside the drop handler destroys
  // the drag source and the browser never fires dragend.
  if (_dragTriggerIndex !== null && _dragTriggerIndex !== index) {
    const triggers = scenes[activeSceneIndex].triggers;
    const moved = triggers.splice(_dragTriggerIndex, 1)[0];
    triggers.splice(index, 0, moved);
    _dragTriggerIndex = null;
    _dirty = true;
    setTimeout(renderEditor, 0);
    return;
  }
  _dragTriggerIndex = null;
  if (_dragAudioId) {
    _registerAudio(_dragAudioId, _dragAudioPath);
    _dirty = true;
    scenes[activeSceneIndex].triggers[index].sound = _dragAudioId;
    _dragAudioId = null; _dragAudioPath = null;
    setTimeout(renderEditor, 0);
  }
  if (_dragEffectRef) {
    scenes[activeSceneIndex].triggers[index].govee_flash = { ref: _dragEffectRef };
    _dirty = true;
    setTimeout(renderEditor, 0);
  }
}
```

## Edit 4 — a safety net

Even with the above, any future drop handler that re-renders would wedge the pointer again. Add a
document-level guard. Put it immediately after the `_resetDragState` function:

```javascript
// If a drag source is destroyed mid-drag, dragend never fires and the drag state
// would leak. Clear it on drop as well, at the document level.
document.addEventListener('drop', () => setTimeout(_resetDragState, 0), true);
document.addEventListener('dragend', () => _resetDragState(), true);
```

---

## What must NOT change

- `updateScene`, `renderScenes`, `renderEditor`, `renderTriggerCard` themselves.
- The dragstart handlers and `_resetDragState` — those are already correct.
- The `.item` / `#scenes-list` `user-select` CSS added earlier.
- Anything in `govee_controller.py`.

## How to sanity-check

1. Drag a scene onto another scene. It reorders **and the pointer stays usable** — clicking
   another scene immediately afterwards works.
2. With the drag logger armed, the scene reorder now shows `dragend` after `drop`.
3. Drag a sound onto a scene's ambient slot, then immediately click something. No freeze.
4. Reorder two trigger cards, then immediately click. No freeze.
5. Drag an effect onto a trigger, then immediately click. No freeze.
