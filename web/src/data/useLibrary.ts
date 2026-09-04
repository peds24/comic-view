import { useEffect, useState } from 'react'
import type { ComicRecord } from '../types/comic'

interface UseLibraryResult {
  records: ComicRecord[]
  loading: boolean
  error: string | null
}

export function useLibrary(): UseLibraryResult {
  const [records, setRecords] = useState<ComicRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    fetch('/data/library.json')
      .then((res) => {
        if (!res.ok) throw new Error(`Failed to load library.json (status ${res.status})`)
        return res.json() as Promise<ComicRecord[]>
      })
      .then((data) => {
        if (!cancelled) setRecords(data)
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [])

  return { records, loading, error }
}
