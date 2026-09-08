import { useEffect, useRef } from 'react'
import type { ComicRecord } from '../types/comic'
import { useVirtualizedWindow } from '../hooks/useVirtualizedWindow'
import { CoverCard } from './CoverCard'
import '../styles/shelf.css'

interface CoverShelfProps {
  records: ComicRecord[]
  currentIndex: number
  position: number
  onIndexChange: (index: number) => void
  onSelect: (record: ComicRecord) => void
  onWheel: (deltaX: number, deltaY: number) => void
  onArrowKey: (direction: 1 | -1, isRepeat: boolean) => void
}

export function CoverShelf({
  records,
  currentIndex,
  position,
  onIndexChange,
  onSelect,
  onWheel,
  onArrowKey,
}: CoverShelfProps) {
  // The virtualization window follows the live (possibly mid-fling) position,
  // not just the last settled index, so cards are already mounted by the
  // time the glide reaches them instead of popping in at the end.
  const visibleIndices = useVirtualizedWindow(records.length, Math.round(position), 6)
  const containerRef = useRef<HTMLDivElement>(null)
  const current = records[currentIndex]

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'ArrowRight') {
        e.preventDefault()
        onArrowKey(1, e.repeat)
      } else if (e.key === 'ArrowLeft') {
        e.preventDefault()
        onArrowKey(-1, e.repeat)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onArrowKey])

  return (
    <>
      <div
        ref={containerRef}
        className="stage"
        data-testid="cover-shelf"
        onWheel={(e) => {
          e.preventDefault()
          onWheel(e.deltaX, e.deltaY)
        }}
      >
        <div className="track">
          {visibleIndices.map((i) => {
            const record = records[i]
            // Continuous, possibly-fractional offset from the live physics
            // position — this is what makes the shelf glide frame-by-frame
            // instead of sitting still until the fling settles.
            const offset = i - position
            return (
              <CoverCard
                key={record.id}
                record={record}
                offset={offset}
                onClick={() => (i === currentIndex ? onSelect(record) : onIndexChange(i))}
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
