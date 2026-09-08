import { useRef } from 'react'
import type { ComicRecord } from '../types/comic'
import { useVirtualizedWindow } from '../hooks/useVirtualizedWindow'
import { useScrollPhysics } from '../hooks/useScrollPhysics'
import { CoverCard } from './CoverCard'
import '../styles/shelf.css'

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
  const current = records[currentIndex]

  return (
    <>
      <div ref={containerRef} className="stage" data-testid="cover-shelf" onWheel={(e) => handleWheel(e.deltaY)}>
        <div className="track">
          {visibleIndices.map((i) => {
            const record = records[i]
            const offset = i - currentIndex
            return (
              <CoverCard
                key={record.id}
                record={record}
                offset={offset}
                onClick={() => (offset === 0 ? onSelect(record) : onIndexChange(i))}
              />
            )
          })}
        </div>
      </div>

      {current && (
        <div className="shelf-caption">
          <div className="title">{current.series ?? current.title}</div>
          <div className="meta">
            {current.series && current.issue_number && (
              <span className="item">
                <span className="lbl">Issue</span>#{current.issue_number}
              </span>
            )}
            {current.publisher && (
              <span className="item">
                <span className="lbl">Publisher</span>
                {current.publisher}
              </span>
            )}
            {current.year && (
              <span className="item">
                <span className="lbl">Year</span>
                {current.year}
              </span>
            )}
            <span className="item">
              <span className="lbl">Position</span>
              {currentIndex + 1} of {records.length}
            </span>
          </div>
        </div>
      )}
    </>
  )
}
