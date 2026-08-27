import { JsonRpcProvider, Contract } from 'ethers'
import { readFileSync } from 'node:fs'

const ADDRESSES = JSON.parse(readFileSync('src/config/addresses.json', 'utf8'))
const abi = (n) => JSON.parse(readFileSync(`src/config/${n}.json`, 'utf8'))

const provider = new JsonRpcProvider('http://127.0.0.1:8545')
const accounts = (await provider.listAccounts()).map((s) => s.address)
console.log('accounts:', accounts.length)

const rbac = new Contract(ADDRESSES.RBAC, abi('RBAC'), provider)
const exam = new Contract(ADDRESSES.ExamLifecycle, abi('ExamLifecycle'), provider)
const hash = new Contract(ADDRESSES.HashRegistry, abi('HashRegistry'), provider)
const result = new Contract(ADDRESSES.ResultAudit, abi('ResultAudit'), provider)

const ROLE = { 1: 'ADMIN', 2: 'EXAMINER', 3: 'SCRUTINIZER', 4: 'STUDENT' }
const STATES = ['PENDING', 'ACTIVE', 'EVALUATION', 'SCRUTINY', 'COMPLETED', 'FINALIZED']
const short = (a) => `${a.slice(0, 8)}…${a.slice(-6)}`
const fmt = (e) => (e?.shortMessage || String(e?.message || e)).slice(0, 90)

for (const idx of [0, 1, 2, 8, 9, 15]) {
  const roleNum = Number(await rbac.getRole(accounts[idx]))
  console.log(`[${idx}] ${short(accounts[idx])} role=${ROLE[roleNum]}`)
}

const signer = await provider.getSigner(accounts[0])
const rbacS = rbac.connect(signer)
console.log('signer-based getRole:', ROLE[Number(await rbacS.getRole(accounts[0]))])

for (let id = 1; id <= 3; id++) {
  const sec = Number(await rbac.getMyExamSection(id, { from: accounts[1] }))
  const d = await exam.getExamDetails(id)
  console.log(`account[1] exam ${id}: section=${sec || 'none'} state=${STATES[Number(d[3])]}`)
}

const scripts = await hash.getExamScripts(17)
console.log('exam 17 scripts (public):', scripts.length)

try {
  await rbac.getExamExaminers(17, { from: accounts[1] })
  console.log('non-admin getExamExaminers: ALLOWED (unexpected!)')
} catch (e) {
  console.log('non-admin getExamExaminers: REVERTED as expected —', fmt(e))
}
const examiners = await rbac.getExamExaminers(17, { from: accounts[0] })
console.log('admin getExamExaminers(17):', examiners.map(short).join(', '))

try {
  await result.connect(signer).submitMarks('SCRIPT_17_99', 1, 50)
  console.log('admin submitMarks: ALLOWED (unexpected!)')
} catch (e) {
  console.log('admin submitMarks: REVERTED as expected —', fmt(e))
}

process.exit(0)
