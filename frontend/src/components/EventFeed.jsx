import { useEffect, useState } from 'react'
import { getContract, ADDRESSES } from '../chain/contracts'
import { shortAddress } from '../chain/provider'

const SUBSCRIPTIONS = [
  ['RBAC', ['RoleGranted', 'RoleRevoked', 'ExaminerAssigned', 'ExaminerRevoked', 'ScrutinizerAssigned', 'ScrutinizerRevoked']],
  ['ExamLifecycle', ['ExamCreated', 'ExamStateUpdated', 'StudentEnrolled']],
  ['HashRegistry', ['ScriptRegistered', 'StudentRevealed']],
  ['ResultAudit', [
    'SectionMarksSubmitted',
    'ScriptReturnedForScrutiny', 'ScrutinyResponse',
    'ScrutinyApproved', 'ScrutinyRejected', 'ResultFinalized',
    'MarksUpdatedAfterRescrutiny',
  ]],
  ['Rescrutiny', [
    'RescrutinyApplied', 'RescrutinyReturned', 'RescrutinyResponded', 'RescrutinyApproved',
  ]],
]

function fmtValue(v) {
  if (typeof v === 'bigint') return Number(v).toLocaleString()
  if (typeof v === 'string' && v.startsWith('0x')) return shortAddress(v)
  if (typeof v === 'string') return v
  if (v && typeof v === 'object' && typeof v.toHexString === 'function') {
    return `${v.toHexString().slice(0, 20)}… (scriptId hash)`
  }
  return String(v)
}

export default function EventFeed() {
  const [events, setEvents] = useState([])

  useEffect(() => {
    const subs = []
    for (const [contractName, eventNames] of SUBSCRIPTIONS) {
      if (!ADDRESSES[contractName]) continue
      const contract = getContract(contractName)
      for (const eventName of eventNames) {
        const handler = (...rest) => {
          const ev = rest[rest.length - 1]
          if (!ev || !ev.args || !ev.fragment) return
          const named = {}
          ev.fragment.inputs.forEach((inp, i) => {
            named[inp.name] = ev.args[i]
          })
          const summary = Object.entries(named)
            .map(([k, val]) => `${k}=${fmtValue(val)}`)
            .join(' · ')
          const item = {
            id: `${ev.blockNumber}-${ev.logIndex}-${Math.random()}`,
            contract: contractName,
            event: eventName,
            summary,
            block: Number(ev.blockNumber),
            tx: ev.transactionHash,
          }
          setEvents((prev) => [item, ...prev].slice(0, 30))
        }
        try {
          contract.on(eventName, handler)
          subs.push(() => contract.off(eventName, handler))
        } catch {
          // event not in ABI — skip
        }
      }
    }
    return () => subs.forEach((off) => off())
  }, [])

  return (
    <aside className="feed">
      <h3>Chain Ledger</h3>
      <p className="hint">
        No addresses in exam/marks/scrutiny/rescrutiny events — scriptIds
        appear as keccak hashes (anonymity). Role/registration events carry
        addresses by design (admin actions).
      </p>
      {events.length === 0 && <div className="feed-empty">Waiting for transactions…</div>}
      {events.map((e) => (
        <div className="feed-item" key={e.id}>
          <div className="feed-head">
            <span className={`badge-sm badge-${e.contract.toLowerCase()}`}>{e.event}</span>
            <span className="feed-block">block {e.block}</span>
          </div>
          <div className="feed-summary">{e.summary}</div>
          <div className="feed-meta">{e.contract}</div>
        </div>
      ))}
    </aside>
  )
}
