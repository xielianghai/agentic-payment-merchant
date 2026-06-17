import { App as AntdApp, Alert, Button, Card, Space, Table } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getCertificates, issueCertificate, refreshCertAlerts, revokeCertificate } from '@/services/api'
import { StatusTag } from '@/components/StatusTag'
import type { Certificate } from '@/services/api'

interface Props {
  merchantId: string
}

export function CertificatesPage({ merchantId }: Props) {
  const { t } = useTranslation()
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()

  const certsQuery = useQuery({ queryKey: ['certificates', merchantId], queryFn: () => getCertificates(merchantId) })

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['certificates', merchantId] })

  const issueMutation = useMutation({
    mutationFn: () => issueCertificate(merchantId),
    onSuccess: () => { message.success(t('certificates.issued')); invalidate() },
  })
  const revokeMutation = useMutation({
    mutationFn: (serialNo: string) => revokeCertificate(merchantId, serialNo),
    onSuccess: () => { message.success(t('certificates.revoked')); invalidate() },
  })
  const refreshMutation = useMutation({
    mutationFn: () => refreshCertAlerts(merchantId),
    onSuccess: () => { message.success(t('certificates.alertsRefreshed')); invalidate() },
  })

  const expiring = certsQuery.data?.filter((c) => c.alert_status === 'EXPIRING_SOON' || c.alert_status === 'EXPIRED') ?? []

  const columns = [
    { title: t('certificates.serial'), dataIndex: 'serial_no', key: 'serial_no' },
    { title: t('certificates.subject'), dataIndex: 'subject_cn', key: 'subject_cn' },
    { title: t('certificates.issuer'), dataIndex: 'issuer_cn', key: 'issuer_cn' },
    {
      title: t('certificates.status'),
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <StatusTag status={s} />,
    },
    {
      title: t('certificates.alert'),
      dataIndex: 'alert_status',
      key: 'alert_status',
      render: (s: string) => <StatusTag status={s} />,
    },
    { title: t('certificates.notAfter'), dataIndex: 'not_after', key: 'not_after' },
    {
      title: t('certificates.actions'),
      key: 'actions',
      render: (_: unknown, row: Certificate) => (
        <Button size="small" danger disabled={row.status === 'REVOKED'} onClick={() => revokeMutation.mutate(row.serial_no)}>
          {t('certificates.revoke')}
        </Button>
      ),
    },
  ]

  return (
    <div className="page-stack">
      {expiring.length > 0 && (
        <Alert type="warning" showIcon message={t('certificates.expiryAlert')} description={t('certificates.expiryAlertDesc', { count: expiring.length })} />
      )}
      <Card
        title={t('certificates.title')}
        extra={
          <Space>
            <Button onClick={() => refreshMutation.mutate()} loading={refreshMutation.isPending}>{t('certificates.refreshAlerts')}</Button>
            <Button type="primary" onClick={() => issueMutation.mutate()} loading={issueMutation.isPending}>{t('certificates.issue')}</Button>
          </Space>
        }
      >
        <Table rowKey="id" loading={certsQuery.isLoading} dataSource={certsQuery.data ?? []} columns={columns} />
      </Card>
    </div>
  )
}
