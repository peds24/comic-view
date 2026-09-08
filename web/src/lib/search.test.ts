import { describe, expect, it } from 'vitest'
import { searchRecords } from './search'
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

describe('searchRecords', () => {
  const records = [
    rec({ id: 'a', title: 'Absolute Batman #16', series: 'Absolute Batman' }),
    rec({ id: 'b', title: 'Berserk #1', series: 'Berserk' }),
    rec({ id: 'c', title: 'Attack on Titan 29', series: 'Attack on Titan' }),
  ]

  it('returns empty for a blank query', () => {
    expect(searchRecords(records, '')).toEqual([])
    expect(searchRecords(records, '   ')).toEqual([])
  })

  it('matches by series, case-insensitively', () => {
    const matches = searchRecords(records, 'batman')
    expect(matches).toHaveLength(1)
    expect(matches[0].index).toBe(0)
    expect(matches[0].record.id).toBe('a')
  })

  it('matches by title when series is absent', () => {
    const withNoSeries = [rec({ id: 'd', title: 'Untitled One-Shot', series: null })]
    expect(searchRecords(withNoSeries, 'one-shot')).toHaveLength(1)
  })

  it('returns multiple matches with correct indices', () => {
    const matches = searchRecords(records, 'at')
    const ids = matches.map((m) => m.record.id)
    expect(ids).toEqual(['a', 'c'])
    expect(matches.map((m) => m.index)).toEqual([0, 2])
  })

  it('caps results at the given limit', () => {
    expect(searchRecords(records, 'at', 1)).toHaveLength(1)
  })
})
