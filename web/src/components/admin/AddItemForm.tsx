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
    <div className="admin-page">
      <form className="admin-frame" onSubmit={handleSubmit}>
        <h1>Add to the longbox</h1>
        <p className="sub">Comics: UPC, ISBN, or a League of Comic Geeks link. Manga: title or ISBN.</p>

        <div className="toggle-row">
          <label className={`toggle${type === 'comic' ? ' active' : ''}`}>
            <input type="radio" name="item-type" checked={type === 'comic'} onChange={() => setType('comic')} />
            Comic
          </label>
          <label className={`toggle${type === 'manga' ? ' active' : ''}`}>
            <input type="radio" name="item-type" checked={type === 'manga'} onChange={() => setType('manga')} />
            Manga
          </label>
        </div>

        <div className="field">
          <label className="sr-only" htmlFor="quick-add-input">
            {placeholder}
          </label>
          <input
            id="quick-add-input"
            type="text"
            placeholder={placeholder}
            value={input}
            onChange={(e) => setInput(e.target.value)}
          />
        </div>

        <div className="check-row">
          <label className={`check${digital ? ' on' : ''}`}>
            <input type="checkbox" checked={digital} onChange={(e) => setDigital(e.target.checked)} />
            <span className="box" />
            Digital
          </label>
          <label className={`check${print ? ' on' : ''}`}>
            <input type="checkbox" checked={print} onChange={(e) => setPrint(e.target.checked)} />
            <span className="box" />
            Physical
          </label>
        </div>

        <button className="submit" type="submit" disabled={!canSubmit}>
          {submitting ? 'Adding…' : 'Add'}
        </button>

        {error && (
          <div className="inline-error" role="alert">
            {error}
          </div>
        )}
        {result && (
          <div className="result-preview">
            {result.record.cover_path && (
              <img src={`/data/covers/${result.record.cover_path}`} alt={result.record.title} />
            )}
            <div className="txt">
              <div>
                <span className="status-word">{result.merged ? 'Merged' : 'Added'}</span> — {result.record.title}
              </div>
              <div className="meta">{formats.join(', ')}</div>
            </div>
          </div>
        )}
      </form>
    </div>
  )
}
