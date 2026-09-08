import type { ComicRecord } from '../types/comic'

export type SortMode = 'year' | 'az' | 'za'

// A purely numeric issue number ("1", "01", "10") sorts numerically so #2
// comes before #10; anything else (an annual, "16A" variant suffix, etc.)
// keeps its original string. Ported from viewer.html's normalizeIssue.
function normalizeIssue(issue: string | null): string | null {
  if (issue && /^\d+$/.test(issue)) return String(parseInt(issue, 10))
  return issue
}

// Groups by series (falling back to title when there's no series), then
// orders same-series records by issue number — numerically when the issue
// number is a bare integer, so "#2" sorts before "#10" instead of after
// it, matching viewer.html's "Library" sort exactly. `reverseSeries` flips
// only the series/title ordering (for the "za" mode) — issues within a
// series always read #1, #2, #3... in ascending order regardless, since
// reversing that too would browse a series backwards, which isn't what
// the A→Z / Z→A toggle is for.
function compareBySeriesThenIssue(a: ComicRecord, b: ComicRecord, reverseSeries = false): number {
  const sa = (a.series || a.title || '').toLowerCase()
  const sb = (b.series || b.title || '').toLowerCase()
  if (sa !== sb) {
    const cmp = sa < sb ? -1 : 1
    return reverseSeries ? -cmp : cmp
  }

  const ia = normalizeIssue(a.issue_number)
  const ib = normalizeIssue(b.issue_number)
  const na = ia != null && /^\d+$/.test(ia) ? parseInt(ia, 10) : null
  const nb = ib != null && /^\d+$/.test(ib) ? parseInt(ib, 10) : null
  if (na != null && nb != null) return na - nb

  const ta = (a.title || '').toLowerCase()
  const tb = (b.title || '').toLowerCase()
  return ta < tb ? -1 : ta > tb ? 1 : 0
}

export function sortRecords(records: ComicRecord[], mode: SortMode): ComicRecord[] {
  const copy = [...records]
  switch (mode) {
    case 'year':
      return copy.sort((a, b) => (a.year ?? -Infinity) - (b.year ?? -Infinity))
    case 'az':
      return copy.sort((a, b) => compareBySeriesThenIssue(a, b))
    case 'za':
      return copy.sort((a, b) => compareBySeriesThenIssue(a, b, true))
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
