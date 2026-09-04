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
  const { handleWheel } = useScrollPhysics(records.length, currentIndex, onIndexChange)
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
