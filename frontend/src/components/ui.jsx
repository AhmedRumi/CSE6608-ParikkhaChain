import { useState } from 'react'
import { formatError } from '../chain/provider'
import { Check, X, Loader2 } from 'lucide-react'

export function StatusLine({ result }) {
  if (!result) return null
  return (
    <div className={`status ${result.ok ? 'status-ok' : 'status-err'}`}>
      <span className="status-icon">
        {result.ok ? (
          <Check size={14} strokeWidth={2.5} aria-hidden="true" />
        ) : (
          <X size={14} strokeWidth={2.5} aria-hidden="true" />
        )}
      </span>
      {result.message}
    </div>
  )
}

/**
 * Generic contract-call form. Fields are {name, label, type, options, initial, placeholder}.
 * onSubmit(values) must return a display string (e.g. receipt summary) or throw.
 */
export function TxForm({ title, fields, onSubmit, submitLabel, compact }) {
  const [values, setValues] = useState(() =>
    Object.fromEntries(fields.map((f) => [f.name, f.initial ?? '']))
  )
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  const run = async (e) => {
    e.preventDefault()
    setBusy(true)
    setResult(null)
    try {
      const submitted = { ...values }
      for (const f of fields) {
        if (
          f.type === 'select' &&
          f.options?.length &&
          !f.options.some((o) => o.value === submitted[f.name])
        ) {
          submitted[f.name] = f.options[0].value
        }
      }
      const msg = await onSubmit(submitted)
      setResult({ ok: true, message: msg })
    } catch (err) {
      setResult({ ok: false, message: formatError(err) })
    } finally {
      setBusy(false)
    }
  }

  const set = (name) => (e) => setValues((v) => ({ ...v, [name]: e.target.value }))

  return (
    <form className="tx-form" onSubmit={run}>
      {title && <h4>{title}</h4>}
      {fields.map((f) => (
        <label key={f.name} className="field">
          <span>{f.label}</span>
          {f.type === 'select' ? (
            <select
              name={f.name}
              value={
                f.options?.length && !f.options.some((o) => o.value === values[f.name])
                  ? f.options[0].value
                  : values[f.name]
              }
              onChange={set(f.name)}
            >
              {f.options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              type={f.type || 'text'}
              name={f.name}
              value={values[f.name]}
              onChange={set(f.name)}
              placeholder={f.placeholder || ''}
              step={f.step}
              required={f.required ?? true}
            />
          )}
        </label>
      ))}
      <button type="submit" disabled={busy} className={compact ? 'btn-sm' : ''}>
        {busy ? (
          <span className="btn-busy">
            <Loader2 size={14} className="spin" aria-hidden="true" /> Sending...
          </span>
        ) : (
          submitLabel || 'Submit'
        )}
      </button>
      <StatusLine result={result} />
    </form>
  )
}

/** Sends a tx with the given signer and returns a receipt summary string. */
export async function sendTx(signer, contractName, fnName, ...args) {
  const { getContract } = await import('../chain/contracts')
  const { getProvider } = await import('../chain/provider')
  const contract = getContract(contractName).connect(signer)

  let tx
  try {
    tx = await contract[fnName](...args)
  } catch (err) {
    const info = await replayForReason(contract, signer, fnName, args, getProvider())
    if (info?.reason) throw new Error(`Reverted on-chain: ${info.reason}`)
    throw new Error(
      `Rejected before mining · from ${signer.address.slice(0, 10)}… · ${fnName}(${args
        .map((a) => (typeof a === 'string' ? JSON.stringify(a) : String(a)))
        .join(', ')}) · ${info?.replay || err.shortMessage || err.message || err}`
    )
  }

  let receipt
  try {
    receipt = await tx.wait()
  } catch (err) {
    const reason = await replayForReason(contract, signer, fnName, args, getProvider())
    if (reason) throw new Error(`Reverted on-chain: ${reason}`)
    throw new Error(`Transaction reverted with no decodable reason (tx ${tx.hash})`)
  }

  if (receipt.status !== 1) {
    const reason = await replayForReason(contract, signer, fnName, args, getProvider())
    if (reason) throw new Error(`Reverted on-chain: ${reason}`)
    throw new Error(`Transaction reverted on-chain (tx ${tx.hash})`)
  }
  return `tx ${tx.hash.slice(0, 12)}… · block ${receipt.blockNumber}`
}

/** Replays the failed call as eth_call to extract the actual revert reason. */
async function replayForReason(contract, signer, fnName, args, provider) {
  try {
    await provider.call(
      {
        from: signer.address,
        to: contract.target,
        data: contract.interface.encodeFunctionData(fnName, args),
      },
      'latest'
    )
    return { reason: null, replay: 'replay succeeded (call would pass now)' }
  } catch (err) {
    try {
      if (err.data) {
        const r = contract.interface.decodeErrorResult(err.data)
        return { reason: String(r?.args?.[0] ?? JSON.stringify(r)), replay: null }
      }
    } catch {
      /* not a decodable revert reason */
    }
    return { reason: null, replay: `replay reverted (${err.shortMessage || err.message})` }
  }
}
