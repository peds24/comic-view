import type { ComicRecord } from '../types/comic'
import type { SortMode } from '../lib/sort'

interface TimelineScrubberProps {
  records: ComicRecord[]
  position: number
  sortMode: SortMode
  onScrub: (index: number) => void
}

function currentLabel(records: ComicRecord[], position: number, sortMode: SortMode): string {
  if (records.length === 0) return ''
  const index = Math.min(records.length - 1, Math.max(0, Math.round(position)))
  const current = records[index]
  if (!current) return ''
  if (sortMode === 'year') return current.year ? String(current.year) : 'Unknown year'
  return current.title.charAt(0).toUpperCase()
}

export function TimelineScrubber({ records, position, sortMode, onScrub }: TimelineScrubberProps) {
  return (
    <div className="timeline" data-testid="timeline-scrubber">
      <span className="label">{currentLabel(records, position, sortMode)}</span>
      <input
        type="range"
        min={0}
        max={Math.max(0, records.length - 1)}
        step="any"
        value={position}
        onChange={(e) => onScrub(Math.round(Number(e.target.value)))}
      />
    </div>
  )
}
