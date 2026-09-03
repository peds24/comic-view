# 3D Browsing UI — Design Spec (Sub-project A of 3)

## Context

The Python side of this project (`library/`, `cli.py`) is complete: `scan`, `enrich`, `import-physical`, and `import-manga-isbn` build a flattened `data/library.json` of 475 comics/manga (digital, physical, or both), each with a cover image and up to 3 extracted/fetched preview pages. That data has no way to be browsed yet beyond a throwaway JSON-reading smoke test (`viewer.html`).

The user wants an explorable UI where comics/manga appear as 3D objects in a horizontal line, angled slightly, with the centered item enlarging to take up most of the screen with full detail — modeled closely on a reference video of **Waxlog** (a vinyl-collection app: records standing in a crate, the focused one enlarged and tilted back showing its top edge, neighbors peeking in at both sides, a position counter, A-Z letter-grouped browsing) found in `/Users/pedrosh/Desktop/comic view inspo/`, alongside several EmulationStation Desktop Edition (ES-DE) coverflow theme screenshots and a working CSS-3D-transform carousel prototype (`gemini-code-*.html`) in the same folder, which validates the lightweight rendering approach chosen below.

Given the scope, the full UI project is split into three independently spec'd/planned/built sub-projects:
- **A (this spec): Core 3D browsing UI** — the shelf/carousel, focus/detail, filters, timeline, scroll physics, responsive behavior. Reads local data directly, read-only.
- **B: Local owner backend + drag-drop upload** — a local-only API server (no public exposure, so no auth needed) wrapping the existing `excel_importer.py`/`isbn_importer.py`/`enrichment.py`/`scanner.py` logic, with a drag-and-drop upload UI for growing the collection from the browser instead of the terminal. Owner-only.
- **C: Public visitor site** — a static "publish" step producing a read-only snapshot (library.json + covers, likely downsized) deployed publicly, so visitors can browse and filter the collection with no login and no write access — solving "I want to show people this project" without exposing any backend.

This spec covers **A only**. B and C are out of scope here and will each get their own design pass once A is built and validated.

## Architecture & data flow

A new `web/` directory holds a React + TypeScript + Vite app, fully independent of the Python package (separate `package.json`, own toolchain). For this sub-project it reads `data/library.json` and `data/covers/**` directly as static files — the Vite dev server is configured to serve the existing `../data` directory at `/data`, so no backend exists yet (that's B). A `src/types/comic.ts` TypeScript type mirrors `ComicRecord` from `library/models.py` field-for-field, so the two stay in sync as the schema evolves; a comment in each file points at its counterpart.

```
web/
  index.html
  vite.config.ts          # dev server: serve ../data at /data
  package.json
  tsconfig.json
  src/
    main.tsx
    App.tsx
    types/comic.ts          # ComicRecord mirror
    data/useLibrary.ts        # fetch + parse /data/library.json
    components/
      CoverShelf.tsx           # the 3D carousel/shelf
      CoverCard.tsx             # one comic's 3D-positioned card
      DetailOverlay.tsx          # full-detail modal on click/tap
      TimelineScrubber.tsx        # top year/letter/publisher indicator
      FilterBar.tsx                 # sort mode + publisher filter controls
    hooks/
      useScrollPhysics.ts      # velocity tracking, inertia, snap-to-item
      useVirtualizedWindow.ts   # renders only currentIndex ± N items
    styles/
      shelf.css                 # perspective/transform CSS
```

## The shelf/carousel

Built as a custom component extending the pattern already proven in the Gemini prototype: a `perspective`-containing stage, with each visible `CoverCard` positioned via `transform: translate3d(x, y, z) rotateY(deg)`, opacity, and blur that fall off with distance from the focused index — receding both left and right (unlike the prototype's one-directional stack) to match the Waxlog reference where neighbors peek in from both sides.

Only items near the current focus are rendered — `currentIndex ± 6` via `useVirtualizedWindow` — regardless of total collection size (475 today, will grow), keeping the DOM light and animation smooth, especially on phones.

**Why custom over a carousel library** (e.g. Swiper's coverflow effect): off-the-shelf coverflow effects don't produce the specific "shelf with visible top-edge depth, symmetric two-sided recession" look from the references, would need heavy CSS overrides anyway, and don't support the velocity/acceleration model described below out of the box. A custom build also fits a portfolio piece better — it's the part worth having full control over.

## Focus & detail — two levels, matching Waxlog

1. **Auto-focus on scroll**: whichever card is centered auto-enlarges to the "focused" size/position (matches the reference's default state). Title, series/issue, and a position counter (e.g. "142 of 475") appear inline beneath it. No click needed to see this much.
2. **Click/tap → detail overlay**: opens `DetailOverlay`, a full-screen modal with the larger cover, the up-to-3 extracted/fetched preview pages (shown as a small strip or swipeable set), description, publisher, year, status (read/unread), and a `formats` badge (Digital / Physical / Digital + Physical). Closes back to the shelf at the same scroll position.

## Scroll acceleration (physics model)

`useScrollPhysics` tracks input velocity from wheel deltas (desktop) and touch drag (mobile) rather than stepping one item per input event (the Gemini prototype's throttled single-step approach). Continuous fast scrolling/swiping builds momentum and skips through many items; as velocity decays (friction-based deceleration), motion slows and **snaps to the nearest item** once velocity drops below a threshold — never leaves the shelf resting between two items. Desktop also supports arrow-key stepping (single-item, no acceleration) as a precise alternative. This is the concrete mechanism behind "acceleration when scrolling so there is greater ease of use."

## Filters & timeline

`FilterBar` offers three **sort modes** — **Year Published**, **A→Z**, **Z→A** (alphabetical by title) — plus an independent **Publisher** filter: a single-select dropdown (built from the distinct `publisher` values present in the library) that narrows the visible set without changing sort mode. Sort mode and publisher filter compose: e.g. "Year Published, filtered to DC Comics." Single-select keeps the first version simple; multi-select is an easy later addition if needed.

`TimelineScrubber`, pinned near the top, is sort-mode-aware:
- **Year Published mode**: shows years passing as you scroll, synced to scroll position (the "timeline... near top of screen as we scroll" ask) — draggable to jump directly to a year.
- **A→Z / Z→A mode**: shows the current letter instead (matching Waxlog's "C — 38 items" grouping).
- Publisher filter active: can show the publisher name/count in the same slot.

## Responsive (phone + desktop)

Same interaction model across viewports; breakpoints adjust:
- Perspective depth and how many neighboring cards are visible/rendered (fewer on narrow screens).
- Touch drag replaces wheel/keyboard as the primary input on phone; both remain available on desktop (trackpad users scroll, not drag).
- `DetailOverlay` layout reflows (stacked on phone, side-by-side cover+text on desktop, matching the Waxlog detail-modal reference).

## Explicitly out of scope for this spec

- Any write path (add/upload) — sub-project B.
- Public deployment, image downsizing/publish pipeline, visitor-vs-owner access split — sub-project C.
- Any change to the Python `library/`/`cli.py` code.

## Verification plan

- **Vitest** for pure logic: scroll-physics math (velocity → target index, deceleration/snap threshold), virtualization window calculation, sort/filter functions — these are easy to get subtly wrong and easy to unit test in isolation from rendering.
- **Manual verification in headless Chrome via Playwright** (per standing instruction — `claude-in-chrome` is unreliable, headless Chrome needs one-time `npx playwright install chromium`): run the dev server against the real 475-record `data/library.json`, screenshot the shelf at rest and mid-scroll, confirm the detail overlay opens with correct data and closes cleanly, confirm all three sort modes and the publisher filter change the visible order/set correctly, confirm the timeline scrubber updates on scroll and is draggable, and confirm the layout holds up at a phone viewport width (e.g. 390px) as well as desktop.
