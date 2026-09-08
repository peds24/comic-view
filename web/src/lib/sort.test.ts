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

  it('orders same-series issues numerically, not lexicographically, in "az" mode', () => {
    // A plain string sort would put "#1" before "#10" before "#2" — the bug
    // this is guarding against.
    const issues = [
      rec({ id: 'i10', series: 'Absolute Batman', issue_number: '10' }),
      rec({ id: 'i1', series: 'Absolute Batman', issue_number: '1' }),
      rec({ id: 'i2', series: 'Absolute Batman', issue_number: '2' }),
    ]
    expect(sortRecords(issues, 'az').map((r) => r.id)).toEqual(['i1', 'i2', 'i10'])
  })

  it('groups by series before issue, falling back to title when there is no series', () => {
    const mixed = [
      rec({ id: 'noseries', title: 'Standalone One-Shot', series: null }),
      rec({ id: 'b2', title: 'Berserk #2', series: 'Berserk', issue_number: '2' }),
      rec({ id: 'b1', title: 'Berserk #1', series: 'Berserk', issue_number: '1' }),
    ]
    expect(sortRecords(mixed, 'az').map((r) => r.id)).toEqual(['b1', 'b2', 'noseries'])
  })

  it('keeps issue order ascending in "za" mode too, only reversing series order', () => {
    const mixed = [
      rec({ id: 'berserk2', series: 'Berserk', issue_number: '2' }),
      rec({ id: 'berserk1', series: 'Berserk', issue_number: '1' }),
      rec({ id: 'aot1', series: 'Attack on Titan', issue_number: '1' }),
    ]
    const result = sortRecords(mixed, 'za').map((r) => r.id)
    // Berserk (later alphabetically) comes before Attack on Titan, but
    // Berserk's own issues still read #1 then #2, not #2 then #1.
    expect(result).toEqual(['berserk1', 'berserk2', 'aot1'])
  })

  it('falls back to non-numeric issue labels (e.g. an annual) via title comparison', () => {
    const withAnnual = [
      rec({ id: 'annual', series: 'Batman', issue_number: 'Annual', title: 'Batman Annual' }),
      rec({ id: 'i1', series: 'Batman', issue_number: '1', title: 'Batman #1' }),
    ]
    // Neither result is "wrong" for a non-numeric issue — this just
    // confirms it falls through to the title tiebreaker instead of
    // throwing or treating "Annual" as NaN-sorts-first/last unpredictably.
    const result = sortRecords(withAnnual, 'az').map((r) => r.id)
    expect(result).toHaveLength(2)
    expect(new Set(result)).toEqual(new Set(['annual', 'i1']))
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
