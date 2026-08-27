import { useEffect, useState, useCallback } from 'react'
import { getAccounts, getSignerFor } from '../chain/provider'
import { getContract, ROLE_NAMES } from '../chain/contracts'

/**
 * Central chain state for the portal:
 *  - accounts: all Ganache accounts
 *  - account:  currently "logged in" account (the demo identity)
 *  - role:     global role via RBAC.getRole(account) (ADMIN > STUDENT > EXAMINER > SCRUTINIZER)
 *  - signer:   ethers signer for the selected account
 *
 * Role detection is SELF-ONLY — it never reveals any other account's role,
 * preserving the anonymity model on the frontend too.
 */
export function useChain() {
  const [accounts, setAccounts] = useState([])
  const [account, setAccount] = useState(null)
  const [role, setRole] = useState(null)
  const [error, setError] = useState(null)
  const [ready, setReady] = useState(false)
  const [signer, setSigner] = useState(null)

  const refreshRole = useCallback(async (addr) => {
    if (!addr) {
      setRole(null)
      return
    }
    try {
      const rbac = getContract('RBAC')
      const roleNum = Number(await rbac.getRole(addr))
      setRole(ROLE_NAMES[roleNum] || `ROLE_${roleNum}`)
    } catch (e) {
      setRole(null)
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    getAccounts()
      .then((accs) => {
        if (cancelled) return
        setAccounts(accs)
        setAccount(accs[0] || null)
      })
      .catch((e) => setError(String(e.message || e)))
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    refreshRole(account)
  }, [account, refreshRole])

  useEffect(() => {
    if (!account) {
      setSigner(null)
      return
    }
    let cancelled = false
    getSignerFor(account)
      .then((s) => {
        if (!cancelled) setSigner(s)
      })
      .catch((e) => setError(String(e.message || e)))
    return () => {
      cancelled = true
    }
  }, [account, setError])

  useEffect(() => {
    if (accounts.length > 0) setReady(true)
  }, [accounts])

  return { accounts, account, setAccount, role, signer, error, ready, refreshRole }
}
