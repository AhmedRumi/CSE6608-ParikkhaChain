import { useChain } from './hooks/useChain'
import AccountSwitcher from './components/AccountSwitcher'
import RoleBadge from './components/RoleBadge'
import EventFeed from './components/EventFeed'
import { X } from 'lucide-react'
import AdminPage from './components/pages/AdminPage'
import ExaminerPage from './components/pages/ExaminerPage'
import ScrutinizerPage from './components/pages/ScrutinizerPage'
import StudentPage from './components/pages/StudentPage'

export default function App() {
  const { accounts, account, setAccount, role, signer, error, ready } = useChain()

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="seal-mark">PC</span>
          <div>
            <h1>Parikkha<span>Chain</span></h1>
            <p>Decentralized Examination & Result Verification</p>
          </div>
        </div>
        <div className="topbar-right">
          <RoleBadge role={role} />
          <AccountSwitcher accounts={accounts} account={account} setAccount={setAccount} />
        </div>
      </header>

      {error && (
        <div className="error-box">
          <span className="status-icon">
            <X size={15} strokeWidth={2.5} aria-hidden="true" />
          </span>
          {error}
        </div>
      )}

      {!ready ? (
        <div className="loading">Connecting to Ganache (127.0.0.1:8545)…</div>
      ) : (
        <div className="layout">
          <main className="content">
            {role === 'ADMIN' && <AdminPage signer={signer} account={account} />}
            {role === 'EXAMINER' && <ExaminerPage signer={signer} account={account} />}
            {role === 'SCRUTINIZER' && <ScrutinizerPage signer={signer} account={account} />}
            {role === 'STUDENT' && <StudentPage account={account} signer={signer} />}
            {!role && (
              <div className="page">
                <h2>No role assigned to this wallet</h2>
                <p>
                  This account has no role on-chain. Switch to another Ganache
                  account (e.g. <span className="mono">[0]</span> = admin, an
                  examiner, a scrutinizer, or a student account) to see the
                  corresponding view.
                </p>
                <p>
                  <strong>Anonymity note:</strong> role detection uses
                  self-check getters only — the app never queries another
                  account's role.
                </p>
              </div>
            )}
          </main>
          <EventFeed />
        </div>
      )}

      <footer className="footer">
        ParikkhaChain · Ganache 127.0.0.1:8545 · role-based views are UX
        filtering — authorization is enforced by the contracts on-chain
      </footer>
    </div>
  )
}
