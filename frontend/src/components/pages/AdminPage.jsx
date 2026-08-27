import { useState } from 'react'
import RolesTab from './admin/RolesTab'
import ExamsTab from './admin/ExamsTab'
import ScriptsTab from './admin/ScriptsTab'
import ResultsTab from './admin/ResultsTab'

const TABS = [
  { id: 'roles', label: 'Roles & Assignments' },
  { id: 'exams', label: 'Exams & Enrollment' },
  { id: 'scripts', label: 'Scripts (Anonymization)' },
  { id: 'results', label: 'Results & Audit' },
]

export default function AdminPage({ signer, account }) {
  const [tab, setTab] = useState('roles')

  return (
    <div className="page">
      <h2>Admin Console</h2>
      <p className="hint">
        Every action here is a signed transaction to the contracts — nothing is
        stored locally. Identity-revealing getters (assignments, progress,
        audit trail) are admin-only on-chain.
      </p>
      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`tab ${tab === t.id ? 'tab-active' : ''}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="tab-content">
        {tab === 'roles' && <RolesTab signer={signer} />}
        {tab === 'exams' && <ExamsTab signer={signer} account={account} />}
        {tab === 'scripts' && <ScriptsTab signer={signer} account={account} />}
        {tab === 'results' && <ResultsTab signer={signer} account={account} />}
      </div>
    </div>
  )
}
