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
