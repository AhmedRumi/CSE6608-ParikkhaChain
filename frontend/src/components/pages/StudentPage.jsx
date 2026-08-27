import { useEffect, useState } from 'react'
import { jsPDF } from 'jspdf'
import autoTable from 'jspdf-autotable'
import { sendTx } from '../ui'
import { getContract, GRADE_STATUS, EXAM_STATES, RESCRUTINY_STATUS } from '../../chain/contracts'
import { formatError, shortAddress } from '../../chain/provider'
import { ArrowLeft, Check, Download, LockKeyhole, Search, X } from 'lucide-react'

/**
 * Grading scale (percentage out of 100 per exam) — adjustable.
 * Per-course marks = SUM of the student's section scripts. Each exam has an
 * admin-defined number of sections (1..10), each with its own total
 * (ExamLifecycle.getSectionTotal / getSectionCount).
 */
const GRADE_TABLE = [
  { min: 80, grade: 'A+', point: 4.0 },
  { min: 75, grade: 'A',  point: 3.8 },
  { min: 70, grade: 'A-', point: 3.5 },
  { min: 65, grade: 'B+', point: 3.2 },
  { min: 60, grade: 'B',  point: 3.0 },
  { min: 55, grade: 'B-', point: 2.7 },
  { min: 50, grade: 'C+', point: 2.3 },
  { min: 45, grade: 'C',  point: 2.0 },
  { min: 40, grade: 'D',  point: 1.0 },
  { min: 0,  grade: 'F',  point: 0.0 },
]

export function gradeOf(marks) {
  for (const g of GRADE_TABLE) if (marks >= g.min) return g
  return GRADE_TABLE[GRADE_TABLE.length - 1]
}

/** Grade from raw marks against a custom exam total (percentage-based). */
export function gradeFor(marks, totalMax) {
  if (!totalMax) return gradeOf(marks)
  return gradeOf(Math.round((marks * 100) / totalMax))
}
const GRADED = ['APPROVED', 'FINALIZED']
const GRADED_IDX = [4, 5]

/**
 * Student view — only the caller's OWN results (contract-enforced via
 * onlyAdminOrSelf in getFullTranscript / getStudentExamResult).
 * - Students register for offered courses themselves (registerForCourse,
 *   auto-enrollment; admin can still override).
 * - Results are LOCKED until the admin marks the exam COMPLETED AND every
 *   registered course's marks are APPROVED (contract-enforced:
 *   getFullTranscript reverts while any course is pending). The UI mirrors
 *   the same rule via public getters.
 * - NOT_SUBMITTED rows are never shown.
 * Per-section marks are derived from PUBLIC on-chain events
 * (SectionMarksSubmitted / ScrutinyResponse), so no admin getters are used.
 */
export default function StudentPage({ account, signer }) {
  const [offered, setOffered] = useState(null)
  const [terms, setTerms] = useState(null)
  const [selectedTerm, setSelectedTerm] = useState(null)
  const [enrolled, setEnrolled] = useState([])
  const [rows, setRows] = useState(null)
  const [locked, setLocked] = useState(false)
  const [lockPending, setLockPending] = useState([])
  const [hasScripts, setHasScripts] = useState(false)
  const [rescrutiny, setRescrutiny] = useState({})
  const [applyForm, setApplyForm] = useState(null)
  const [reasonDraft, setReasonDraft] = useState('')
  const [error, setError] = useState(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const exam = getContract('ExamLifecycle')
        const hash = getContract('HashRegistry')
        const result = getContract('ResultAudit')

        // 1. My enrolled (registered) exams
        const myExamIds = (await exam.getStudentExams(account)).map(Number)

        // 2. My scripts → per-exam list [{ sid, section }]
        //    (every section is a SEPARATE script, each with its own examiner)
        let myScripts = []
        try { myScripts = await hash.getStudentScripts(account) } catch { /* no scripts yet */ }
        const scriptsByExam = new Map()
        if (myScripts.length) {
          const examsOf = await Promise.all(myScripts.map((s) => hash.getExamId(s)))
          const sections = await Promise.all(myScripts.map((s) => hash.getScriptSection(s)))
          myScripts.forEach((s, i) => {
            const eid = Number(examsOf[i])
            if (!scriptsByExam.has(eid)) scriptsByExam.set(eid, [])
            scriptsByExam.get(eid).push({ sid: s, section: Number(sections[i]) })
          })
          for (const list of scriptsByExam.values()) list.sort((a, b) => a.section - b.section)
        }

        // 3. Enrolled courses + per-section approval status
        const enrolledList = []
        let anyPending = false

        // 3a. My rescrutiny applications (keyed "examId:section")
        const rescrutinyMap = {}
        try {
          const rescr = getContract('Rescrutiny')
          const appCount = Number(await rescr.getStudentApplicationCount(account))
          if (appCount > 0) {
            const [sids, examIds, sections, statuses, marksUpdated, reasons] =
              await rescr.getStudentApplications(account, { from: account })
            for (let i = 0; i < sids.length; i++) {
              const sid = sids[i]
              // Scrutinizer's return (suggested marks + comment) and the
              // examiner's revision, scoped to the student's OWN scriptId —
              // the events are address-free, so this leaks nothing about
              // other students (same anonymity-safe event pattern as the
              // examiner/scrutinizer pages).
              let suggested = null
              let comment = null
              let revised = null
              try {
                const [returns, responds] = await Promise.all([
                  rescr.queryFilter(rescr.filters.RescrutinyReturned(sid), 0, 'latest'),
                  rescr.queryFilter(rescr.filters.RescrutinyResponded(sid), 0, 'latest'),
                ])
                const lastRet = returns[returns.length - 1]
                if (lastRet) {
                  suggested = Number(lastRet.args[3])
                  comment = String(lastRet.args[4])
                }
                const lastResp = responds[responds.length - 1]
                if (lastResp) revised = Number(lastResp.args[3])
              } catch { /* ignore */ }
              rescrutinyMap[`${Number(examIds[i])}:${Number(sections[i])}`] = {
                sid,
                status: Number(statuses[i]),
                marksUpdated: marksUpdated[i],
                reason: reasons[i],
                suggested,
                comment,
                revised,
              }
            }
          }
        } catch { /* Rescrutiny not deployed yet */ }

        for (const eid of myExamIds) {
          const d = await exam.getExamDetails(eid)
          const list = scriptsByExam.get(eid) || []
          const sections = []
          for (const s of list) {
            let m = null
            try { m = await result.getMarks(s.sid) } catch { /* no marks record */ }
            sections.push({
              sid: s.sid,
              section: s.section,
              status: m ? Number(m[2]) : 0,
            })
          }
          const examState = Number(d[3])
          const pending =
            (examState !== 4 && examState !== 5) ||
            sections.some((s) => s.status > 0 && !GRADED_IDX.includes(s.status))
          enrolledList.push({
            examId: eid,
            title: d[0],
            course: d[1],
            term: Number(d[5]) ? await exam.getTermName(Number(d[5])) : 'General',
            totals: d[6].map(Number),
            examState,
            sections,
            pending,
          })
          if (pending) anyPending = true
        }

        // 4. Offered courses (CREATED or ACTIVE) I haven't registered yet
        const total = Number(await exam.getTotalExams())
        const offeredList = []
        for (let id = 1; id <= total; id++) {
          if (myExamIds.includes(id)) continue
          const d = await exam.getExamDetails(id)
          const st = Number(d[3])
          if (st !== 0 && st !== 1) continue
          const termId = Number(d[5])
          offeredList.push({
            examId: id,
            title: d[0],
            course: d[1],
            termId,
            term: termId ? await exam.getTermName(termId) : 'General',
            secTots: d[6].map(Number),
            date: Number(d[2]),
          })
        }

        // 5. Terms (Examination Types) — grouped listing for registration
        const termCount = Number(await exam.getTermCount())
        const termsList = []
        for (let id = 1; id <= termCount; id++) {
          termsList.push({ termId: id, name: await exam.getTermName(id) })
        }
        if (offeredList.some((c) => c.termId === 0)) {
          termsList.push({ termId: 0, name: 'General' })
        }

        // 6. Transcript — only when unlocked AND the student has scripts
        //    (getFullTranscript -> getStudentScripts reverts with
        //    "No scripts found for this student" when no script exists yet)
        let rowsOut = null
        let hasScripts = myScripts.length > 0
        if (!anyPending && hasScripts) {
          const t = await result.getFullTranscript(account, { from: account })
          const details = new Map()
          const secTotalCache = new Map()
          for (const eid of t.examIds) {
            if (!details.has(Number(eid))) {
              try {
                const d = await exam.getExamDetails(Number(eid))
                details.set(Number(eid), { title: d[0], course: d[1], totals: d[6].map(Number) })
              } catch {
                details.set(Number(eid), { title: '', course: '', totals: [] })
              }
            }
          }
          const out = []
          for (let i = 0; i < t.examIds.length; i++) {
            const eid = Number(t.examIds[i])
            const meta = details.get(eid) || { title: '', course: '', totals: [] }
            const sids = t.scripts[i] || []
            const sectionNos = await Promise.all(sids.map((sid) => hash.getScriptSection(sid)))
            const secTotals = await Promise.all(
              sectionNos.map(async (sec) => {
                const key = `${eid}:${sec}`
                if (!secTotalCache.has(key)) {
                  secTotalCache.set(key, Number(await exam.getSectionTotal(eid, sec)))
                }
                return secTotalCache.get(key)
              })
            )
            const sections = sids.map((sid, j) => ({
              sid,
              section: Number(sectionNos[j]),
              marks: Number((t.marksObtained[i] || [])[j]),
              total: secTotals[j],
            }))
            out.push({
              examId: eid,
              title: meta.title,
              course: meta.course,
              sections,
              totalMax: Number(t.totalMarks[i]),
              status: GRADE_STATUS[Number(t.statuses[i])] || String(t.statuses[i]),
              hasScrutiny: t.hasScrutiny[i],
            })
          }
          rowsOut = out
        }

        if (!cancelled) {
          setOffered(offeredList)
          setTerms(termsList)
          setEnrolled(enrolledList)
          setLocked(anyPending)
          setLockPending(enrolledList.filter((x) => x.pending))
          setRows(rowsOut)
          setHasScripts(hasScripts)
          setRescrutiny(rescrutinyMap)
          setApplyForm(null)
          setReasonDraft('')
        }
      } catch (e) {
        if (!cancelled) setError(formatError(e))
      }
    })()
    return () => { cancelled = true }
  }, [account, reload])

  if (error) return <div className="error-box"><span className="status-icon"><X size={15} strokeWidth={2.5} aria-hidden="true" /></span>{error}</div>
  if (offered === null) return <div className="loading">Loading your courses…</div>

  const visible = (rows || []).filter((r) => r.status !== 'NOT_SUBMITTED')
  const graded = visible.filter((r) => GRADED.includes(r.status))
  const gpa = graded.length
    ? graded.reduce((s, r) => s + gradeFor(r.sections.reduce((a, x) => a + x.marks, 0), r.totalMax).point, 0) / graded.length
    : null

  return (
    <div className="page">
      <h2>Student View</h2>

      <h3>Register for Offered Courses</h3>
      {offered.length === 0 ? (
        <div className="info-box">
          No open courses to register right now — check back once the admin
          creates a term and opens courses.
        </div>
      ) : selectedTerm === null ? (
        <>
          <p className="hint">
            Pick an Examination Type (Term) to see its open courses. Registering
            auto-enrolls you on-chain (admin can still customize).
          </p>
          <div className="term-grid">
            {(terms || []).map((t) => {
              const open = offered.filter((c) => c.termId === t.termId)
              if (open.length === 0) return null
              return (
                <button
                  key={t.termId}
                  type="button"
                  className="term-card"
                  onClick={() => setSelectedTerm(t.termId)}
                >
                  <strong>{t.name}</strong>
                  <span>{open.length} open {open.length === 1 ? 'course' : 'courses'}</span>
                </button>
              )
            })}
          </div>
        </>
      ) : (
        <>
          <button type="button" className="btn-sm" onClick={() => setSelectedTerm(null)}>
            <ArrowLeft size={14} aria-hidden="true" /> All Examination Types
          </button>
          <h4 className="term-title">
            {(terms || []).find((t) => t.termId === selectedTerm)?.name || 'General'}
          </h4>
          <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Course</th>
                <th>Exam</th>
                <th>Section totals</th>
                <th>Date</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {offered
                .filter((c) => c.termId === selectedTerm)
                .map((c) => (
                  <tr key={c.examId}>
                    <td>{c.course}</td>
                    <td>{c.title || `Exam ${c.examId}`}</td>
                    <td>
                      {c.secTots.map((t, i) => (
                        <span key={i} className="section-chip">S{i + 1}: {t}</span>
                      ))}
                    </td>
                    <td>{new Date(c.date * 1000).toLocaleDateString()}</td>
                    <td>
                      <button
                        className="btn-sm"
                        onClick={async () => {
                          try {
                            await sendTx(signer, 'ExamLifecycle', 'registerForCourse', c.examId)
                            setReload((r) => r + 1)
                          } catch (e) {
                            setError(formatError(e))
                          }
                        }}
                      >
                        Register (tx)
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
          </div>
        </>
      )}

      <h3>My Registered Courses</h3>
      {enrolled.length === 0 ? (
        <div className="info-box">You haven't registered for any course yet.</div>
      ) : (
        <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              <th>Course</th>
              <th>Exam</th>
              <th>Term</th>
              <th>Sections (scripts)</th>
            </tr>
          </thead>
          <tbody>
            {enrolled.map((c) => (
              <tr key={c.examId}>
                <td>{c.course}</td>
                <td>{c.title || `Exam ${c.examId}`}</td>
                <td>{c.term}</td>
                <td>
                  {c.sections.length === 0 ? (
                    <span className="section-chip">script pending</span>
                  ) : (
                    c.sections.map((s) => (
                      <div className="feed-block" key={s.sid}>
                        <span className={`state state-${(GRADE_STATUS[s.status] || '').toLowerCase()}`}>
                          S{s.section}: {GRADE_STATUS[s.status]}
                        </span>
                        <RescrutinySection
                          examId={c.examId}
                          section={s.section}
                          examState={c.examState}
                          sectionStatus={s.status}
                          app={rescrutiny[`${c.examId}:${s.section}`]}
                          signer={signer}
                          applyForm={applyForm}
                          reasonDraft={reasonDraft}
                          setApplyForm={setApplyForm}
                          setReasonDraft={setReasonDraft}
                          setError={setError}
                          onReload={() => setReload((r) => r + 1)}
                        />
                      </div>
                    ))
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        </div>
      )}

      {locked ? (
        <div className="info-box warning">
          <LockKeyhole size={15} className="inline-icon" aria-hidden="true" />{' '}
          <strong>Results are locked.</strong> Your gradesheet is released
          only after the admin marks each exam{' '}
          <strong>COMPLETED or FINALIZED</strong> and all sections are approved. Pending:{' '}
          {lockPending
            .map((c) =>
              c.examState !== 4 && c.examState !== 5
                ? `${c.course} (exam: ${EXAM_STATES[c.examState]})`
                : `${c.course} (${c.sections.map((s) => `S${s.section}: ${GRADE_STATUS[s.status]}`).join(', ')})`
            )
            .join(', ')}
          .
        </div>
      ) : rows === null ? (
        <div className="info-box">
          {hasScripts
            ? 'Your gradesheet is ready to generate once marks are recorded. Nothing to show yet.'
            : 'Your registration is saved, but no script has been assigned to you yet. ' +
              'Once the admin assigns your script (after examiners are set), results will appear here.'}
        </div>
      ) : visible.length === 0 ? (
        <div className="info-box">
          No graded results to display yet (marks are recorded for your
          registered courses but nothing is approved).
        </div>
      ) : (
        <>
          <div className="gpa-box">
            <div>
              <strong>CGPA: {gpa !== null ? gpa.toFixed(2) : '—'}</strong>
              <br />
              <span>
                {graded.length} graded {graded.length === 1 ? 'course' : 'courses'}
              </span>
            </div>
            <button className="btn-sm" onClick={() => downloadGradesheet(visible, account, gpa)}>
              <Download size={14} aria-hidden="true" /> Download Gradesheet (PDF)
            </button>
            <div className="seal" title="Results verified on-chain">
              VERIFIED
              <small>on-chain</small>
            </div>
          </div>
          <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>Course</th>
                <th>Exam</th>
                {secNumbers(visible).map((n) => (
                  <th key={n}>Section {n}</th>
                ))}
                <th>Total</th>
                <th>Grade</th>
                <th>Point</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((r, i) => {
                const sum = r.sections.reduce((s, x) => s + x.marks, 0)
                const g = gradeFor(sum, r.totalMax)
                const eligible = GRADED.includes(r.status)
                return (
                  <tr key={i}>
                    <td>
                      {r.course}
                      {r.title && <div className="feed-block">{r.title}</div>}
                    </td>
                    <td>
                      Exam {r.examId}
                      {r.sections.map((x) => (
                        <div key={x.sid} className="feed-block mono">{`S${x.section}: ${shortAddress(x.sid)}`}</div>
                      ))}
                    </td>
                    {secNumbers(visible).map((n) => {
                      const x = r.sections.find((s) => s.section === n)
                      return <td key={n}>{x ? `${x.marks}/${x.total}` : '—'}</td>
                    })}
                    <td>
                      <strong>{sum}/{r.totalMax}</strong>
                    </td>
                    <td>{eligible ? <strong>{g.grade}</strong> : '—'}</td>
                    <td>{eligible ? g.point.toFixed(2) : '—'}</td>
                    <td>
                      <span className={`state state-${r.status.toLowerCase()}`}>{r.status}</span>
                      {r.hasScrutiny && <span className="section-chip">reviewed</span>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          </div>
        </>
      )}
    </div>
  )
}

/**
 * Per-section rescrutiny controls (student side).
 * Visible only while the exam is COMPLETED and the section's marks are
 * APPROVED. Shows the application status; on APPROVED tells the student
 * the re-evaluation is done and the revised score is shown in the
 * gradesheet below. Non-applicants see nothing.
 */
function RescrutinySection({
  examId,
  section,
  examState,
  sectionStatus,
  app,
  signer,
  applyForm,
  reasonDraft,
  setApplyForm,
  setReasonDraft,
  setError,
  onReload,
}) {
  if (examState !== 4 || sectionStatus !== 4) return null
  const isForm = applyForm && applyForm.examId === examId && applyForm.section === section
  if (app) {
    const label = RESCRUTINY_STATUS[app.status] || String(app.status)
    if (app.status === 3) {
      return (
        <span className="rescrutiny-done">
          <Check size={14} className="inline-icon" aria-hidden="true" />
          {app.marksUpdated
            ? 'Re-evaluation approved — revised score shown in gradesheet'
            : 'Re-evaluation approved — score unchanged'}
        </span>
      )
    }
    return (
      <span>
        <span className={`state state-${label.toLowerCase()}`}>Rescrutiny: {label}</span>
        {app.status === 0 && (
          <div className="scrutiny-note">Applied for rescrutiny — awaiting response…</div>
        )}
        {app.status === 1 && (
          <div className="scrutiny-note scrutiny-pending">
            Returned by scrutinizer — suggested {app.suggested !== null ? app.suggested : '—'}
            {app.comment ? ` · “${app.comment}”` : ''}
          </div>
        )}
        {app.status === 2 && (
          <div className="scrutiny-note">
            Revised to {app.revised !== null ? app.revised : '—'} — awaiting scrutinizer approval
          </div>
        )}
      </span>
    )
  }
  return (
    <span>
      {isForm ? (
        <div className="rescrutiny-form">
          <textarea
            rows="2"
            placeholder="Reason for re-evaluation…"
            value={reasonDraft}
            onChange={(e) => setReasonDraft(e.target.value)}
          />
          <div className="inline-actions">
            <button
              type="button"
              className="btn-sm"
              disabled={!reasonDraft.trim()}
              onClick={async () => {
                try {
                  await sendTx(signer, 'Rescrutiny', 'applyForRescrutiny', examId, section, reasonDraft.trim())
                  onReload()
                } catch (e) {
                  setError(formatError(e))
                }
              }}
            >
              Submit (tx)
            </button>
            <button type="button" className="btn-sm" onClick={() => setApplyForm(null)}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          className="btn-sm"
          onClick={() => {
            setReasonDraft('')
            setApplyForm({ examId, section })
          }}
        >
          <Search size={14} aria-hidden="true" /> Request Rescrutiny
        </button>
      )}
    </span>
  )
}

/** Sorted union of section numbers present in the transcript rows. */
function secNumbers(rows) {
  return [...new Set(rows.flatMap((r) => r.sections.map((x) => x.section)))].sort((a, b) => a - b)
}

function downloadGradesheet(rows, account, gpa) {
  const doc = new jsPDF()
  doc.setFontSize(16)
  doc.text('ParikkhaChain — Official Gradesheet', 14, 16)
  doc.setFontSize(10)
  doc.text(
    `Student: ${account}`,
    14,
    23
  )
  doc.text(`Generated: ${new Date().toLocaleString()} · Ganache (chain 1337)`, 14, 28)
  const secs = secNumbers(rows)
  autoTable(doc, {
    startY: 33,
    head: [['#', 'Course', 'Exam', ...secs.map((n) => `S${n}`), 'Total', 'Grade', 'Point', 'Status']],
    body: rows.map((r, i) => {
      const sum = r.sections.reduce((s, x) => s + x.marks, 0)
      const g = gradeFor(sum, r.totalMax)
      const eligible = GRADED.includes(r.status)
      return [
        i + 1,
        r.course,
        `Exam ${r.examId}${r.title ? ` (${r.title})` : ''}`,
        ...secs.map((n) => {
          const x = r.sections.find((s) => s.section === n)
          return x ? `${x.marks}/${x.total}` : ''
        }),
        `${sum}/${r.totalMax}`,
        eligible ? g.grade : '—',
        eligible ? g.point.toFixed(2) : '—',
        r.status,
      ]
    }),
    foot: gpa !== null
      ? [[{}, '', '', ...secs.map(() => ''), 'CGPA', gpa.toFixed(2), '', '', `${rows.filter((r) => GRADED.includes(r.status)).length} grade(s)`]]
      : undefined,
    styles: { fontSize: 9 },
    headStyles: { fillColor: [31, 41, 55] },
    footStyles: { fillColor: [220, 220, 220], textColor: 20 },
  })
  const endY = doc.lastAutoTable.finalY + 5
  doc.setFontSize(8)
  doc.setTextColor(120)
  doc.text(
    'Blockchain-verified: grades, marks and scrutiny events are stored on-chain; only the student (or admin) may view them.',
    14,
    endY
  )
  doc.save(`ParikkhaChain_Gradesheet_${account.slice(0, 8)}.pdf`)
}
