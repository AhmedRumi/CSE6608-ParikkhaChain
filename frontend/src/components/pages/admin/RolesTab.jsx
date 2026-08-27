import { useState } from 'react'
import { TxForm, sendTx, StatusLine } from '../../ui'
import { getContract } from '../../../chain/contracts'
import { formatError, shortAddress } from '../../../chain/provider'

const ROLE_OPTIONS = [
  { value: '1', label: 'ADMIN (1)' },
  { value: '2', label: 'EXAMINER (2)' },
  { value: '3', label: 'SCRUTINIZER (3)' },
  { value: '4', label: 'STUDENT (4)' },
]

const SECTION_OPTIONS = Array.from({ length: 10 }, (_, i) => ({
  value: String(i + 1),
  label: `Section ${i + 1}`,
}))

export default function RolesTab({ signer }) {
  const [lookup, setLookup] = useState({ address: '' })
  const [lookupResult, setLookupResult] = useState(null)
  const [lookupError, setLookupError] = useState(null)

  const doLookup = async (e) => {
    e.preventDefault()
    setLookupError(null)
    try {
      const rbac = getContract('RBAC')
      const role = Number(await rbac.getRole(lookup.address))
      const bits = Number(await rbac.getRoleBits(lookup.address))
      setLookupResult({ role, bits })
    } catch (err) {
      setLookupError(formatError(err))
    }
  }

  return (
    <div className="grid-2">
      <div>
        <h3>Grant / Revoke Roles</h3>
        <TxForm
          title="Grant role"
          fields={[
            { name: 'account', label: 'Account address' },
            { name: 'role', label: 'Role', type: 'select', options: ROLE_OPTIONS, initial: '2' },
          ]}
          onSubmit={(v) => sendTx(signer, 'RBAC', 'grantRole', v.account, Number(v.role))}
          submitLabel="Grant role (tx)"
        />
        <TxForm
          title="Revoke role"
          fields={[
            { name: 'account', label: 'Account address' },
            { name: 'role', label: 'Role', type: 'select', options: ROLE_OPTIONS, initial: '2' },
          ]}
          onSubmit={(v) => sendTx(signer, 'RBAC', 'revokeRole', v.account, Number(v.role))}
          submitLabel="Revoke role (tx)"
        />
        <TxForm
          title="Revoke all roles"
          fields={[{ name: 'account', label: 'Account address' }]}
          onSubmit={(v) => sendTx(signer, 'RBAC', 'revokeAllRoles', v.account)}
          submitLabel="Revoke all (tx)"
        />
        <form className="tx-form" onSubmit={doLookup}>
          <h4>Lookup an account's roles</h4>
          <label className="field">
            <span>Account address</span>
            <input
              value={lookup.address}
              onChange={(e) => setLookup({ address: e.target.value })}
              placeholder="0x…"
            />
          </label>
          <button type="submit">Lookup (view)</button>
          <StatusLine result={lookupError ? { ok: false, message: lookupError } : null} />
          {lookupResult && (
            <div className="lookup-result">
              getRole → {['NONE', 'ADMIN', 'EXAMINER', 'SCRUTINIZER', 'STUDENT'][lookupResult.role]}{' '}
              · getRoleBits → {lookupResult.bits}
            </div>
          )}
        </form>
      </div>

      <div>
        <h3>Exam Assignments</h3>
        <TxForm
          title="Assign section examiner (sections are 1..10; exam's own count is enforced on-chain)"
          fields={[
            { name: 'examiner', label: 'Examiner address' },
            { name: 'examId', label: 'Exam ID', type: 'number' },
            { name: 'section', label: 'Section', type: 'select', options: SECTION_OPTIONS, initial: '1' },
          ]}
          onSubmit={(v) =>
            sendTx(signer, 'RBAC', 'assignExaminerToExam', v.examiner, Number(v.examId), Number(v.section))
          }
          submitLabel="Assign examiner (tx)"
        />
        <TxForm
          title="Revoke examiner from exam"
          fields={[
            { name: 'examiner', label: 'Examiner address' },
            { name: 'examId', label: 'Exam ID', type: 'number' },
          ]}
          onSubmit={(v) =>
            sendTx(signer, 'RBAC', 'revokeExaminerFromExam', v.examiner, Number(v.examId))
          }
          submitLabel="Revoke examiner (tx)"
        />
        <TxForm
          title="Assign scrutinizer to exam"
          fields={[
            { name: 'scrutinizer', label: 'Scrutinizer address' },
            { name: 'examId', label: 'Exam ID', type: 'number' },
          ]}
          onSubmit={(v) =>
            sendTx(signer, 'RBAC', 'assignScrutinizerToExam', v.scrutinizer, Number(v.examId))
          }
          submitLabel="Assign scrutinizer (tx)"
        />
        <TxForm
          title="Revoke scrutinizer from exam"
          fields={[
            { name: 'scrutinizer', label: 'Scrutinizer address' },
            { name: 'examId', label: 'Exam ID', type: 'number' },
          ]}
          onSubmit={(v) =>
            sendTx(signer, 'RBAC', 'revokeScrutinizerFromExam', v.scrutinizer, Number(v.examId))
          }
          submitLabel="Revoke scrutinizer (tx)"
        />
      </div>
    </div>
  )
}
