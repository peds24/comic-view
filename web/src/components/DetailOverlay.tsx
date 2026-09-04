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
    <div data-testid="detail-overlay">
      <button onClick={onClose}>Close</button>
      {record.cover_path && <img src={`/data/covers/${record.cover_path}`} alt={record.title} />}
      <h2>{record.title}</h2>
      {record.series && (
        <div>
          {record.series} {record.issue_number ? `#${record.issue_number}` : ''}
        </div>
      )}
      <div>{record.publisher}</div>
      <div>{record.year}</div>
      <div>{record.status}</div>
      <div>{formatsBadge(record.formats)}</div>
      {record.description && <p>{record.description}</p>}
      {record.preview_pages.length > 0 && (
        <div>
          {record.preview_pages.map((page) => (
            <img key={page} src={`/data/covers/${page}`} alt="" />
          ))}
        </div>
      )}
    </div>
  )
}
