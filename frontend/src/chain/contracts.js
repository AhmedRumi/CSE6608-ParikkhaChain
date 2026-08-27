import { Contract } from 'ethers'
import { getProvider } from './provider'

import ADDRESSES from '../../../deployed_addresses.json'
import ABI_RBAC from '../config/RBAC.json'
import ABI_EXAM from '../config/ExamLifecycle.json'
import ABI_HASH from '../config/HashRegistry.json'
import ABI_RESULT from '../config/ResultAudit.json'
import ABI_RESCRUTINY from '../config/Rescrutiny.json'

const ABIS = {
  RBAC: ABI_RBAC,
  ExamLifecycle: ABI_EXAM,
  HashRegistry: ABI_HASH,
  ResultAudit: ABI_RESULT,
  Rescrutiny: ABI_RESCRUTINY,
}

export function getContract(name, signerOrProvider = null) {
  const address = ADDRESSES[name]
  if (!address) throw new Error(`No deployed address for ${name}`)
  return new Contract(address, ABIS[name], signerOrProvider || getProvider())
}

export { ADDRESSES }

// Exam state enum (ExamLifecycle): 0 CREATED,1 ACTIVE,2 EVALUATION,
// 3 SCRUTINY, 4 COMPLETED, 5 FINALIZED
export const EXAM_STATES = ['CREATED', 'ACTIVE', 'EVALUATION', 'SCRUTINY', 'COMPLETED', 'FINALIZED']

// RescrutinyStatus (Rescrutiny): 0 APPLIED,1 RETURNED,2 REVISED,3 APPROVED
export const RESCRUTINY_STATUS = ['APPLIED', 'RETURNED', 'REVISED', 'APPROVED']

// RBAC Role enum: ADMIN=1, EXAMINER=2, SCRUTINIZER=3, STUDENT=4
export const ROLE_NAMES = {
  1: 'ADMIN',
  2: 'EXAMINER',
  3: 'SCRUTINIZER',
  4: 'STUDENT',
}

// SectionStatus (ResultAudit): 0 NOT_SUBMITTED,1 SUBMITTED,2 UNDER_SCRUTINY,
// 3 SCRUTINIZED, 4 APPROVED
export const SECTION_STATUS = [
  'NOT_SUBMITTED',
  'SUBMITTED',
  'UNDER_SCRUTINY',
  'SCRUTINIZED',
  'APPROVED',
]

// GradeStatus: 0 NOT_SUBMITTED,1 SUBMITTED,2 UNDER_SCRUTINY,3 SCRUTINIZED,
// 4 APPROVED, 5 FINALIZED
export const GRADE_STATUS = [
  'NOT_SUBMITTED',
  'SUBMITTED',
  'UNDER_SCRUTINY',
  'SCRUTINIZED',
  'APPROVED',
  'FINALIZED',
]
