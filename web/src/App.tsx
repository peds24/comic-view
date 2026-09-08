// web/src/App.tsx
import { useMemo, useState } from 'react'
import { useLibrary } from './data/useLibrary'
import { sortRecords, filterByPublisher, type SortMode } from './lib/sort'
import { CoverShelf } from './components/CoverShelf'
import { FilterBar } from './components/FilterBar'
import { SearchBox } from './components/SearchBox'
import { TimelineScrubber } from './components/TimelineScrubber'
import { DetailOverlay } from './components/DetailOverlay'
import { AddItemForm } from './components/admin/AddItemForm'
import type { ComicRecord } from './types/comic'

function BrowsingView() {
  const { records, loading, error } = useLibrary()
  const [sortMode, setSortMode] = useState<SortMode>('year')
  const [publisher, setPublisher] = useState<string | null>(null)
  const [currentIndex, setCurrentIndex] = useState(0)
  const [selected, setSelected] = useState<ComicRecord | null>(null)

  // Manga is temporarily hidden while the shelf is comics-only for now.
  const comics = useMemo(() => records.filter((r) => r.type === 'comic'), [records])

  const visible = useMemo(
    () => sortRecords(filterByPublisher(comics, publisher), sortMode),
    [comics, publisher, sortMode],
  )

  const safeIndex = useMemo(
    () => Math.min(currentIndex, Math.max(0, visible.length - 1)),
    [currentIndex, visible.length],
  )

  if (loading) return <div className="page">Loading…</div>
  if (error) return <div className="page">Error: {error}</div>

  return (
    <div className="page">
      <div className="masthead">
        <div className="wordmark">
          The <span>Longbox</span>
        </div>
        <SearchBox records={visible} onJump={setCurrentIndex} />
        <FilterBar
          records={comics}
          sortMode={sortMode}
          onSortModeChange={setSortMode}
          publisher={publisher}
          onPublisherChange={setPublisher}
        />
      </div>
      <TimelineScrubber
        records={visible}
        currentIndex={safeIndex}
        sortMode={sortMode}
        onScrub={setCurrentIndex}
      />
      <CoverShelf
        records={visible}
        currentIndex={safeIndex}
        onIndexChange={setCurrentIndex}
        onSelect={setSelected}
      />
      {selected && <DetailOverlay record={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}

export default function App() {
  const isAdmin = window.location.pathname === '/admin'
  return isAdmin ? <AddItemForm /> : <BrowsingView />
}
