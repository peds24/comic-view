import type { ComicRecord } from '../types/comic'
import type { SortMode } from '../lib/sort'

interface TimelineScrubberProps {
  records: ComicRecord[]
  currentIndex: number
  sortMode: SortMode
  onScrub: (index: number) => void
}

function currentLabel(records: ComicRecord[], currentIndex: number, sortMode: SortMode): string {
  const current = records[currentIndex]
  if (!current) return ''
  if (sortMode === 'year') return current.year ? String(current.year) : 'Unknown year'
  return current.title.charAt(0).toUpperCase()
}

export function TimelineScrubber({ records, currentIndex, sortMode, onScrub }: TimelineScrubberProps) {
  return (
    <div className="timeline" data-testid="timeline-scrubber">
      <span className="label">{currentLabel(records, currentIndex, sortMode)}</span>
      <input
        type="range"
        min={0}
        max={Math.max(0, records.length - 1)}
        value={currentIndex}
        onChange={(e) => onScrub(Number(e.target.value))}
      />
    </div>
  )
}
