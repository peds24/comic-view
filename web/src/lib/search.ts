import type { ComicRecord } from '../types/comic'

export interface SearchMatch {
  index: number
  record: ComicRecord
}

// Searches by title or series, case-insensitively, over whatever list the
// caller passes — the shelf passes its already-filtered/sorted `visible`
// array, so a match's `index` maps straight onto CoverShelf's currentIndex.
export function searchRecords(records: ComicRecord[], query: string, limit = 8): SearchMatch[] {
  const q = query.trim().toLowerCase()
  if (!q) return []

  const matches: SearchMatch[] = []
  for (let i = 0; i < records.length; i++) {
    const record = records[i]
    const haystack = `${record.title} ${record.series ?? ''}`.toLowerCase()
    if (haystack.includes(q)) {
      matches.push({ index: i, record })
      if (matches.length >= limit) break
    }
  }
  return matches
}
