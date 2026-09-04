// web/src/components/admin/AddItemForm.tsx
import { useState } from 'react'

type ItemType = 'comic' | 'manga'

interface AddResponse {
  ok: boolean
  merged: boolean
  record: { title: string; cover_path: string | null }
}

export function AddItemForm() {
  const [type, setType] = useState<ItemType>('comic')
  const [input, setInput] = useState('')
  const [digital, setDigital] = useState(false)
  const [print, setPrint] = useState(false)
  const [result, setResult] = useState<AddResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const formats = [...(digital ? ['digital'] : []), ...(print ? ['print'] : [])]
  const canSubmit = input.trim().length > 0 && formats.length > 0 && !submitting

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    setResult(null)

    const endpoint = type === 'comic' ? '/api/add-comic' : '/api/add-manga'
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input, formats }),
      })
      const data = await res.json()
      if (!res.ok) {
        setError(data.error ?? `Request failed (status ${res.status})`)
      } else {
        setResult(data)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSubmitting(false)
    }
  }

  const placeholder = type === 'comic' ? 'UPC, ISBN, or League of Comic Geeks link' : 'Title or ISBN'

  return (
    <form onSubmit={handleSubmit}>
      <h1>Add to collection</h1>
      <label>
        <input type="radio" checked={type === 'comic'} onChange={() => setType('comic')} />
        Comic
      </label>
      <label>
        <input type="radio" checked={type === 'manga'} onChange={() => setType('manga')} />
        Manga
      </label>

      <input
        type="text"
        placeholder={placeholder}
        value={input}
        onChange={(e) => setInput(e.target.value)}
      />

      <label>
        <input type="checkbox" checked={digital} onChange={(e) => setDigital(e.target.checked)} />
        Digital
      </label>
      <label>
        <input type="checkbox" checked={print} onChange={(e) => setPrint(e.target.checked)} />
        Physical
      </label>

      <button type="submit" disabled={!canSubmit}>
        {submitting ? 'Adding…' : 'Add'}
      </button>

      {error && <div role="alert">{error}</div>}
      {result && (
        <div>
          {result.merged ? 'Merged into existing record: ' : 'Added: '}
          {result.record.title}
          {result.record.cover_path && <img src={`/data/covers/${result.record.cover_path}`} alt={result.record.title} />}
        </div>
      )}
    </form>
  )
}
