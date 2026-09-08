import { useState } from 'react'
import type { ComicRecord } from '../types/comic'
import { searchRecords } from '../lib/search'

interface SearchBoxProps {
  records: ComicRecord[]
  onJump: (index: number) => void
}

export function SearchBox({ records, onJump }: SearchBoxProps) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const matches = searchRecords(records, query)

  function jump(index: number) {
    onJump(index)
    setQuery('')
    setOpen(false)
  }

  return (
    <div className="search-box" data-testid="search-box">
      <input
        type="text"
        placeholder="Jump to a comic…"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') {
            setQuery('')
            setOpen(false)
          } else if (e.key === 'Enter' && matches.length > 0) {
            jump(matches[0].index)
          }
        }}
      />
      {open && query && (
        <ul className="search-results">
          {matches.length > 0 ? (
            matches.map((m) => (
              <li key={m.record.id}>
                <button type="button" onMouseDown={(e) => e.preventDefault()} onClick={() => jump(m.index)}>
                  <span className="r-title">{m.record.series ?? m.record.title}</span>
                  {m.record.year && <span className="r-year">{m.record.year}</span>}
                </button>
              </li>
            ))
          ) : (
            <li className="empty">No matches</li>
          )}
        </ul>
      )}
    </div>
  )
}
