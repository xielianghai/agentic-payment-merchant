import { App as AntdApp, Alert, Button, Card, Popconfirm, Space, Table } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  deleteTrustKey,
  getExpiryAlerts,
  getTrustKeys,
  registerTrustKey,
  rotateTrustKey,
  verifyTrustKey,
} from '@/services/api'
import { StatusTag } from '@/components/StatusTag'
import type { TrustKey } from '@/services/api'
import { formatLocalDateTime } from '@/utils/formatDateTime'

interface Props {
  merchantId: string
}

export function TrustKeysPage({ merchantId }: Props) {
  const { t, i18n } = useTranslation()
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()

  const keysQuery = useQuery({ queryKey: ['trustKeys', merchantId], queryFn: () => getTrustKeys(merchantId) })
  const alertsQuery = useQuery({ queryKey: ['expiryAlerts', merchantId], queryFn: () => getExpiryAlerts(merchantId) })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['trustKeys', merchantId] })
    void queryClient.invalidateQueries({ queryKey: ['expiryAlerts', merchantId] })
    void queryClient.invalidateQueries({ queryKey: ['logs'] })
  }

  const registerMutation = useMutation({
    mutationFn: () => registerTrustKey(merchantId),
    onSuccess: () => { message.success(t('trust.registered')); invalidate() },
  })
  const rotateMutation = useMutation({
    mutationFn: () => rotateTrustKey(merchantId, 'admin'),
    onSuccess: () => { message.success(t('trust.rotated')); invalidate() },
  })
  const verifyMutation = useMutation({
    mutationFn: (kid: string) => verifyTrustKey(merchantId, kid),
    onSuccess: () => { message.success(t('trust.verified')); invalidate() },
  })
  const deleteMutation = useMutation({
    mutationFn: (kid: string) => deleteTrustKey(merchantId, kid),
    onSuccess: (_data, kid) => {
      message.success(t('trust.deleteSuccess', { kid }))
      invalidate()
    },
    onError: (err: Error) => message.error(err.message),
  })

  const alertItems = alertsQuery.data?.filter((k) => k.alert_status !== 'OK') ?? []

  const columns = [
    { title: 'KID', dataIndex: 'kid', key: 'kid' },
    { title: t('trust.alg'), dataIndex: 'alg', key: 'alg' },
    { title: t('trust.fingerprint'), dataIndex: 'fingerprint', key: 'fingerprint', ellipsis: true },
    {
      title: t('trust.status'),
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <StatusTag status={s} />,
    },
    {
      title: t('trust.expiresAt'),
      dataIndex: 'expires_at',
      key: 'expires_at',
      render: (value: string) => formatLocalDateTime(value, i18n.language === 'zh' ? 'zh-CN' : 'en-US'),
    },
    {
      title: t('trust.actions'),
      key: 'actions',
      render: (_: unknown, row: TrustKey) => (
        <Space wrap>
          <Button size="small" onClick={() => verifyMutation.mutate(row.kid)} disabled={row.status !== 'ACTIVE'}>
            {t('trust.verify')}
          </Button>
          {row.status === 'ROTATED' && (
            <Popconfirm
              title={t('trust.deleteConfirmTitle')}
              description={t('trust.deleteConfirmDesc', { kid: row.kid })}
              okText={t('trust.deleteConfirmOk')}
              cancelText={t('common.cancel')}
              okButtonProps={{ danger: true, loading: deleteMutation.isPending }}
              onConfirm={() => deleteMutation.mutate(row.kid)}
            >
              <Button size="small" danger>{t('trust.delete')}</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div className="page-stack">
      {alertItems.length > 0 && (
        <Alert type="warning" showIcon message={t('trust.expiryAlert')} description={t('trust.expiryAlertDesc', { count: alertItems.length })} />
      )}

      <Card
        title={t('trust.title')}
        extra={
          <Space>
            <Button onClick={() => registerMutation.mutate()} loading={registerMutation.isPending}>{t('trust.register')}</Button>
            <Button type="primary" onClick={() => rotateMutation.mutate()} loading={rotateMutation.isPending}>{t('trust.rotate')}</Button>
          </Space>
        }
      >
        <Table rowKey="id" loading={keysQuery.isLoading} dataSource={keysQuery.data ?? []} columns={columns} />
      </Card>
    </div>
  )
}
