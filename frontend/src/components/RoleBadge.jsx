export default function RoleBadge({ role }) {
  if (!role) return <span className="badge badge-none">UNKNOWN</span>
  const cls = {
    ADMIN: 'badge-admin',
    EXAMINER: 'badge-examiner',
    SCRUTINIZER: 'badge-scrutinizer',
    STUDENT: 'badge-student',
  }[role]
  return <span className={`badge ${cls || 'badge-none'}`}>{role}</span>
}
