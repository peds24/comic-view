import type { ComicRecord } from '../types/comic'
import { distinctPublishers, type SortMode } from '../lib/sort'

interface FilterBarProps {
  records: ComicRecord[]
  sortMode: SortMode
  onSortModeChange: (mode: SortMode) => void
  publisher: string | null
  onPublisherChange: (publisher: string | null) => void
}

export function FilterBar({ records, sortMode, onSortModeChange, publisher, onPublisherChange }: FilterBarProps) {
  const publishers = distinctPublishers(records)

  return (
    <div data-testid="filter-bar">
      <select value={sortMode} onChange={(e) => onSortModeChange(e.target.value as SortMode)}>
        <option value="year">Year Published</option>
        <option value="az">A → Z</option>
        <option value="za">Z → A</option>
      </select>
      <select value={publisher ?? ''} onChange={(e) => onPublisherChange(e.target.value || null)}>
        <option value="">All publishers</option>
        {publishers.map((p) => (
          <option key={p} value={p}>
            {p}
          </option>
        ))}
      </select>
    </div>
  )
}
