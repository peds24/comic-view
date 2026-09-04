# Web App Shelf Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold a new `web/` React+TypeScript+Vite app implementing sub-project A's shelf/carousel browsing UI as a working, unstyled component tree — real data flow, focus/detail, sort/filter, scroll physics, and virtualization, with a placeholder `/admin` view that Plan 2 (quick-add) fills in.

**Architecture:** A single-page app with no router library — `App.tsx` reads `window.location.pathname` and renders either the browsing view (`"/"`) or a placeholder admin view (`"/admin"`). The browsing view composes `FilterBar` (sort/filter state) → `useLibrary` (fetched records) → pure `lib/sort.ts` functions (sorted/filtered array) → `CoverShelf` (virtualized, physics-driven focus index) → `DetailOverlay` (on click). Pure logic (sort/filter, virtualization window math, scroll-physics math) lives in plain `.ts` files with Vitest coverage; components are thin wiring around them.

**Tech Stack:** Vite, React 18, TypeScript, Vitest. No CSS framework, no component library, no router library (YAGNI for two routes).

**Spec:** `docs/superpowers/specs/2026-09-04-web-app-and-quick-add-design.md` (Part 1), which itself extends `docs/superpowers/specs/2026-09-02-3d-browsing-ui-design.md`.

## Global Constraints

- No visual styling/CSS this pass — plain unstyled DOM elements throughout (`styles/shelf.css` stays empty).
- `web/` is fully independent of the Python package's toolchain (own `package.json`, own `node_modules`, never imported by `library/`).
- In dev, Vite serves `data/library.json`/`data/covers/**` by proxying to the existing `comic-library serve` server on port 8000 (started separately, by hand, per this plan's manual verification steps) — this plan does not modify any Python file.
- `ComicRecord` fields in `src/types/comic.ts` must mirror `library/models.py`'s `ComicRecord` dataclass field-for-field (see Task 2).
- Only near-focus items render: `currentIndex ± 6` via `useVirtualizedWindow`, regardless of total collection size.

---

### Task 1: Scaffold the Vite React+TS app

**Files:**
- Create: `web/package.json`, `web/tsconfig.json`, `web/tsconfig.node.json`, `web/vite.config.ts`, `web/index.html`, `web/src/main.tsx`, `web/src/App.tsx`, `web/.gitignore`

**Interfaces:**
- Produces: a running dev server at `http://localhost:5173` rendering `<App />`; `vite.config.ts` proxies `/data` and `/api` to `http://127.0.0.1:8000` so later tasks can fetch `/data/library.json` without CORS setup.

- [ ] **Step 1: Scaffold with the official Vite template**

Run from the repo root:

```bash
npm create vite@latest web -- --template react-ts
```

- [ ] **Step 2: Add Vitest**

```bash
cd web && npm install && npm install -D vitest
```

- [ ] **Step 3: Add the `test` script and dev-proxy config**

Edit `web/package.json`, add to `"scripts"`:

```json
"test": "vitest run"
```

Replace the contents of `web/vite.config.ts` with:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/data': 'http://127.0.0.1:8000',
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
```

- [ ] **Step 4: Strip the template's default styling and content**

Replace `web/src/App.tsx` with:

```tsx
export default function App() {
  return <div>web app placeholder</div>
}
```

Delete `web/src/App.css` and `web/src/index.css` if present, and remove their imports from `web/src/main.tsx` and `web/src/App.tsx` (the template imports `./index.css` in `main.tsx` — remove that line too, but keep `main.tsx` otherwise as scaffolded: it mounts `<App />` into `#root`).

- [ ] **Step 5: Verify the dev server and build both work**

```bash
npm run build
```

Expected: builds without error, producing `web/dist/`.

- [ ] **Step 6: Commit**

```bash
git add web/
git commit -m "Scaffold web/ Vite React+TS app"
```

---

### Task 2: `ComicRecord` type mirror + `useLibrary` data hook

**Files:**
- Create: `web/src/types/comic.ts`
- Create: `web/src/data/useLibrary.ts`
- Test: `web/src/data/useLibrary.test.ts`

**Interfaces:**
- Produces: `ComicRecord` type (exported from `types/comic.ts`); `useLibrary(): { records: ComicRecord[]; loading: boolean; error: string | null }` (exported from `data/useLibrary.ts`), fetching `GET /data/library.json`.

- [ ] **Step 1: Write `types/comic.ts`**

```typescript
// Mirrors library/models.py's ComicRecord dataclass field-for-field —
// keep the two in sync as the schema evolves.
export type ComicType = 'comic' | 'manga'
export type ReadStatus = 'read' | 'unread'
export type Format = 'digital' | 'print'

export interface ComicRecord {
  id: string
  title: string
  type: ComicType
  series: string | null
  issue_number: string | null
  author: string | null
  year: number | null
  publisher: string | null
  description: string | null
  upc: string | null
  isbn: string | null
  cover_path: string | null
  preview_pages: string[]
  status: ReadStatus
  formats: Format[]
  added_date: string
  metadata_source: Record<string, string>
}
```

- [ ] **Step 2: Install a testing utility for hooks**

```bash
cd web && npm install -D @testing-library/react @testing-library/jest-dom jsdom
```

Replace the full contents of `web/vite.config.ts` with:

```typescript
/// <reference types="vitest" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/data': 'http://127.0.0.1:8000',
      '/api': 'http://127.0.0.1:8000',
    },
  },
  test: {
    environment: 'jsdom',
  },
})
```

(The triple-slash reference is required for TypeScript to recognize the `test` key on `defineConfig`'s argument — without it, `npm run build`'s type-check fails on an unknown property.)

- [ ] **Step 3: Write the failing test for `useLibrary`**

```typescript
// web/src/data/useLibrary.test.ts
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useLibrary } from './useLibrary'

const sampleRecord = {
  id: 'upc-1', title: 'Absolute Batman #10', type: 'comic', series: 'Absolute Batman',
  issue_number: '10', author: null, year: 2025, publisher: 'DC Comics', description: null,
  upc: '76194138584601011', isbn: null, cover_path: 'upc-1/cover.jpg', preview_pages: [],
  status: 'unread', formats: ['print'], added_date: '2025-07-16', metadata_source: {},
}

describe('useLibrary', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => [sampleRecord],
    })))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('fetches and returns library records', async () => {
    const { result } = renderHook(() => useLibrary())

    expect(result.current.loading).toBe(true)

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.records).toEqual([sampleRecord])
    expect(result.current.error).toBeNull()
    expect(fetch).toHaveBeenCalledWith('/data/library.json')
  })

  it('sets an error message when the fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500 })))

    const { result } = renderHook(() => useLibrary())

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.records).toEqual([])
    expect(result.current.error).toBe('Failed to load library.json (status 500)')
  })
})
```

- [ ] **Step 4: Run test to verify it fails**

```bash
npm run test -- useLibrary
```

Expected: FAIL — `useLibrary` module doesn't exist yet.

- [ ] **Step 5: Implement `useLibrary`**

```typescript
// web/src/data/useLibrary.ts
import { useEffect, useState } from 'react'
import type { ComicRecord } from '../types/comic'

interface UseLibraryResult {
  records: ComicRecord[]
  loading: boolean
  error: string | null
}

export function useLibrary(): UseLibraryResult {
  const [records, setRecords] = useState<ComicRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    fetch('/data/library.json')
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load library.json (status ${res.status})`)
        return res.json() as Promise<ComicRecord[]>
      })
      .then((data) => {
        if (!cancelled) setRecords(data)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  return { records, loading, error }
}
```

- [ ] **Step 6: Run test to verify it passes**

```bash
npm run test -- useLibrary
```

Expected: PASS (2 tests)

- [ ] **Step 7: Commit**

```bash
git add web/src/types/comic.ts web/src/data/useLibrary.ts web/src/data/useLibrary.test.ts web/package.json web/package-lock.json web/vite.config.ts
git commit -m "Add ComicRecord type and useLibrary data hook"
```

---

### Task 3: Pure sort/filter functions (`lib/sort.ts`)

**Files:**
- Create: `web/src/lib/sort.ts`
- Test: `web/src/lib/sort.test.ts`

**Interfaces:**
- Consumes: `ComicRecord` from `types/comic.ts` (Task 2).
- Produces: `SortMode = 'year' | 'az' | 'za'`; `sortRecords(records: ComicRecord[], mode: SortMode): ComicRecord[]`; `filterByPublisher(records: ComicRecord[], publisher: string | null): ComicRecord[]`; `distinctPublishers(records: ComicRecord[]): string[]` (sorted alphabetically, excludes null/empty).

- [ ] **Step 1: Write the failing tests**

```typescript
// web/src/lib/sort.test.ts
import { describe, expect, it } from 'vitest'
import { distinctPublishers, filterByPublisher, sortRecords } from './sort'
import type { ComicRecord } from '../types/comic'

function rec(overrides: Partial<ComicRecord>): ComicRecord {
  return {
    id: 'x', title: 'Title', type: 'comic', series: null, issue_number: null,
    author: null, year: null, publisher: null, description: null, upc: null,
    isbn: null, cover_path: null, preview_pages: [], status: 'unread',
    formats: ['digital'], added_date: '2025-01-01', metadata_source: {},
    ...overrides,
  }
}

describe('sortRecords', () => {
  const records = [
    rec({ id: 'a', title: 'Bravo', year: 2020 }),
    rec({ id: 'b', title: 'Alpha', year: 2022 }),
    rec({ id: 'c', title: 'Charlie', year: 2018 }),
  ]

  it('sorts by year ascending for mode "year"', () => {
    expect(sortRecords(records, 'year').map((r) => r.id)).toEqual(['c', 'a', 'b'])
  })

  it('sorts alphabetically for mode "az"', () => {
    expect(sortRecords(records, 'az').map((r) => r.id)).toEqual(['b', 'a', 'c'])
  })

  it('sorts reverse-alphabetically for mode "za"', () => {
    expect(sortRecords(records, 'za').map((r) => r.id)).toEqual(['c', 'a', 'b'])
  })

  it('treats a null year as oldest in "year" mode', () => {
    const withNull = [...records, rec({ id: 'd', title: 'Delta', year: null })]
    expect(sortRecords(withNull, 'year').map((r) => r.id)).toEqual(['d', 'c', 'a', 'b'])
  })

  it('does not mutate the input array', () => {
    const copy = [...records]
    sortRecords(records, 'az')
    expect(records).toEqual(copy)
  })
})

describe('filterByPublisher', () => {
  const records = [
    rec({ id: 'a', publisher: 'DC Comics' }),
    rec({ id: 'b', publisher: 'Marvel' }),
    rec({ id: 'c', publisher: 'DC Comics' }),
  ]

  it('returns all records when publisher is null', () => {
    expect(filterByPublisher(records, null)).toHaveLength(3)
  })

  it('filters to only the matching publisher', () => {
    expect(filterByPublisher(records, 'DC Comics').map((r) => r.id)).toEqual(['a', 'c'])
  })
})

describe('distinctPublishers', () => {
  it('returns sorted unique non-null publishers', () => {
    const records = [
      rec({ publisher: 'Marvel' }),
      rec({ publisher: 'DC Comics' }),
      rec({ publisher: 'Marvel' }),
      rec({ publisher: null }),
    ]
    expect(distinctPublishers(records)).toEqual(['DC Comics', 'Marvel'])
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm run test -- sort
```

Expected: FAIL — `./sort` module doesn't exist.

- [ ] **Step 3: Implement `lib/sort.ts`**

```typescript
// web/src/lib/sort.ts
import type { ComicRecord } from '../types/comic'

export type SortMode = 'year' | 'az' | 'za'

export function sortRecords(records: ComicRecord[], mode: SortMode): ComicRecord[] {
  const copy = [...records]
  switch (mode) {
    case 'year':
      return copy.sort((a, b) => (a.year ?? -Infinity) - (b.year ?? -Infinity))
    case 'az':
      return copy.sort((a, b) => a.title.localeCompare(b.title))
    case 'za':
      return copy.sort((a, b) => b.title.localeCompare(a.title))
  }
}

export function filterByPublisher(records: ComicRecord[], publisher: string | null): ComicRecord[] {
  if (publisher === null) return records
  return records.filter((r) => r.publisher === publisher)
}

export function distinctPublishers(records: ComicRecord[]): string[] {
  const set = new Set(records.map((r) => r.publisher).filter((p): p is string => !!p))
  return [...set].sort((a, b) => a.localeCompare(b))
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm run test -- sort
```

Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/sort.ts web/src/lib/sort.test.ts
git commit -m "Add pure sort/filter functions for the shelf"
```

---

### Task 4: Virtualization window hook

**Files:**
- Create: `web/src/hooks/useVirtualizedWindow.ts`
- Test: `web/src/hooks/useVirtualizedWindow.test.ts`

**Interfaces:**
- Produces: `useVirtualizedWindow(totalLength: number, currentIndex: number, radius?: number): number[]` — returns the list of indices to render, clamped to `[0, totalLength - 1]`, defaulting `radius` to 6.

- [ ] **Step 1: Write the failing tests**

```typescript
// web/src/hooks/useVirtualizedWindow.test.ts
import { describe, expect, it } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useVirtualizedWindow } from './useVirtualizedWindow'

describe('useVirtualizedWindow', () => {
  it('returns currentIndex plus/minus the radius', () => {
    const { result } = renderHook(() => useVirtualizedWindow(100, 50, 6))
    expect(result.current).toEqual([44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56])
  })

  it('clamps at the start of the list', () => {
    const { result } = renderHook(() => useVirtualizedWindow(100, 2, 6))
    expect(result.current[0]).toBe(0)
    expect(result.current[result.current.length - 1]).toBe(8)
  })

  it('clamps at the end of the list', () => {
    const { result } = renderHook(() => useVirtualizedWindow(10, 8, 6))
    expect(result.current[0]).toBe(2)
    expect(result.current[result.current.length - 1]).toBe(9)
  })

  it('defaults radius to 6', () => {
    const { result } = renderHook(() => useVirtualizedWindow(100, 50))
    expect(result.current).toHaveLength(13)
  })

  it('returns an empty array for an empty list', () => {
    const { result } = renderHook(() => useVirtualizedWindow(0, 0, 6))
    expect(result.current).toEqual([])
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm run test -- useVirtualizedWindow
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement the hook**

```typescript
// web/src/hooks/useVirtualizedWindow.ts
import { useMemo } from 'react'

export function useVirtualizedWindow(totalLength: number, currentIndex: number, radius = 6): number[] {
  return useMemo(() => {
    if (totalLength <= 0) return []
    const start = Math.max(0, currentIndex - radius)
    const end = Math.min(totalLength - 1, currentIndex + radius)
    const indices: number[] = []
    for (let i = start; i <= end; i++) indices.push(i)
    return indices
  }, [totalLength, currentIndex, radius])
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm run test -- useVirtualizedWindow
```

Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add web/src/hooks/useVirtualizedWindow.ts web/src/hooks/useVirtualizedWindow.test.ts
git commit -m "Add useVirtualizedWindow hook"
```

---

### Task 5: Scroll-physics pure functions + hook

**Files:**
- Create: `web/src/hooks/scrollPhysics.ts` (pure math, unit tested)
- Create: `web/src/hooks/useScrollPhysics.ts` (React hook wrapping the math with wheel/touch listeners and a `requestAnimationFrame` loop — exercised manually, not unit tested, per the spec's Vitest-for-pure-logic-only plan)
- Test: `web/src/hooks/scrollPhysics.test.ts`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `stepPhysics(state: { position: number; velocity: number }, friction: number): { position: number; velocity: number }`; `snapToNearest(position: number, itemCount: number): number`; `useScrollPhysics(itemCount: number, onIndexChange: (index: number) => void): { position: number; handleWheel: (deltaY: number) => void }`.

- [ ] **Step 1: Write the failing tests for the pure math**

```typescript
// web/src/hooks/scrollPhysics.test.ts
import { describe, expect, it } from 'vitest'
import { snapToNearest, stepPhysics } from './scrollPhysics'

describe('stepPhysics', () => {
  it('advances position by velocity and decays velocity by friction', () => {
    const next = stepPhysics({ position: 0, velocity: 10 }, 0.9)
    expect(next.position).toBeCloseTo(10)
    expect(next.velocity).toBeCloseTo(9)
  })

  it('zeroes out velocity once it decays below the snap threshold', () => {
    const next = stepPhysics({ position: 0, velocity: 0.005 }, 0.9)
    expect(next.velocity).toBe(0)
  })

  it('applies friction repeatedly toward zero', () => {
    let state = { position: 0, velocity: 100 }
    for (let i = 0; i < 200; i++) state = stepPhysics(state, 0.9)
    expect(state.velocity).toBe(0)
  })
})

describe('snapToNearest', () => {
  it('rounds to the nearest integer index', () => {
    expect(snapToNearest(4.6, 100)).toBe(5)
    expect(snapToNearest(4.4, 100)).toBe(4)
  })

  it('clamps to the valid index range', () => {
    expect(snapToNearest(-3, 100)).toBe(0)
    expect(snapToNearest(500, 100)).toBe(99)
  })

  it('handles a single-item list', () => {
    expect(snapToNearest(5, 1)).toBe(0)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
npm run test -- scrollPhysics
```

Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement the pure math**

```typescript
// web/src/hooks/scrollPhysics.ts
const SNAP_VELOCITY_THRESHOLD = 0.01

export interface PhysicsState {
  position: number
  velocity: number
}

export function stepPhysics(state: PhysicsState, friction: number): PhysicsState {
  const velocity = state.velocity * friction
  const position = state.position + velocity
  return {
    position,
    velocity: Math.abs(velocity) < SNAP_VELOCITY_THRESHOLD ? 0 : velocity,
  }
}

export function snapToNearest(position: number, itemCount: number): number {
  if (itemCount <= 0) return 0
  const rounded = Math.round(position)
  return Math.min(itemCount - 1, Math.max(0, rounded))
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
npm run test -- scrollPhysics
```

Expected: PASS (6 tests)

- [ ] **Step 5: Implement the wrapping hook (no dedicated unit test — wires the math above to DOM events and a rAF loop; covered by manual verification in Task 10)**

```typescript
// web/src/hooks/useScrollPhysics.ts
import { useCallback, useEffect, useRef, useState } from 'react'
import { snapToNearest, stepPhysics, type PhysicsState } from './scrollPhysics'

const FRICTION = 0.92
const WHEEL_TO_VELOCITY = 0.05

export function useScrollPhysics(itemCount: number, onIndexChange: (index: number) => void) {
  const [position, setPosition] = useState(0)
  const stateRef = useRef<PhysicsState>({ position: 0, velocity: 0 })
  const rafRef = useRef<number | null>(null)

  const tick = useCallback(() => {
    stateRef.current = stepPhysics(stateRef.current, FRICTION)
    setPosition(stateRef.current.position)

    if (stateRef.current.velocity === 0) {
      const snapped = snapToNearest(stateRef.current.position, itemCount)
      stateRef.current = { position: snapped, velocity: 0 }
      setPosition(snapped)
      onIndexChange(snapped)
      rafRef.current = null
      return
    }
    rafRef.current = requestAnimationFrame(tick)
  }, [itemCount, onIndexChange])

  const handleWheel = useCallback(
    (deltaY: number) => {
      stateRef.current = { ...stateRef.current, velocity: stateRef.current.velocity + deltaY * WHEEL_TO_VELOCITY }
      if (rafRef.current === null) rafRef.current = requestAnimationFrame(tick)
    },
    [tick],
  )

  useEffect(() => {
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [])

  return { position, handleWheel }
}
```

- [ ] **Step 6: Commit**

```bash
git add web/src/hooks/scrollPhysics.ts web/src/hooks/scrollPhysics.test.ts web/src/hooks/useScrollPhysics.ts
git commit -m "Add scroll-physics math and hook"
```

---

### Task 6: `CoverCard` + `CoverShelf` components

**Files:**
- Create: `web/src/components/CoverCard.tsx`
- Create: `web/src/components/CoverShelf.tsx`

**Interfaces:**
- Consumes: `ComicRecord` (Task 2), `useVirtualizedWindow` (Task 4), `useScrollPhysics` (Task 5).
- Produces: `CoverCard(props: { record: ComicRecord; focused: boolean; onClick: () => void })`; `CoverShelf(props: { records: ComicRecord[]; currentIndex: number; onIndexChange: (i: number) => void; onSelect: (record: ComicRecord) => void })`.

- [ ] **Step 1: Implement `CoverCard.tsx`**

```tsx
// web/src/components/CoverCard.tsx
import type { ComicRecord } from '../types/comic'

interface CoverCardProps {
  record: ComicRecord
  focused: boolean
  onClick: () => void
}

export function CoverCard({ record, focused, onClick }: CoverCardProps) {
  return (
    <div data-testid="cover-card" data-focused={focused} onClick={onClick}>
      {record.cover_path && <img src={`/data/covers/${record.cover_path}`} alt={record.title} />}
      <div>{record.title}</div>
      {focused && (
        <div>
          <div>{record.series ? `${record.series} #${record.issue_number ?? ''}` : record.title}</div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Implement `CoverShelf.tsx`**

```tsx
// web/src/components/CoverShelf.tsx
import { useRef } from 'react'
import type { ComicRecord } from '../types/comic'
import { useVirtualizedWindow } from '../hooks/useVirtualizedWindow'
import { useScrollPhysics } from '../hooks/useScrollPhysics'
import { CoverCard } from './CoverCard'

interface CoverShelfProps {
  records: ComicRecord[]
  currentIndex: number
  onIndexChange: (index: number) => void
  onSelect: (record: ComicRecord) => void
}

export function CoverShelf({ records, currentIndex, onIndexChange, onSelect }: CoverShelfProps) {
  const visibleIndices = useVirtualizedWindow(records.length, currentIndex, 6)
  const { handleWheel } = useScrollPhysics(records.length, onIndexChange)
  const containerRef = useRef<HTMLDivElement>(null)

  return (
    <div
      ref={containerRef}
      data-testid="cover-shelf"
      onWheel={(e) => handleWheel(e.deltaY)}
    >
      <div>
        {currentIndex + 1} of {records.length}
      </div>
      {visibleIndices.map((i) => {
        const record = records[i]
        const focused = i === currentIndex
        return (
          <CoverCard
            key={record.id}
            record={record}
            focused={focused}
            onClick={() => (focused ? onSelect(record) : onIndexChange(i))}
          />
        )
      })}
    </div>
  )
}
```

- [ ] **Step 3: Verify the build still compiles**

```bash
npm run build
```

Expected: no TypeScript errors.

- [ ] **Step 4: Commit**

```bash
git add web/src/components/CoverCard.tsx web/src/components/CoverShelf.tsx
git commit -m "Add CoverCard and CoverShelf components"
```

---

### Task 7: `FilterBar` component

**Files:**
- Create: `web/src/components/FilterBar.tsx`

**Interfaces:**
- Consumes: `SortMode`, `distinctPublishers` (Task 3), `ComicRecord` (Task 2).
- Produces: `FilterBar(props: { records: ComicRecord[]; sortMode: SortMode; onSortModeChange: (m: SortMode) => void; publisher: string | null; onPublisherChange: (p: string | null) => void })`.

- [ ] **Step 1: Implement `FilterBar.tsx`**

```tsx
// web/src/components/FilterBar.tsx
import type { ComicRecord } from '../types/comic'
import { distinctPublishers, type SortMode } from '../lib/sort'

interface FilterBarProps {
  records: ComicRecord[]
  sortMode: SortMode
  onSortModeChange: (mode: SortMode) => void
  publisher: string | null
  onPublisherChange: (publisher: string | null) => void
}

export function FilterBar({ records, sortMode, onSortModeChange, publisher, onPublisherChange }: FilterBarProps) {
  const publishers = distinctPublishers(records)

  return (
    <div data-testid="filter-bar">
      <select value={sortMode} onChange={(e) => onSortModeChange(e.target.value as SortMode)}>
        <option value="year">Year Published</option>
        <option value="az">A → Z</option>
        <option value="za">Z → A</option>
      </select>
      <select value={publisher ?? ''} onChange={(e) => onPublisherChange(e.target.value || null)}>
        <option value="">All publishers</option>
        {publishers.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </select>
    </div>
  )
}
```

- [ ] **Step 2: Verify the build still compiles**

```bash
npm run build
```

- [ ] **Step 3: Commit**

```bash
git add web/src/components/FilterBar.tsx
git commit -m "Add FilterBar component"
```

---

### Task 8: `TimelineScrubber` component

**Files:**
- Create: `web/src/components/TimelineScrubber.tsx`

**Interfaces:**
- Consumes: `ComicRecord`, `SortMode`.
- Produces: `TimelineScrubber(props: { records: ComicRecord[]; currentIndex: number; sortMode: SortMode; onScrub: (index: number) => void })`.

- [ ] **Step 1: Implement `TimelineScrubber.tsx`**

```tsx
// web/src/components/TimelineScrubber.tsx
import type { ComicRecord } from '../types/comic'
import type { SortMode } from '../lib/sort'

interface TimelineScrubberProps {
  records: ComicRecord[]
  currentIndex: number
  sortMode: SortMode
  onScrub: (index: number) => void
}

function currentLabel(records: ComicRecord[], currentIndex: number, sortMode: SortMode): string {
  const current = records[currentIndex]
  if (!current) return ''
  if (sortMode === 'year') return current.year ? String(current.year) : 'Unknown year'
  return current.title.charAt(0).toUpperCase()
}

export function TimelineScrubber({ records, currentIndex, sortMode, onScrub }: TimelineScrubberProps) {
  return (
    <div data-testid="timeline-scrubber">
      <span>{currentLabel(records, currentIndex, sortMode)}</span>
      <input
        type="range"
        min={0}
        max={Math.max(0, records.length - 1)}
        value={currentIndex}
        onChange={(e) => onScrub(Number(e.target.value))}
      />
    </div>
  )
}
```

- [ ] **Step 2: Verify the build still compiles**

```bash
npm run build
```

- [ ] **Step 3: Commit**

```bash
git add web/src/components/TimelineScrubber.tsx
git commit -m "Add TimelineScrubber component"
```

---

### Task 9: `DetailOverlay` component

**Files:**
- Create: `web/src/components/DetailOverlay.tsx`

**Interfaces:**
- Consumes: `ComicRecord`.
- Produces: `DetailOverlay(props: { record: ComicRecord; onClose: () => void })`.

- [ ] **Step 1: Implement `DetailOverlay.tsx`**

```tsx
// web/src/components/DetailOverlay.tsx
import type { ComicRecord } from '../types/comic'

interface DetailOverlayProps {
  record: ComicRecord
  onClose: () => void
}

function formatsBadge(formats: ComicRecord['formats']): string {
  if (formats.includes('digital') && formats.includes('print')) return 'Digital + Physical'
  if (formats.includes('digital')) return 'Digital'
  return 'Physical'
}

export function DetailOverlay({ record, onClose }: DetailOverlayProps) {
  return (
    <div data-testid="detail-overlay">
      <button onClick={onClose}>Close</button>
      {record.cover_path && <img src={`/data/covers/${record.cover_path}`} alt={record.title} />}
      <h2>{record.title}</h2>
      {record.series && (
        <div>
          {record.series} {record.issue_number ? `#${record.issue_number}` : ''}
        </div>
      )}
      <div>{record.publisher}</div>
      <div>{record.year}</div>
      <div>{record.status}</div>
      <div>{formatsBadge(record.formats)}</div>
      {record.description && <p>{record.description}</p>}
      {record.preview_pages.length > 0 && (
        <div>
          {record.preview_pages.map((page) => (
            <img key={page} src={`/data/covers/${page}`} alt="" />
          ))}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Verify the build still compiles**

```bash
npm run build
```

- [ ] **Step 3: Commit**

```bash
git add web/src/components/DetailOverlay.tsx
git commit -m "Add DetailOverlay component"
```

---

### Task 10: Wire `App.tsx` together, add the `/admin` placeholder route, manual verification

**Files:**
- Modify: `web/src/App.tsx`

**Interfaces:**
- Consumes: everything from Tasks 2–9.
- Produces: the assembled browsing view at `/`, and a placeholder `<div>` at `/admin` for Plan 2 to replace.

- [ ] **Step 1: Implement `App.tsx`**

```tsx
// web/src/App.tsx
import { useMemo, useState } from 'react'
import { useLibrary } from './data/useLibrary'
import { sortRecords, filterByPublisher, type SortMode } from './lib/sort'
import { CoverShelf } from './components/CoverShelf'
import { FilterBar } from './components/FilterBar'
import { TimelineScrubber } from './components/TimelineScrubber'
import { DetailOverlay } from './components/DetailOverlay'
import type { ComicRecord } from './types/comic'

function BrowsingView() {
  const { records, loading, error } = useLibrary()
  const [sortMode, setSortMode] = useState<SortMode>('year')
  const [publisher, setPublisher] = useState<string | null>(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [selected, setSelected] = useState<ComicRecord | null>(null)

  const visible = useMemo(
    () => sortRecords(filterByPublisher(records, publisher), sortMode),
    [records, publisher, sortMode],
  )

  if (loading) return <div>Loading…</div>
  if (error) return <div>Error: {error}</div>

  return (
    <div>
      <FilterBar
        records={records}
        sortMode={sortMode}
        onSortModeChange={setSortMode}
        publisher={publisher}
        onPublisherChange={setPublisher}
      />
      <TimelineScrubber
        records={visible}
        currentIndex={currentIndex}
        sortMode={sortMode}
        onScrub={setCurrentIndex}
      />
      <CoverShelf
        records={visible}
        currentIndex={currentIndex}
        onIndexChange={setCurrentIndex}
        onSelect={setSelected}
      />
      {selected && <DetailOverlay record={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

function AdminPlaceholder() {
  // Replaced by the quick-add flow in a follow-up plan.
  return <div>Admin — coming soon</div>
}

export default function App() {
  const isAdmin = window.location.pathname === '/admin'
  return isAdmin ? <AdminPlaceholder /> : <BrowsingView />
}
```

- [ ] **Step 2: Run the full test suite**

```bash
npm run test
```

Expected: all tests pass (from Tasks 2–5).

- [ ] **Step 3: Verify the build compiles**

```bash
npm run build
```

- [ ] **Step 4: Manual verification in headless Chrome via Playwright**

Per the standing instruction (headless Chrome over `claude-in-chrome`), install once if not already:

```bash
npx --yes playwright@1.48.0 install chromium
```

Start the existing Python server in one terminal (serves `data/library.json`):

```bash
comic-library serve --port 8000
```

Start the Vite dev server in another:

```bash
cd web && npm run dev
```

Write a throwaway driver script (e.g. `web/scratch_verify.mjs`) using `playwright` to: navigate to `http://localhost:5173/`, confirm the shelf renders cards, screenshot it, click a focused card to open `DetailOverlay` and screenshot it, change the sort mode and publisher filter and confirm the visible set changes, scroll (dispatch a wheel event) and confirm `currentIndex`'s position counter updates, then navigate to `http://localhost:5173/admin` and confirm the placeholder renders. Delete the script when done (throwaway, not part of the plan's deliverable).

- [ ] **Step 5: Commit**

```bash
git add web/src/App.tsx
git commit -m "Wire shelf browsing view together in App.tsx"
```

## Self-Review Notes

- **Spec coverage:** CoverShelf/CoverCard (Task 6), DetailOverlay (Task 9), TimelineScrubber (Task 8), FilterBar (Task 7), useScrollPhysics (Task 5), useVirtualizedWindow (Task 4) — all six components/hooks from the A spec's file tree are covered. Sort modes + publisher filter (Task 3/7) match the spec's "Year Published / A→Z / Z→A + single-select publisher" requirement. Position counter is in `CoverShelf` (Task 6). Styling, responsive breakpoints, and drag-to-jump-on-timeline are explicitly deferred per this plan's Global Constraints and the spec's "out of scope."
- **Type consistency checked:** `ComicRecord` (Task 2) is used identically in Tasks 3, 6, 7, 8, 9, 10. `SortMode` (Task 3) is used identically in Tasks 7, 8, 10. `useVirtualizedWindow`'s signature (Task 4) matches its call in `CoverShelf` (Task 6). `useScrollPhysics`'s return shape (Task 5) matches its use in `CoverShelf` (Task 6).
