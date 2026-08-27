import { useEffect, useState } from 'react'
import { StatusLine } from '../../ui'
import { getContract } from '../../../chain/contracts'
import { shortAddress, formatError } from '../../../chain/provider'
import { Check, X } from 'lucide-react'

/**
 * Script registration with section options driven by the selected exam's
 * actual section count (admin-defined at exam creation).
 */
function RegisterScriptForm({ exams, courseOptions, signer }) {
  const [values, setValues] = useState({
    examId: exams?.[0]?.examId ? String(exams[0].examId) : '',
    section: '1',
    studentAddress: '',
    studentName: '',
    studentId: '',
    courseCode: courseOptions[0]?.value || '',
  })
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  const exam = exams?.find((e) => String(e.examId) === values.examId)
  const secCount = Math.max(1, exam?.secCount || 1)
  const sectionOptions = Array.from({ length: secCount }, (_, i) => ({
    value: String(i + 1),
    label: `Section ${i + 1}`,
  }))

  const set = (name) => (e) => setValues((v) => ({ ...v, [name]: e.target.value }))

  // Keep the selected exam AND course code in sync once the exam list
  // loads. `examId` and `courseCode` are initialized from `exams`/`courseOptions`
  // only once on mount, but those props are null until the async fetch
  // completes. Without syncing, a stale '' would submit as an empty course
  // code and revert on-chain with "Course code cannot be empty".
  useEffect(() => {
    setValues((v) => {
      const valid = (exams || []).some((e) => String(e.examId) === v.examId)
      const newExamId = valid
        ? v.examId
        : exams?.[0]?.examId
          ? String(exams[0].examId)
          : ''
      // Sync courseCode from the first exam's course when stale
      let newCourseCode = v.courseCode
      if (!v.courseCode && courseOptions?.[0]?.value) {
        newCourseCode = courseOptions[0].value
      } else if (
        v.courseCode &&
        !(courseOptions || []).some((o) => o.value === v.courseCode)
      ) {
        newCourseCode = courseOptions?.[0]?.value || ''
      }
      return { ...v, examId: newExamId, courseCode: newCourseCode }
    })
  }, [exams, courseOptions])

  const run = async (e) => {
    e.preventDefault()
    setBusy(true)
    setResult(null)
    try {
      const examId = Number(values.examId)
      if (!examId) {
        throw new Error('Select an exam first — create one in the Exams tab if none exist')
      }
      // Validate inputs before hitting the chain: Ganache + solc 0.8.19 can
      // return opaque "missing revert data" errors for reverts, so we
      // surface clear errors up front where we can.
      if (!values.studentAddress || values.studentAddress === '0x' || values.studentAddress.length < 10) {
        throw new Error('Enter a valid student address')
      }
      const exam = getContract('ExamLifecycle')
      const enrolled = await exam.isStudentEnrolled(examId, values.studentAddress)
      if (!enrolled) {
        throw new Error(
          `Student ${shortAddress(values.studentAddress)} is not enrolled in this exam. ` +
          'Enroll them first from the Admin ▸ Exams tab, or have the student self-register.'
        )
      }
      const hash = getContract('HashRegistry').connect(signer)
      const tx = await hash.registerScriptFromTopsheet(
        examId,
        Number(values.section),
        values.studentAddress,
        values.studentName,
        values.studentId,
        values.courseCode
      )
      const rec = await tx.wait()
      const logs = await hash.queryFilter(hash.filters.ScriptRegistered(), rec.blockNumber, rec.blockNumber)
      const scriptId = logs[0] ? String(logs[0].args[0]) : '(unknown)'
      setResult({
        ok: true,
        message: `tx ${tx.hash.slice(0, 12)}… · block ${rec.blockNumber} · ${scriptId}`,
      })
    } catch (err) {
      setResult({ ok: false, message: formatError(err) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="tx-form" onSubmit={run}>
      <h4>Every section is a SEPARATE script — register each section once</h4>
      <label className="field">
        <span>Exam</span>
        <select
          value={values.examId}
          onChange={(e) => {
            set('examId')(e)
            setValues((v) => ({ ...v, section: '1' }))
          }}
        >
          {(exams || []).map((ex) => (
            <option key={ex.examId} value={String(ex.examId)}>
              Exam {ex.examId} · {ex.course}{ex.name ? ` · ${ex.name}` : ''} ({ex.secCount} section(s))
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Section</span>
        <select value={values.section} onChange={set('section')}>
          {sectionOptions.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Student address</span>
        <input value={values.studentAddress} onChange={set('studentAddress')} required />
      </label>
      <label className="field">
        <span>Student name</span>
        <input value={values.studentName} onChange={set('studentName')} required />
      </label>
      <label className="field">
        <span>Student ID</span>
        <input value={values.studentId} onChange={set('studentId')} required />
      </label>
      <label className="field">
        <span>Course code</span>
        <select value={values.courseCode} onChange={set('courseCode')}>
          {courseOptions.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </label>
      <button type="submit" disabled={busy}>
        {busy ? <span className="btn-busy">Sending...</span> : 'Register script (tx)'}
      </button>
      <StatusLine result={result} />
    </form>
  )
}

export default function ScriptsTab({ signer, account }) {
  const [scripts, setScripts] = useState(null)
  const [scriptsError, setScriptsError] = useState(null)
  const [listExamId, setListExamId] = useState('')
  const [revealed, setRevealed] = useState(null)
  const [revealError, setRevealError] = useState(null)
  const [revealScriptId, setRevealScriptId] = useState('')
  const [verified, setVerified] = useState(null)
  const [exams, setExams] = useState(null)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const exam = getContract('ExamLifecycle')
        const total = Number(await exam.getTotalExams())
        const list = []
        for (let id = 1; id <= total; id++) {
          const d = await exam.getExamDetails(id)
          list.push({ examId: id, course: d[1], name: d[0], secCount: (d[6] || []).length })
        }
        if (!cancelled) setExams(list)
      } catch {
        if (!cancelled) setExams([])
      }
    })()
    return () => { cancelled = true }
  }, [])

  const courseOptions = [...new Map((exams || []).map((e) => [e.course, e])).values()].map((e) => ({
    value: e.course,
    label: `${e.course} · Exam ${e.examId}${e.name ? ` · ${e.name}` : ''}`,
  }))

  const loadScripts = async (e) => {
    e.preventDefault()
    setScriptsError(null)
    setScripts(null)
    try {
      const hash = getContract('HashRegistry')
      const list = await hash.getExamScripts(Number(listExamId))
      const withSections = await Promise.all(
        list.map(async (s) => ({
          sid: s,
          section: Number(await hash.getScriptSection(s)),
        }))
      )
      setScripts(withSections)
    } catch (err) {
      setScriptsError(formatError(err))
    }
  }

  const doReveal = async (e) => {
    e.preventDefault()
    setRevealError(null)
    setRevealed(null)
    try {
      const hash = getContract('HashRegistry')
      const r = await hash.revealStudent(revealScriptId, { from: account })
      setRevealed({ address: r[0], name: r[1], id: r[2], course: r[3] })
    } catch (err) {
      setRevealError(formatError(err))
    }
  }

  const doVerify = async (e) => {
    e.preventDefault()
    const v = new FormData(e.target)
    const hash = getContract('HashRegistry')
    const ok = await hash.verifyTopsheet(
      v.get('scriptId'),
      v.get('studentName'),
      v.get('studentId'),
      v.get('courseCode')
    )
    setVerified(ok)
  }

  return (
    <div>
      <div className="grid-2">
        <div>
          <h3>Register Script (Anonymization)</h3>
          <RegisterScriptForm exams={exams} courseOptions={courseOptions} signer={signer} />
          <h3>Verify Topsheet</h3>
          <form className="tx-form" onSubmit={doVerify}>
            <label className="field">
              <span>Script ID</span>
              <input name="scriptId" required placeholder="SCRIPT_…" />
            </label>
            <label className="field">
              <span>Student name</span>
              <input name="studentName" required />
            </label>
            <label className="field">
              <span>Student ID</span>
              <input name="studentId" required />
            </label>
            <label className="field">
              <span>Course code</span>
              <select name="courseCode" required>
                {courseOptions.length === 0 && <option value="">No courses yet</option>}
                {courseOptions.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </label>
            <button type="submit">Verify (view)</button>
            {verified !== null && (
              <div className={`status ${verified ? 'status-ok' : 'status-err'}`}>
                <span className="status-icon">
                  {verified ? (
                    <Check size={14} strokeWidth={2.5} aria-hidden="true" />
                  ) : (
                    <X size={14} strokeWidth={2.5} aria-hidden="true" />
                  )}
                </span>
                {verified ? 'Topsheet matches — hash verified' : 'Topsheet does NOT match'}
              </div>
            )}
          </form>
        </div>

        <div>
          <h3>Reveal & Inspect</h3>
          <form className="tx-form" onSubmit={doReveal}>
            <h4>Reveal student identity (admin view)</h4>
            <label className="field">
              <span>Script ID</span>
              <input value={revealScriptId} onChange={(e) => setRevealScriptId(e.target.value)} placeholder="SCRIPT_…" />
            </label>
            <button type="submit">Reveal (view)</button>
            <StatusLine result={revealError ? { ok: false, message: revealError } : null} />
            {revealed && (
              <div className="lookup-result">
                {revealed.name} · {revealed.id} · {revealed.course} · {shortAddress(revealed.address)}
              </div>
            )}
          </form>

          <form className="tx-form" onSubmit={loadScripts}>
            <h4>Scripts of an exam (public)</h4>
            <label className="field">
              <span>Exam ID</span>
              <input type="number" value={listExamId} onChange={(e) => setListExamId(e.target.value)} />
            </label>
            <button type="submit">Load scripts (view)</button>
            <StatusLine result={scriptsError ? { ok: false, message: scriptsError } : null} />
            {scripts && (
              <ul className="addr-list">
                {scripts.length === 0 && <li>No scripts registered</li>}
                {scripts.map((s) => (
                  <li key={s.sid}>
                    {s.sid} <span className="section-chip">Section {s.section}</span>
                  </li>
                ))}
              </ul>
            )}
          </form>
        </div>
      </div>
    </div>
  )
}
