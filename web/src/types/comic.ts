// Mirrors library/models.py's ComicRecord dataclass field-for-field —
// keep the two in sync as the schema evolves.
export type ComicType = 'comic' | 'manga'
export type ReadStatus = 'read' | 'unread'
export type Format = 'digital' | 'print'

export interface ComicRecord {
  id: string
  title: string
  type: ComicType
  series: string | null
  issue_number: string | null
  author: string | null
  year: number | null
  publisher: string | null
  description: string | null
  upc: string | null
  isbn: string | null
  cover_path: string | null
  preview_pages: string[]
  status: ReadStatus
  formats: Format[]
  added_date: string
  metadata_source: Record<string, string>
}
