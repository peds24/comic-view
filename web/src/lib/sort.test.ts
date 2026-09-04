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
