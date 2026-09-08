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
