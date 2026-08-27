import { useEffect, useState } from 'react'
import { getContract, EXAM_STATES, SECTION_STATUS, RESCRUTINY_STATUS, ADDRESSES } from '../../chain/contracts'
import { formatError } from '../../chain/provider'
import { TxForm, sendTx } from '../ui'
import { X } from 'lucide-react'

/**
 * Examiner view — SELF-ONLY section visibility + marking/response actions.
 * Only the caller's own section is ever fetched or editable.
 * When a scrutineer sends a section back, this view shows their suggested
 * marks + comment (read from on-chain events) with the UNDER_SCRUTINY status.
 */
export default function ExaminerPage({ signer, account }) {
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
        const total = Number(await exam.getTotalExams())
        const out = []
        for (let id = 1; id <= total; id++) {
          const mySec = Number(await rbac.getMyExamSection(id, { from: account }))
          if (mySec === 0) continue
          const d = await exam.getExamDetails(id)
          let secTotal = 0
          try {
            secTotal = Number(await exam.getSectionTotal(id, mySec))
          } catch { /* legacy fallback */ }
          // Only MY section's scripts (every section is a separate script)
          const scripts = await getContract('HashRegistry').getExamSectionScripts(id, mySec)
          const scriptsRows = []
          for (const sid of scripts) {
            const [, marks, status] = await result.getMySectionMarks(sid, {
              from: account,
            })
            const st = Number(status)
            let scrutiny = null
            if (st === 2 || st === 3) {
              const returns = await result.queryFilter(
                result.filters.ScriptReturnedForScrutiny(sid),
                0,
                'latest'
              )
              const last = returns[returns.length - 1]
              if (last) {
                scrutiny = {
                  suggested: Number(last.args[2]),
                  comment: String(last.args[3]),
                  block: Number(last.blockNumber),
                }
              }
            }
            scriptsRows.push({
              sid,
              marks: Number(marks),
              total: secTotal,
              status: SECTION_STATUS[st],
              scrutiny,
            })
          }
          // Rescrutiny applications for MY section (anonymous — no student)
          const rescrTasks = []
          if (ADDRESSES.Rescrutiny) {
            try {
              const rescr = getContract('Rescrutiny')
              const appCount = Number(await rescr.getExamApplicationCount(id))
            if (appCount > 0) {
              const [sids, sections, statuses, suggestedMarks, revisedMarks] =
                await rescr.getExamApplications(id)
              const [, reasons, comments, examinerNotes] =
                await rescr.getExamApplicationNotes(id)
              for (let i = 0; i < sids.length; i++) {
                if (Number(sections[i]) !== mySec) continue
                rescrTasks.push({
                  sid: sids[i],
                  status: Number(statuses[i]),
                  suggestedMarks: Number(suggestedMarks[i]),
                  revisedMarks: Number(revisedMarks[i]),
                  reason: reasons[i],
                  comment: comments[i],
                  examinerNote: examinerNotes[i],
                })
              }
            }
            } catch { /* Rescrutiny not deployed yet */ }
          }
          out.push({
            id,
            name: d[0],
            state: EXAM_STATES[Number(d[3])],
            section: mySec,
            scripts: scriptsRows,
            rescrTasks,
          })
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
    result.on('SectionMarksSubmitted', handler)
    result.on('MarksUpdatedAfterRescrutiny', handler)
    hash.on('ScriptRegistered', handler)
    if (ADDRESSES.Rescrutiny) {
      const rescr = getContract('Rescrutiny')
      rescr.on('RescrutinyReturned', handler)
      rescr.on('RescrutinyResponded', handler)
      rescr.on('RescrutinyApproved', handler)
      return () => {
        result.off('ScriptReturnedForScrutiny', handler)
        result.off('ScrutinyResponse', handler)
        result.off('SectionMarksSubmitted', handler)
        result.off('MarksUpdatedAfterRescrutiny', handler)
        hash.off('ScriptRegistered', handler)
        rescr.off('RescrutinyReturned', handler)
        rescr.off('RescrutinyResponded', handler)
        rescr.off('RescrutinyApproved', handler)
      }
    }
    return () => {
      result.off('ScriptReturnedForScrutiny', handler)
      result.off('ScrutinyResponse', handler)
      result.off('SectionMarksSubmitted', handler)
      result.off('MarksUpdatedAfterRescrutiny', handler)
      hash.off('ScriptRegistered', handler)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [account])

  if (error) return <div className="error-box"><span className="status-icon"><X size={15} strokeWidth={2.5} aria-hidden="true" /></span>{error}</div>
  if (!rows) return <div className="loading">Loading your section assignments…</div>

  if (rows.length === 0) {
    return (
      <div className="page">
        <h2>Examiner View</h2>
        <div className="info-box">
          You are not assigned as a section examiner for any exam yet.
          The other examiners are never revealed to you.
        </div>
      </div>
    )
  }

  return (
    <div className="page">
      <h2>Examiner View — My Sections Only</h2>
      <p className="hint">
        Reads are self-checks (<code>getMyExamSection</code>,{' '}
        <code>getMySectionMarks</code>) — the other section's marks and the
        other examiner's identity are never fetched. Marking and responding
        are contract-enforced to your own section. When the scrutineer sends
        a section back, their suggested marks and comment appear below with
        the <code>UNDER_SCRUTINY</code> status.
      </p>
      {rows.map((ex) => (
        <div className="card" key={ex.id}>
          <h3>
            Exam {ex.id} — {ex.name}{' '}
            <span className={`state state-${ex.state.toLowerCase()}`}>{ex.state}</span>
            <span className="section-chip">Your section: {ex.section}</span>
          </h3>
          <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Script ID (anonymous)</th>
                <th>Your section marks</th>
                <th>Status</th>
                <th>Scrutinizer's request</th>
              </tr>
            </thead>
            <tbody>
              {ex.scripts.map((s) => (
                <tr key={s.sid}>
                  <td className="mono">{s.sid}</td>
                  <td>{s.marks}/{s.total}</td>
                  <td><span className={`state state-${s.status.toLowerCase()}`}>{s.status}</span></td>
                  <td>
                    {s.scrutiny ? (
                      <span
                        className={
                          s.status === 'UNDER_SCRUTINY'
                            ? 'scrutiny-note scrutiny-pending'
                            : 'scrutiny-note'
                        }
                      >
                        suggested {s.scrutiny.suggested}/{s.total}
                        {s.scrutiny.comment ? ` — “${s.scrutiny.comment}”` : ''}
                        {s.status === 'UNDER_SCRUTINY' && (
                          <span className="feed-block"> · awaiting your response</span>
                        )}
                      </span>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          {ex.rescrTasks.length > 0 && (
            <>
              <h4>Rescrutiny — Your Section</h4>
              <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Script (anonymous)</th>
                    <th>Status</th>
                    <th>Scrutinizer's request</th>
                    <th>Your response</th>
                  </tr>
                </thead>
                <tbody>
                  {ex.rescrTasks.map((app) => {
                    const label = RESCRUTINY_STATUS[app.status] || String(app.status)
                    const pending = app.status === 1
                    return (
                      <tr key={app.sid}>
                        <td className="mono">{app.sid}</td>
                        <td>
                          <span className={`state state-${label.toLowerCase()}`}>{label}</span>
                        </td>
                        <td>
                          <div className="scrutiny-note">Reason: “{app.reason}”</div>
                          {app.status === 1 && (
                            <div className="scrutiny-note scrutiny-pending">
                              returned: suggested {app.suggestedMarks} — “{app.comment}”
                            </div>
                          )}
                          {app.status === 2 && (
                            <div className="scrutiny-note">
                              you revised to {app.revisedMarks} — “{app.examinerNote}” (awaiting
                              scrutinizer approval)
                            </div>
                          )}
                          {app.status === 3 && (
                            <div className="scrutiny-note">approved — re-evaluation done</div>
                          )}
                        </td>
                        <td>
                          {pending ? (
                            <TxForm
                              title="Verify & revise marks"
                              fields={[
                                { name: 'revised', label: `Revised marks /${ex.scripts[0]?.total ?? 50}`, type: 'number', step: '1' },
                                { name: 'note', label: 'Note to scrutinizer' },
                              ]}
                              compact
                              onSubmit={(v) =>
                                sendTx(signer, 'Rescrutiny', 'respondToRescrutiny', app.sid, Number(v.revised), v.note)
                              }
                              submitLabel="Respond (tx)"
                            />
                          ) : (
                            '—'
                          )}
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
              title={`Submit section ${ex.section} marks`}
              fields={[
                { name: 'scriptId', label: 'Script', type: 'select', options: ex.scripts.map((s) => ({ value: s.sid, label: s.sid })) },
                { name: 'marks', label: `Marks /${ex.scripts[0]?.total ?? 50} (section ${ex.section})`, type: 'number', step: '1' },
              ]}
              onSubmit={(v) =>
                sendTx(signer, 'ResultAudit', 'submitMarks', v.scriptId, Number(v.marks))
              }
              submitLabel="Submit marks (tx)"
              compact
            />
            <TxForm
              title="Respond to scrutiny (if pending)"
              fields={[
                { name: 'scriptId', label: 'Script', type: 'select', options: ex.scripts.map((s) => ({ value: s.sid, label: s.sid })) },
                { name: 'revised', label: `Revised marks /${ex.scripts[0]?.total ?? 50}`, type: 'number', step: '1' },
                { name: 'note', label: 'Note to scrutinizer' },
              ]}
              onSubmit={(v) =>
                sendTx(signer, 'ResultAudit', 'respondToScrutiny', v.scriptId, Number(v.revised), v.note)
              }
              submitLabel="Respond (tx)"
              compact
            />
          </div>
        </div>
      ))}
    </div>
  )
}
