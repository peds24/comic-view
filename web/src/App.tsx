// web/src/App.tsx
import { useMemo, useState } from 'react'
import { useLibrary } from './data/useLibrary'
import { sortRecords, filterByPublisher, type SortMode } from './lib/sort'
import { CoverShelf } from './components/CoverShelf'
import { FilterBar } from './components/FilterBar'
import { TimelineScrubber } from './components/TimelineScrubber'
import { DetailOverlay } from './components/DetailOverlay'
import type { ComicRecord } from './types/comic'

function BrowsingView() {
  const { records, loading, error } = useLibrary()
  const [sortMode, setSortMode] = useState<SortMode>('year')
  const [publisher, setPublisher] = useState<string | null>(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [selected, setSelected] = useState<ComicRecord | null>(null)

  const visible = useMemo(
    () => sortRecords(filterByPublisher(records, publisher), sortMode),
    [records, publisher, sortMode],
  )

  if (loading) return <div>Loading…</div>
  if (error) return <div>Error: {error}</div>

  return (
    <div>
      <FilterBar
        records={records}
        sortMode={sortMode}
        onSortModeChange={setSortMode}
        publisher={publisher}
        onPublisherChange={setPublisher}
      />
      <TimelineScrubber
        records={visible}
        currentIndex={currentIndex}
        sortMode={sortMode}
        onScrub={setCurrentIndex}
      />
      <CoverShelf
        records={visible}
        currentIndex={currentIndex}
        onIndexChange={setCurrentIndex}
        onSelect={setSelected}
      />
      {selected && <DetailOverlay record={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

function AdminPlaceholder() {
  // Replaced by the quick-add flow in a follow-up plan.
  return <div>Admin — coming soon</div>
}

export default function App() {
  const isAdmin = window.location.pathname === '/admin'
  return isAdmin ? <AdminPlaceholder /> : <BrowsingView />
}
