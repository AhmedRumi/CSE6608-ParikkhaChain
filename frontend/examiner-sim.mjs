import { JsonRpcProvider, Contract } from 'ethers'
import { readFileSync } from 'node:fs'

const ADDRESSES = JSON.parse(readFileSync('src/config/addresses.json', 'utf8'))
const abi = (n) => JSON.parse(readFileSync(`src/config/${n}.json`, 'utf8'))
const provider = new JsonRpcProvider('http://127.0.0.1:8545')
const accounts = (await provider.listAccounts()).map((s) => s.address)

const exam = new Contract(ADDRESSES.ExamLifecycle, abi('ExamLifecycle'), provider)
const rbac = new Contract(ADDRESSES.RBAC, abi('RBAC'), provider)
const result = new Contract(ADDRESSES.ResultAudit, abi('ResultAudit'), provider)
const hash = new Contract(ADDRESSES.HashRegistry, abi('HashRegistry'), provider)

const EXAM_STATES = ['PENDING', 'ACTIVE', 'EVALUATION', 'SCRUTINY', 'COMPLETED', 'FINALIZED']
const SECTION_STATUS = ['NOT_SUBMITTED', 'SUBMITTED', 'UNDER_SCRUTINY', 'SCRUTINIZED', 'APPROVED']

const account = accounts[1]
console.log('account[1]:', account)
const total = Number(await exam.getTotalExams())
for (let id = 1; id <= total; id++) {
  const mySec = Number(await rbac.getMyExamSection(id, { from: account }))
  console.log(`exam ${id}: mySection=${mySec || 'NONE'}`)
  if (mySec === 0) continue
  const d = await exam.getExamDetails(id)
  const scripts = await hash.getExamScripts(id)
  console.log(`  name=${d[0]} state=${EXAM_STATES[Number(d[3])]} scripts=${scripts.join(', ')}`)
  for (const sid of scripts) {
    const [, marks, status] = await result.getMySectionMarks(sid, { from: account })
    console.log(`    ${sid}: ${Number(marks)}/50 ${SECTION_STATUS[Number(status)]}`)
  }
}
process.exit(0)
