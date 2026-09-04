import type { ComicRecord } from '../types/comic'

interface CoverCardProps {
  record: ComicRecord
  focused: boolean
  onClick: () => void
}

export function CoverCard({ record, focused, onClick }: CoverCardProps) {
  return (
    <div data-testid="cover-card" data-focused={focused} onClick={onClick}>
      {record.cover_path && <img src={`/data/covers/${record.cover_path}`} alt={record.title} />}
      <div>{record.title}</div>
      {focused && (
        <div>
          <div>{record.series ? `${record.series} #${record.issue_number ?? ''}` : record.title}</div>
        </div>
      )}
    </div>
  )
}
