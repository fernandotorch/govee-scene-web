# Task: Stop scene rows starting a text selection instead of a drag

**Evidence.** Instrumenting the page shows that pressing a scene row produces
`mousedown` → `selectstart` → `mouseup` → `click`, and **no `dragstart` at all**. A text
selection begins instead of a drag.

**Cause.** `.item` is the only draggable class in the Studio without `user-select: none`.
`.sfx-file` (line 57), `.effect-card` (line 68) and `.spotify-item` (line 117) all set it.
When a press lands on selectable text inside a `draggable="true"` element, the browser starts a
text selection and never initiates the element drag.

One file: `templates/studio.html`. CSS only.

---

## Edit 1 — make scene rows unselectable

Find the `.item` rule:

```css
  .item { background: var(--panel); padding: 10px; margin-bottom: 6px; border-radius: 4px; border: 1px solid transparent; cursor: pointer; }
```

Replace with:

```css
  .item { background: var(--panel); padding: 10px; margin-bottom: 6px; border-radius: 4px; border: 1px solid transparent; cursor: pointer; user-select: none; -webkit-user-select: none; }
```

## Edit 2 — do not let a stray selection survive in the scenes panel

Directly after the `.item.drag-over` rule, add:

```css
  /* The scenes list is also the panel-content element, so a press that misses a
     row lands on the container. Without this a drag gesture there starts a text
     selection that then swallows subsequent clicks. */
  #scenes-list { user-select: none; -webkit-user-select: none; }
```

---

## What must NOT change

- Any JavaScript. This is a CSS-only change.
- The `.item:hover`, `.item.active`, `.item.dragging` and `.item.drag-over` rules themselves.
- `user-select` on `.sfx-file`, `.effect-card`, `.spotify-item` — they are already correct.
- The scene row markup in `renderScenes`, including `draggable`, `onclick` and the drag handlers.

## How to sanity-check

1. Press and drag a scene row. A drag starts (the row dims via `.dragging`), and dropping on
   another row reorders. No text gets highlighted.
2. Clicking a scene still selects it.
3. The `×` delete button on a row still works.
4. With the drag logger armed, pressing a scene row now shows `dragstart` and, on release,
   `dragend` — and no `selectstart`.
