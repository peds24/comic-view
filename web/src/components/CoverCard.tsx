import type { ComicRecord } from '../types/comic'
import { cardTransformStyle } from '../lib/shelfTransform'

interface CoverCardProps {
  record: ComicRecord
  offset: number
  onClick: () => void
}

export function CoverCard({ record, offset, onClick }: CoverCardProps) {
  const focused = offset === 0
  const primaryLine = record.series ?? record.title
  const secondaryLine = record.series && record.issue_number ? `#${record.issue_number}` : ''

  return (
    <button
      type="button"
      className="cover-card"
      data-testid="cover-card"
      data-focused={focused}
      data-status={record.status}
      style={cardTransformStyle(offset) as React.CSSProperties}
      onClick={onClick}
    >
      <div className="art">
        {record.cover_path && (
          <img
            src={`/data/covers/${record.cover_path}`}
            alt={record.title}
            onError={(e) => {
              e.currentTarget.style.display = 'none'
            }}
          />
        )}
      </div>
      <div className="halftone" />
      <div className="status-dot" />
      <div className="plate">
        <div className="series">{primaryLine}</div>
        {secondaryLine && <div className="issue">{secondaryLine}</div>}
      </div>
    </button>
  )
}
