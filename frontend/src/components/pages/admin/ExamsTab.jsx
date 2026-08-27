import { useEffect, useState } from 'react'
import { TxForm, sendTx, StatusLine } from '../../ui'
import { getContract, EXAM_STATES, ADDRESSES } from '../../../chain/contracts'
import { shortAddress, formatError } from '../../../chain/provider'
import { RefreshCw, X } from 'lucide-react'

const STATE_OPTIONS = EXAM_STATES.map((s, i) => ({ value: String(i), label: `${s} (${i})` }))

export function ExamRegistryTable({ account }) {
  const [exams, setExams] = useState(null)
  const [error, setError] = useState(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const exam = getContract('ExamLifecycle')
        const hash = getContract('HashRegistry')
        const rbac = getContract('RBAC')
        const total = Number(await exam.getTotalExams())
        const rows = []
        for (let id = 1; id <= total; id++) {
          const d = await exam.getExamDetails(id)
          const term = d[5] ? await exam.getTermName(Number(d[5])) : 'General'
          const [scripts, examiners, scrutinizers] = await Promise.all([
            hash.getExamScripts(id),
            rbac.getExamExaminers(id, { from: account }),
            rbac.getExamScrutinizers(id, { from: account }),
          ])
          rows.push({
            id,
            name: d[0],
            course: d[1],
            state: EXAM_STATES[Number(d[3])] || String(d[3]),
            term,
            totals: d[6].map(String),
            scripts: scripts.length,
            examiners: examiners[0].map((a, i) => ({ addr: a, section: Number(examiners[1][i]) })),
            scrutinizers,
          })
        }
        if (!cancelled) setExams(rows)
      } catch (e) {
        if (!cancelled) setError(formatError(e))
      }
    })()
    return () => { cancelled = true }
  }, [reload])

  if (error) return <div className="error-box"><span className="status-icon"><X size={15} strokeWidth={2.5} aria-hidden="true" /></span>{error}</div>
  if (!exams) return <div className="loading">Loading exams…</div>

  return (
    <div>
      <div className="row-between">
        <h3>Exam Registry (on-chain)</h3>
        <button className="btn-sm" onClick={() => setReload((r) => r + 1)}>
          <RefreshCw size={14} aria-hidden="true" /> Refresh
        </button>
      </div>
      <div className="table-scroll">
      <table className="data-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Exam</th>
            <th>Course</th>
            <th>Term</th>
            <th>Section totals</th>
            <th>State</th>
            <th>Scripts</th>
            <th>Section Examiners</th>
            <th>Scrutinizers</th>
          </tr>
        </thead>
        <tbody>
          {exams.map((ex) => (
            <tr key={ex.id}>
              <td>{ex.id}</td>
              <td>{ex.name}</td>
              <td>{ex.course}</td>
              <td>{ex.term}</td>
              <td>
                {ex.totals.map((t, i) => (
                  <span key={i} className="section-chip">S{i + 1}: {t}</span>
                ))}
              </td>
              <td><span className={`state state-${ex.state.toLowerCase()}`}>{ex.state}</span></td>
              <td>{ex.scripts}</td>
              <td>
                {ex.examiners.length === 0
                  ? '—'
                  : ex.examiners.map((e, i) => (
                      <span key={i} className="section-chip">S{e.section}: {shortAddress(e.addr)}</span>
                    ))}
              </td>
              <td>{ex.scrutinizers.map(shortAddress).join(', ') || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  )
}

export function TermsCard({ signer, onCreated }) {
  const [terms, setTerms] = useState(null)
  const [error, setError] = useState(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const exam = getContract('ExamLifecycle')
        const count = Number(await exam.getTermCount())
        const list = []
        for (let i = 1; i <= count; i++) list.push({ id: i, name: await exam.getTermName(i) })
        if (!cancelled) setTerms(list)
      } catch (e) {
        if (!cancelled) setError(formatError(e))
      }
    })()
    return () => { cancelled = true }
  }, [reload])

  return (
    <div>
      <div className="row-between">
        <h3>Terms (Examination Types)</h3>
        <button className="btn-sm" onClick={() => { setReload((r) => r + 1); onCreated && onCreated() }}>
          <RefreshCw size={14} aria-hidden="true" /> Refresh
        </button>
      </div>
      {error && <div className="error-box"><span className="status-icon"><X size={15} strokeWidth={2.5} aria-hidden="true" /></span>{error}</div>}
      <TxForm
        title="Create term — e.g. “BSc Exam January 2026 Term”, “Supply 2026”"
        fields={[
          { name: 'name', label: 'Term name', initial: 'BSc Exam January 2026 Term' },
        ]}
        onSubmit={async (v) => {
          const res = await sendTx(signer, 'ExamLifecycle', 'createTerm', v.name)
          setReload((r) => r + 1)
          onCreated && onCreated()
          return res
        }}
        submitLabel="Create term (tx)"
      />
      {terms && (
        <ul className="addr-list">
          {terms.length === 0 && <li>No terms yet — create one above, then register courses under it</li>}
          {terms.map((t) => (
            <li key={t.id}><strong>#{t.id}</strong> {t.name}</li>
          ))}
        </ul>
      )}
    </div>
  )
}

/**
 * Exam creation with an ADMIN-DEFINED number of sections (1..10), each with
 * its own total marks. The totals array is passed to createTermExam.
 */
function CreateExamForm({ signer, termOptions }) {
  const [values, setValues] = useState({
    termId: termOptions[0]?.value || '',
    name: 'CSE009 Final Examination',
    courseCode: 'CSE009',
    date: '',
    sectionCount: '2',
  })
  const [totals, setTotals] = useState(['50', '50'])
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  const count = Math.max(1, Math.min(10, Number(values.sectionCount) || 1))
  const set = (name) => (e) => setValues((v) => ({ ...v, [name]: e.target.value }))

  // Keep the selected term in sync with the term list. `termId` is initialized
  // from termOptions only once on mount; if the list loads afterwards (or is
  // empty), the stale '' value would otherwise submit as 0 and revert on-chain
  // with "Invalid term" (createTermExam requires termId > 0).
  useEffect(() => {
    setValues((v) => {
      const realOptions = termOptions.filter((o) => o.value !== '')
      if (realOptions.some((o) => o.value === v.termId)) return v
      return { ...v, termId: realOptions[0]?.value || '' }
    })
  }, [termOptions])

  const run = async (e) => {
    e.preventDefault()
    setBusy(true)
    setResult(null)
    try {
      const termId = Number(values.termId)
      if (!termId) {
        throw new Error('Select a term first — create one in the Terms card if none exist')
      }
      const ts = Math.floor(new Date(values.date + 'T12:00:00').getTime() / 1000)
      const sectionTotals = totals.slice(0, count).map((t) => Number(t))
      if (sectionTotals.some((t) => !Number.isFinite(t) || t <= 0 || t > 1000)) {
        throw new Error('Each section total must be a positive number (max 1000)')
      }
      const msg = await sendTx(
        signer,
        'ExamLifecycle',
        'createTermExam',
        termId,
        values.name,
        values.courseCode,
        ts,
        sectionTotals
      )
      setResult({ ok: true, message: `${msg} · ${count} section(s) created` })
    } catch (err) {
      setResult({ ok: false, message: formatError(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="tx-form" onSubmit={run}>
      <h4>Create term exam — define the number of sections & their totals</h4>
      <label className="field">
        <span>Term</span>
        <select value={values.termId} onChange={set('termId')}>
          {termOptions.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Exam name</span>
        <input value={values.name} onChange={set('name')} required />
      </label>
      <label className="field">
        <span>Course code</span>
        <input value={values.courseCode} onChange={set('courseCode')} required />
      </label>
      <label className="field">
        <span>Exam date</span>
        <input type="date" value={values.date} onChange={set('date')} required />
      </label>
      <label className="field">
        <span>Number of sections (1–10)</span>
        <input
          type="number"
          min="1"
          max="10"
          value={values.sectionCount}
          onChange={(e) => {
            set('sectionCount')(e)
            const n = Math.max(1, Math.min(10, Number(e.target.value) || 1))
            setTotals((t) => Array.from({ length: n }, (_, i) => t[i] ?? '50'))
          }}
          required
        />
      </label>
      <p className="hint">One row per section — each section becomes its own
        anonymous script, marked by its own examiner.</p>
      {totals.slice(0, count).map((t, i) => (
        <label key={i} className="field">
          <span>Section {i + 1} total marks</span>
          <input
            type="number"
            min="1"
            max="1000"
            value={totals[i]}
            onChange={(e) =>
              setTotals((arr) => arr.map((x, j) => (j === i ? e.target.value : x)))
            }
            required
          />
        </label>
      ))}
      <button type="submit" disabled={busy}>
        {busy ? (
          <span className="btn-busy">Sending...</span>
        ) : (
          `Create exam — ${count} section(s) (tx)`
        )}
      </button>
      <StatusLine result={result} />
    </form>
  )
}

export default function ExamsTab({ signer, account }) {
  const [enrolled, setEnrolled] = useState(null)
  const [enrolledError, setEnrolledError] = useState(null)
  const [enrollExamId, setEnrollExamId] = useState('')
  const [terms, setTerms] = useState(null)

  const refreshTerms = async () => {
    try {
      const exam = getContract('ExamLifecycle')
      const count = Number(await exam.getTermCount())
      const list = []
      for (let i = 1; i <= count; i++) list.push({ id: i, name: await exam.getTermName(i) })
      setTerms(list)
    } catch (e) {
      setTerms([])
    }
  }

  useEffect(() => { refreshTerms() }, [])

  const loadEnrolled = async (e) => {
    e.preventDefault()
    setEnrolledError(null)
    setEnrolled(null)
    try {
      const exam = getContract('ExamLifecycle')
      const list = await exam.getEnrolledStudents(Number(enrollExamId), { from: account })
      setEnrolled(list)
    } catch (err) {
      setEnrolledError(formatError(err))
    }
  }

  const termOptions = terms === null
    ? [{ value: '', label: 'Loading terms…' }]
    : terms.length === 0
      ? [{ value: '', label: 'No terms yet — create one in the Terms card first' }]
      : terms.map((t) => ({ value: String(t.id), label: `#${t.id} ${t.name}` }))

  return (
    <div>
      <ExamRegistryTable account={account} />
      <div className="grid-2">
        <div>
          <TermsCard signer={signer} onCreated={refreshTerms} />
        </div>
        <div>
          <h3>Create Course Exam under a Term</h3>
          <CreateExamForm signer={signer} termOptions={termOptions} />
          <TxForm
            title="Update exam state (lifecycle)"
            fields={[
              { name: 'examId', label: 'Exam ID', type: 'number' },
              { name: 'state', label: 'New state', type: 'select', options: STATE_OPTIONS, initial: '2' },
            ]}
            onSubmit={(v) => sendTx(signer, 'ExamLifecycle', 'updateExamState', Number(v.examId), Number(v.state))}
            submitLabel="Update state (tx)"
          />
        </div>
      </div>
      <div className="grid-2">
        <div>
          <h3>Enroll Students</h3>
          <TxForm
            title="Enroll single student (admin override)"
            fields={[
              { name: 'examId', label: 'Exam ID', type: 'number' },
              { name: 'student', label: 'Student address' },
            ]}
            onSubmit={(v) => sendTx(signer, 'ExamLifecycle', 'enrollStudent', Number(v.examId), v.student)}
            submitLabel="Enroll (tx)"
          />
          <TxForm
            title="Enroll batch (one address per line)"
            fields={[
              { name: 'examId', label: 'Exam ID', type: 'number' },
              { name: 'addresses', label: 'Student addresses', type: 'textarea' },
            ]}
            onSubmit={(v) => {
              const addrs = v.addresses.split(/[\n,;]+/).map((s) => s.trim()).filter(Boolean)
              return sendTx(signer, 'ExamLifecycle', 'enrollStudentsBatch', Number(v.examId), addrs)
            }}
            submitLabel="Enroll batch (tx)"
          />
          <form className="tx-form" onSubmit={loadEnrolled}>
            <h4>List enrolled students (view)</h4>
            <label className="field">
              <span>Exam ID</span>
              <input
                type="number"
                value={enrollExamId}
                onChange={(e) => setEnrollExamId(e.target.value)}
              />
            </label>
            <button type="submit">Load enrolled (view)</button>
            <StatusLine result={enrolledError ? { ok: false, message: enrolledError } : null} />
            {enrolled && (
              <ul className="addr-list">
                {enrolled.length === 0 && <li>No students enrolled yet</li>}
                {enrolled.map((a) => (
                  <li key={a}>{shortAddress(a)} <span className="mono-sm">{a}</span></li>
                ))}
              </ul>
            )}
          </form>
        </div>
      </div>
    </div>
  )
}
