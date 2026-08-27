import { useState } from 'react'
import { TxForm, sendTx, StatusLine } from '../../ui'
import { getContract, GRADE_STATUS } from '../../../chain/contracts'
import { shortAddress, formatError } from '../../../chain/provider'

const ts = (t) => (t ? new Date(Number(t) * 1000).toLocaleString() : '')

export default function ResultsTab({ signer, account }) {
  const [progress, setProgress] = useState(null)
  const [progressError, setProgressError] = useState(null)
  const [progressScript, setProgressScript] = useState('')
  const [trail, setTrail] = useState(null)
  const [trailError, setTrailError] = useState(null)
  const [trailScript, setTrailScript] = useState('')
  const [results, setResults] = useState(null)
  const [resultsError, setResultsError] = useState(null)
  const [resultsExamId, setResultsExamId] = useState('')

  const loadProgress = async (e) => {
    e.preventDefault()
    setProgressError(null)
    setProgress(null)
    try {
      const ra = getContract('ResultAudit')
      const hash = getContract('HashRegistry')
      const p = await ra.getSectionProgress(progressScript, { from: account })
      const examId = Number(await hash.getExamId(progressScript))
      let secTotal = 0
      try {
        secTotal = Number(await getContract('ExamLifecycle').getSectionTotal(examId, Number(p[3])))
      } catch { /* legacy fallback */ }
      setProgress({ ...p, secTotal })
    } catch (err) {
      setProgressError(formatError(err))
    }
  }

  const loadTrail = async (e) => {
    e.preventDefault()
    setTrailError(null)
    setTrail(null)
    try {
      const ra = getContract('ResultAudit')
      const t = await ra.getAuditTrail(trailScript, { from: account })
      setTrail(t)
    } catch (err) {
      setTrailError(formatError(err))
    }
  }

  const loadResults = async (e) => {
    e.preventDefault()
    setResultsError(null)
    setResults(null)
    try {
      const ra = getContract('ResultAudit')
      const finalized = await ra.isExamFinalized(Number(resultsExamId))
      const list = await ra.getExamResults(Number(resultsExamId))
      const hash = getContract('HashRegistry')
      const withSections = await Promise.all(
        list.map(async (s) => ({ sid: s, section: Number(await hash.getScriptSection(s)) }))
      )
      setResults({ finalized, list: withSections })
    } catch (err) {
      setResultsError(formatError(err))
    }
  }

  return (
    <div>
      <div className="grid-2">
        <div>
          <h3>Finalize</h3>
          <TxForm
            title="Finalize exam results (locks marks permanently)"
            fields={[{ name: 'examId', label: 'Exam ID', type: 'number' }]}
            onSubmit={(v) => sendTx(signer, 'ResultAudit', 'finalizeExamResults', Number(v.examId))}
            submitLabel="Finalize (tx)"
          />

          <form className="tx-form" onSubmit={loadProgress}>
            <h4>Script progress — admin only</h4>
            <label className="field">
              <span>Script ID</span>
              <input value={progressScript} onChange={(e) => setProgressScript(e.target.value)} placeholder="SCRIPT_…" />
            </label>
            <button type="submit">Load progress (view)</button>
            <StatusLine result={progressError ? { ok: false, message: progressError } : null} />
            {progress && (
              <div className="lookup-result">
                Section {Number(progress[3])} ·{' '}
                {progress[0] ? 'submitted' : 'not submitted'} ·{' '}
                {Number(progress[1])}/{progress.secTotal} ·{' '}
                {['NOT_SUBMITTED', 'SUBMITTED', 'UNDER_SCRUTINY', 'SCRUTINIZED', 'APPROVED', 'FINALIZED'][Number(progress[2])]}
              </div>
            )}
          </form>
        </div>

        <div>
          <h3>Audit Trail — admin only</h3>
          <form className="tx-form" onSubmit={loadTrail}>
            <label className="field">
              <span>Script ID</span>
              <input value={trailScript} onChange={(e) => setTrailScript(e.target.value)} placeholder="SCRIPT_…" />
            </label>
            <button type="submit">Load trail (view)</button>
            <StatusLine result={trailError ? { ok: false, message: trailError } : null} />
            {trail && (
              <div className="trail">
                {trail.map((e, i) => (
                  <div className="trail-entry" key={i}>
                    <span className="trail-type">{e[5]}</span>
                    <span className="mono-sm">{e[0]} → {e[1]}</span>
                    <span>by {shortAddress(e[3])}</span>
                    <span className="trail-time">{ts(e[2])}</span>
                    <div className="trail-reason">“{e[4]}”</div>
                  </div>
                ))}
              </div>
            )}
          </form>
        </div>
      </div>

      <form className="tx-form" onSubmit={loadResults}>
        <h4>Exam results (admin view)</h4>
        <label className="field">
          <span>Exam ID</span>
          <input type="number" value={resultsExamId} onChange={(e) => setResultsExamId(e.target.value)} />
        </label>
        <button type="submit">Load results (view)</button>
        <StatusLine result={resultsError ? { ok: false, message: resultsError } : null} />
        {results && (
          <div className="lookup-result">
            Finalized: <strong>{results.finalized ? 'YES — marks locked' : 'no'}</strong>
            <ul className="addr-list">
              {results.list.length === 0 && <li>No results yet</li>}
              {results.list.map((s) => (
                <li key={s.sid}>
                  {s.sid} <span className="section-chip">Section {s.section}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </form>
    </div>
  )
}
