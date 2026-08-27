import { JsonRpcProvider } from 'ethers'

// Ganache local chain (Remix "External HTTP Provider" target)
export const RPC_URL = 'http://127.0.0.1:8545'

let _provider = null

export function getProvider() {
  if (!_provider) {
    _provider = new JsonRpcProvider(RPC_URL)
  }
  return _provider
}

// Ganache accounts are unlocked — an ethers JsonRpcSigner sends with
// eth_sendTransaction on behalf of the selected account.
export async function getAccounts() {
  const signers = await getProvider().listAccounts()
  return signers.map((s) => s.address)
}

export async function getSignerFor(address) {
  const provider = getProvider()
  return provider.getSigner(address)
}

export function shortAddress(address) {
  if (!address) return ''
  const a = String(address)
  return `${a.slice(0, 8)}…${a.slice(-6)}`
}

export function formatError(err) {
  const msg = String(err?.shortMessage || err?.message || err)
  const m = msg.match(/reverted with reason string '([^']+)'/)
  if (m) return m[1]
  const m2 = msg.match(/execution reverted: ([^"(]+)/)
  if (m2) return m2[1]
  if (msg.toLowerCase().includes('missing revert data')) {
    return 'Transaction reverted on-chain. Common causes: student not enrolled in this exam, section already submitted, or exam not in ACTIVE/EVALUATION state. Check the Ganache console for details.'
  }
  return msg.slice(0, 200)
}
