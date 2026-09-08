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

  it('clamps a stale currentIndex past the end of a shrunk list instead of returning empty', () => {
    const { result } = renderHook(() => useVirtualizedWindow(5, 40, 6))
    expect(result.current).toEqual([0, 1, 2, 3, 4])
  })
})
