// web/src/components/DetailOverlay.tsx
import type { ComicRecord } from '../types/comic'

interface DetailOverlayProps {
  record: ComicRecord
  onClose: () => void
}

function formatsBadge(formats: ComicRecord['formats']): string {
  if (formats.includes('digital') && formats.includes('print')) return 'Digital + Physical'
  if (formats.includes('digital')) return 'Digital'
  return 'Physical'
}

export function DetailOverlay({ record, onClose }: DetailOverlayProps) {
  return (
    <div className="detail-backdrop" onClick={onClose}>
      <div data-testid="detail-overlay" className="detail" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose} aria-label="Close">
          ✕
        </button>
        <div className="cover-frame">
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
        <div className="body">
          <h2>{record.title}</h2>
          {record.series && (
            <p className="byline">
              {record.series} {record.issue_number ? `#${record.issue_number}` : ''}
            </p>
          )}
          <div className="factrow">
            {record.publisher && <span className="tag">{record.publisher}</span>}
            {record.year && <span className="tag">{record.year}</span>}
            <span className="tag accent">{formatsBadge(record.formats)}</span>
            <span className="tag">{record.status === 'read' ? 'Read' : 'Unread'}</span>
          </div>
          {record.description && <p className="desc">{record.description}</p>}
          {record.preview_pages.length > 0 && (
            <div className="pages">
              {record.preview_pages.map((page) => (
                <img key={page} src={`/data/covers/${page}`} alt="" />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
