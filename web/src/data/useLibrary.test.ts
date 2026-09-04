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
