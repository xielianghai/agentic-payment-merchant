import { App as AntdApp, Alert, Button, Card, Popconfirm, Space, Table } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  deleteCertificate,
  getCertificates,
  issueCertificate,
  refreshCertAlerts,
  revokeCertificate,
} from '@/services/api'
import { StatusTag } from '@/components/StatusTag'
import type { Certificate } from '@/services/api'
import { formatLocalDateTime } from '@/utils/formatDateTime'

interface Props {
  merchantId: string
}

export function CertificatesPage({ merchantId }: Props) {
  const { t, i18n } = useTranslation()
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()

  const certsQuery = useQuery({ queryKey: ['certificates', merchantId], queryFn: () => getCertificates(merchantId) })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['certificates', merchantId] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    void queryClient.invalidateQueries({ queryKey: ['logs'] })
  }

  const issueMutation = useMutation({
    mutationFn: () => issueCertificate(merchantId),
    onSuccess: () => { message.success(t('certificates.issued')); invalidate() },
  })
  const revokeMutation = useMutation({
    mutationFn: (serialNo: string) => revokeCertificate(merchantId, serialNo),
    onSuccess: () => { message.success(t('certificates.revoked')); invalidate() },
  })
  const deleteMutation = useMutation({
    mutationFn: (serialNo: string) => deleteCertificate(merchantId, serialNo),
    onSuccess: (_data, serialNo) => {
      message.success(t('certificates.deleteSuccess', { serial: serialNo }))
      invalidate()
    },
    onError: (err: Error) => message.error(err.message),
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
    {
      title: t('certificates.notAfter'),
      dataIndex: 'not_after',
      key: 'not_after',
      render: (value: string) => formatLocalDateTime(value, i18n.language === 'zh' ? 'zh-CN' : 'en-US'),
    },
    {
      title: t('certificates.actions'),
      key: 'actions',
      render: (_: unknown, row: Certificate) => (
        <Space wrap>
          <Button
            size="small"
            danger
            disabled={row.status === 'REVOKED'}
            onClick={() => revokeMutation.mutate(row.serial_no)}
          >
            {t('certificates.revoke')}
          </Button>
          {row.status === 'REVOKED' && (
            <Popconfirm
              title={t('certificates.deleteConfirmTitle')}
              description={t('certificates.deleteConfirmDesc', { serial: row.serial_no })}
              okText={t('certificates.deleteConfirmOk')}
              cancelText={t('common.cancel')}
              okButtonProps={{ danger: true, loading: deleteMutation.isPending }}
              onConfirm={() => deleteMutation.mutate(row.serial_no)}
            >
              <Button size="small" danger>{t('certificates.delete')}</Button>
            </Popconfirm>
          )}
        </Space>
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
