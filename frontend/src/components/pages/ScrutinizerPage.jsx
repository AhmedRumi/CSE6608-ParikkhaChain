import { useEffect, useState } from 'react'
import { getContract, EXAM_STATES, SECTION_STATUS, RESCRUTINY_STATUS, ADDRESSES } from '../../chain/contracts'
import { formatError } from '../../chain/provider'
import { TxForm, sendTx } from '../ui'
import { X } from 'lucide-react'

/**
 * Scrutinizer view — anonymity-first: only the exams this account
 * scrutinizes are listed (self-check). Examiner identities are never shown.
 * Each script is a SINGLE section's answer script (A or B), so it has one
 * marking state derived from on-chain events + getMarks():
 *   NOT_SUBMITTED  — examiner hasn't marked yet
 *   SUBMITTED      — awaiting review
 *   UNDER_SCRUTINY — sent to examiner (shows your suggested marks/comment)
 *   SCRUTINIZED    — examiner responded (shows their revised marks) → can approve
 *   APPROVED       — approved for this script
 */
export default function ScrutinizerPage({ signer, account }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState(null)

  const reload = () => {
    setRows(null)
    setError(null)
    let cancelled = false
    ;(async () => {
      try {
        const exam = getContract('ExamLifecycle')
        const rbac = getContract('RBAC')
        const result = getContract('ResultAudit')
        const rescr = ADDRESSES.Rescrutiny ? getContract('Rescrutiny') : null
        const total = Number(await exam.getTotalExams())
        const out = []
        for (let id = 1; id <= total; id++) {
          const isScrut = await rbac.isScrutinizerForExam(id, { from: account })
          if (!isScrut) continue
          const d = await exam.getExamDetails(id)
          const hash = getContract('HashRegistry')
          const scripts = await hash.getExamScripts(id)
          const scriptRows = []
          for (const sid of scripts) {
            const [marksV, secTotal, stRaw] = await result.getMarks(sid)
            const st = Number(stRaw)
            const state = SECTION_STATUS[st] || 'FINALIZED'
            let detail = null
            if (st === 2 || st === 3) {
              const [returns, responses, rejects] = await Promise.all([
                result.queryFilter(result.filters.ScriptReturnedForScrutiny(sid), 0, 'latest'),
                result.queryFilter(result.filters.ScrutinyResponse(sid), 0, 'latest'),
                result.queryFilter(result.filters.ScrutinyRejected(sid), 0, 'latest'),
              ])
              if (st === 3) {
                const lastRes = responses[responses.length - 1]
                if (lastRes) detail = `examiner revised to ${Number(lastRes.args[3])}/${secTotal}`
              } else {
                const lastRej = rejects[rejects.length - 1]
                const lastRet = returns[returns.length - 1]
                if (lastRej && (!lastRet || lastRej.blockNumber >= lastRet.blockNumber)) {
                  detail = `rejected — “${String(lastRej.args[2])}”`
                } else if (lastRet) {
                  detail = `sent: suggested ${Number(lastRet.args[2])}/${secTotal} — “${String(lastRet.args[3])}”`
                }
              }
            }
            scriptRows.push({
              sid,
              section: Number(await hash.getScriptSection(sid)),
              marks: Number(marksV),
              secTotal: Number(secTotal),
              state,
              detail,
            })
          }
          // Rescrutiny applications for this exam (anonymous — no student)
          const rescrApplications = []
          if (rescr) {
            try {
              const appCount = Number(await rescr.getExamApplicationCount(id))
            if (appCount > 0) {
              const [sids, sections, statuses, suggestedMarks, revisedMarks, finalMarks] =
                await rescr.getExamApplications(id)
              const [, reasons, comments, examinerNotes, appliedAt, resolvedAt] =
                await rescr.getExamApplicationNotes(id)
              for (let i = 0; i < sids.length; i++) {
                rescrApplications.push({
                  sid: sids[i],
                  section: Number(sections[i]),
                  status: Number(statuses[i]),
                  suggestedMarks: Number(suggestedMarks[i]),
                  revisedMarks: Number(revisedMarks[i]),
                  finalMarks: Number(finalMarks[i]),
                  reason: reasons[i],
                  comment: comments[i],
                  examinerNote: examinerNotes[i],
                  appliedAt: Number(appliedAt[i]),
                  resolvedAt: Number(resolvedAt[i]),
                })
              }
            }
            } catch { /* Rescrutiny not deployed yet */ }
          }
          out.push({ id, name: d[0], state: EXAM_STATES[Number(d[3])], scripts: scriptRows, rescrutiny: rescrApplications })
        }
        if (!cancelled) setRows(out)
      } catch (e) {
        if (!cancelled) setError(formatError(e))
      }
    })()
    return () => { cancelled = true }
  }

  useEffect(reload, [account])

  useEffect(() => {
    if (!account) return
    const result = getContract('ResultAudit')
    const hash = getContract('HashRegistry')
    const handler = () => reload()
    result.on('ScriptReturnedForScrutiny', handler)
    result.on('ScrutinyResponse', handler)
    result.on('ScrutinyApproved', handler)
    result.on('ScrutinyRejected', handler)
    result.on('SectionMarksSubmitted', handler)
    result.on('MarksUpdatedAfterRescrutiny', handler)
    hash.on('ScriptRegistered', handler)
    if (ADDRESSES.Rescrutiny) {
      const rescr = getContract('Rescrutiny')
      rescr.on('RescrutinyApplied', handler)
      rescr.on('RescrutinyReturned', handler)
      rescr.on('RescrutinyResponded', handler)
      rescr.on('RescrutinyApproved', handler)
      return () => {
        result.off('ScriptReturnedForScrutiny', handler)
        result.off('ScrutinyResponse', handler)
        result.off('ScrutinyApproved', handler)
        result.off('ScrutinyRejected', handler)
        result.off('SectionMarksSubmitted', handler)
        result.off('MarksUpdatedAfterRescrutiny', handler)
        hash.off('ScriptRegistered', handler)
        rescr.off('RescrutinyApplied', handler)
        rescr.off('RescrutinyReturned', handler)
        rescr.off('RescrutinyResponded', handler)
        rescr.off('RescrutinyApproved', handler)
      }
    }
    return () => {
      result.off('ScriptReturnedForScrutiny', handler)
      result.off('ScrutinyResponse', handler)
      result.off('ScrutinyApproved', handler)
      result.off('ScrutinyRejected', handler)
      result.off('SectionMarksSubmitted', handler)
      result.off('MarksUpdatedAfterRescrutiny', handler)
      hash.off('ScriptRegistered', handler)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account])

  if (error) return <div className="error-box"><span className="status-icon"><X size={15} strokeWidth={2.5} aria-hidden="true" /></span>{error}</div>
  if (!rows) return <div className="loading">Loading your scrutiny assignments…</div>

  if (rows.length === 0) {
    return (
      <div className="page">
        <h2>Scrutinizer View</h2>
        <div className="info-box">
          You are not assigned as a scrutinizer for any exam yet.
        </div>
      </div>
    )
  }

  const scriptOptions = (ex) => ex.scripts.map((s) => ({ value: s.sid, label: s.sid }))

  return (
    <div className="page">
      <h2>Scrutinizer View — Anonymous Script Queue</h2>
      <p className="hint">
        Scripts are anonymized. Every section is a <strong>separate
        script</strong>, each marked by its own examiner — you review scripts,
        not people, and examiner identities stay hidden until the reveal step.
        If the submitted marks are fine, <strong>approve directly</strong>;
        otherwise send the script to its examiner with suggested marks and a
        comment, then approve once the examiner responds.
      </p>
      {rows.map((ex) => (
        <div className="card" key={ex.id}>
          <h3>
            Exam {ex.id} — {ex.name}{' '}
            <span className={`state state-${ex.state.toLowerCase()}`}>{ex.state}</span>
            <span className="section-chip">{ex.scripts.length} scripts</span>
          </h3>
          <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Script ID (anonymous)</th>
                <th>Section</th>
                <th>Marks</th>
                <th>State</th>
              </tr>
            </thead>
            <tbody>
              {ex.scripts.map((s) => (
                <tr key={s.sid}>
                  <td className="mono">{s.sid}</td>
                  <td><span className="section-chip">Section {s.section}</span></td>
                  <td>{s.marks}/{s.secTotal}</td>
                  <td>
                    <span className={`state state-${s.state.toLowerCase()}`}>{s.state}</span>
                    {s.detail && <div className="scrutiny-note">{s.detail}</div>}
                    {s.state === 'SCRUTINIZED' && (
                      <div className="feed-block">ready to approve</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          {ex.rescrutiny.length > 0 && (
            <>
              <h4>Rescrutiny Applications (re-evaluation)</h4>
              <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Script (anonymous)</th>
                    <th>Section</th>
                    <th>Status</th>
                    <th>Details</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {ex.rescrutiny.map((app) => {
                    const label = RESCRUTINY_STATUS[app.status] || String(app.status)
                    return (
                      <tr key={app.sid}>
                        <td className="mono">{app.sid}</td>
                        <td><span className="section-chip">Section {app.section}</span></td>
                        <td>
                          <span className={`state state-${label.toLowerCase()}`}>{label}</span>
                        </td>
                        <td>
                          <div className="scrutiny-note">Reason: “{app.reason}”</div>
                          {app.status === 1 && (
                            <div className="scrutiny-note">
                              returned: suggested {app.suggestedMarks} — “{app.comment}”
                            </div>
                          )}
                          {app.status === 2 && (
                            <div className="scrutiny-note">
                              examiner revised to {app.revisedMarks} — “{app.examinerNote}”
                            </div>
                          )}
                          {app.status === 3 && (
                            <div className="scrutiny-note">approved — final marks {app.finalMarks}</div>
                          )}
                        </td>
                        <td>
                          <RescrutinyActions app={app} signer={signer} />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              </div>
            </>
          )}
          <div className="grid-2">
            <TxForm
              title="Send to examiner (return for scrutiny)"
              fields={[
                { name: 'scriptId', label: 'Script', type: 'select', options: scriptOptions(ex) },
                { name: 'suggested', label: 'Suggested marks', type: 'number', step: '1' },
                { name: 'comment', label: 'Comment' },
              ]}
              onSubmit={(v) =>
                sendTx(signer, 'ResultAudit', 'returnScriptForScrutiny', v.scriptId, Number(v.suggested), v.comment)
              }
              submitLabel="Send to examiner (tx)"
              compact
            />
            <TxForm
              title="Approve marks"
              fields={[
                { name: 'scriptId', label: 'Script', type: 'select', options: scriptOptions(ex) },
              ]}
              onSubmit={(v) =>
                sendTx(signer, 'ResultAudit', 'approveScrutiny', v.scriptId)
              }
              submitLabel="Approve (tx)"
              compact
            />
          </div>
        </div>
      ))}
    </div>
  )
}

/**
 * Rescrutiny actions for one application (scrutinizer side).
 * APPLIED  → approve directly (marks unchanged) OR return to that section's
 *            examiner with suggested marks + comment.
 * REVISED  → examiner responded; scrutinizer approves (marks get written).
 * RETURNED → waiting for the examiner; APPROVED → done.
 */
function RescrutinyActions({ app, signer }) {
  if (app.status === 0) {
    return (
      <div className="rescrutiny-form">
        <TxForm
          title="No issue → approve directly"
          fields={[{ name: 'comment', label: 'Comment' }]}
          compact
          onSubmit={(v) => sendTx(signer, 'Rescrutiny', 'approveDirectly', app.sid, v.comment)}
          submitLabel="Approve (tx)"
        />
        <TxForm
          title="Issue found → return to examiner"
          fields={[
            { name: 'suggested', label: 'Suggested marks', type: 'number', step: '1' },
            { name: 'comment', label: 'Comment' },
          ]}
          compact
          onSubmit={(v) =>
            sendTx(signer, 'Rescrutiny', 'returnForRescrutiny', app.sid, Number(v.suggested), v.comment)
          }
          submitLabel="Return (tx)"
        />
      </div>
    )
  }
  if (app.status === 2) {
    return (
      <TxForm
        title="Approve after revision"
        fields={[{ name: 'comment', label: 'Comment' }]}
        compact
        onSubmit={(v) => sendTx(signer, 'Rescrutiny', 'approveAfterRevision', app.sid, v.comment)}
        submitLabel="Approve revised (tx)"
      />
    )
  }
  return null
}
