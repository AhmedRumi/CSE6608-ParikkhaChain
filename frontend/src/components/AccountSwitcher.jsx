import { useEffect, useRef, useState } from 'react'
import { shortAddress } from '../chain/provider'
import { ChevronDown, Copy } from 'lucide-react'

export default function AccountSwitcher({ accounts, account, setAccount }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    const onClick = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('click', onClick)
    return () => document.removeEventListener('click', onClick)
  }, [])

  const copy = (addr) => navigator.clipboard?.writeText(addr)
  const currentIdx = accounts.indexOf(account)

  return (
    <div className="account-switcher" ref={ref}>
      <label>Logged in as (wallet = identity):</label>
      <div className="account-menu">
        <button
          type="button"
          className="account-menu-trigger"
          onClick={() => setOpen(!open)}
        >
          <span className="account-menu-label">
            {account
              ? `[${currentIdx}] ${account} · ${shortAddress(account)}`
              : 'Select account…'}
          </span>
          <ChevronDown size={14} className="account-menu-caret" aria-hidden="true" />
        </button>
        {open && (
          <ul className="account-menu-list">
            {accounts.map((acc, i) => (
              <li key={acc}>
                <button
                  type="button"
                  className="account-menu-item"
                  onClick={() => {
                    setAccount(acc)
                    setOpen(false)
                  }}
                >
                  [{i}] {acc} · {shortAddress(acc)}
                </button>
                <button
                  type="button"
                  className="account-menu-copy"
                  title="Copy address"
                  onClick={(e) => {
                    e.stopPropagation()
                    copy(acc)
                  }}
                >
                  <Copy size={12} aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
