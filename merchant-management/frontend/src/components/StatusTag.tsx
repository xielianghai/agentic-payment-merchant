import { Tag } from 'antd'
import { useTranslation } from 'react-i18next'

const colorMap: Record<string, string> = {
  ACTIVE: 'green',
  DISABLED: 'default',
  PUBLISHED: 'green',
  COMPLETED: 'green',
  SIGNED: 'green',
  APPROVED: 'green',
  MATCHED: 'green',
  VALIDATED: 'blue',
  PENDING: 'orange',
  DRAFT: 'default',
  FAILED: 'red',
  REJECTED: 'red',
  REVOKED: 'red',
  OFFLINE: 'default',
  MISMATCH: 'red',
  EXPIRING_SOON: 'orange',
  EXPIRED: 'red',
}

export function StatusTag({ status }: { status: string }) {
  const { t } = useTranslation()
  const key = `status.${status}`
  const label = t(key, status)
  return <Tag color={colorMap[status] || 'default'}>{label}</Tag>
}
