import { App as AntdApp, Button, Card, Drawer, Popconfirm, Space, Table } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { deleteMerchant, disableMerchant, enableMerchant, getMerchant, getMerchants, onboardMerchant } from '@/services/api'
import { StatusTag } from '@/components/StatusTag'
import { JsonPreview } from '@/components/JsonPreview'
import type { Merchant } from '@/services/api'

export function MerchantsPage() {
  const { t, i18n } = useTranslation()
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const [detailId, setDetailId] = useState<string | null>(null)

  const merchantsQuery = useQuery({ queryKey: ['merchants'], queryFn: () => getMerchants() })
  const detailQuery = useQuery({
    queryKey: ['merchant', detailId],
    queryFn: () => getMerchant(detailId!),
    enabled: !!detailId,
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['merchants'] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    void queryClient.invalidateQueries({ queryKey: ['logs'] })
  }

  const onboardMutation = useMutation({
    mutationFn: onboardMerchant,
    onSuccess: () => invalidate(),
  })

  const disableMutation = useMutation({
    mutationFn: disableMerchant,
    onSuccess: (_data, merchantId) => {
      message.success(t('merchants.disableSuccess', { id: merchantId }))
      invalidate()
    },
    onError: (err: Error) => message.error(err.message),
  })

  const enableMutation = useMutation({
    mutationFn: enableMerchant,
    onSuccess: (_data, merchantId) => {
      message.success(t('merchants.enableSuccess', { id: merchantId }))
      invalidate()
    },
    onError: (err: Error) => message.error(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteMerchant,
    onSuccess: (_data, merchantId) => {
      message.success(t('merchants.deleteSuccess', { id: merchantId }))
      if (detailId === merchantId) setDetailId(null)
      invalidate()
    },
    onError: (err: Error) => message.error(err.message),
  })

  const columns = [
    { title: t('merchants.id'), dataIndex: 'id', key: 'id' },
    {
      title: t('merchants.name'),
      key: 'name',
      render: (_: unknown, row: Merchant) =>
        i18n.language === 'zh' ? row.display_name_zh : row.display_name_en,
    },
    {
      title: t('merchants.status'),
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => <StatusTag status={status} />,
    },
    {
      title: t('merchants.protocols'),
      dataIndex: 'protocols',
      key: 'protocols',
      render: (protocols: string[]) => protocols.join(', '),
    },
    { title: t('merchants.backend'), dataIndex: 'backend_base_url', key: 'backend' },
    {
      title: t('merchants.actions'),
      key: 'actions',
      render: (_: unknown, row: Merchant) => (
        <Space size={0} className="merchant-table-actions">
          <Button type="link" size="small" onClick={() => setDetailId(row.id)}>{t('merchants.view')}</Button>
          {row.status === 'PENDING' && (
            <Button type="link" size="small" loading={onboardMutation.isPending} onClick={() => onboardMutation.mutate(row.id)}>
              {t('merchants.onboard')}
            </Button>
          )}
          {row.status === 'ACTIVE' && (
            <Popconfirm
              title={t('merchants.disableConfirmTitle')}
              description={t('merchants.disableConfirmDesc', {
                name: i18n.language === 'zh' ? row.display_name_zh : row.display_name_en,
                id: row.id,
              })}
              okText={t('merchants.disableConfirmOk')}
              cancelText={t('common.cancel')}
              okButtonProps={{ danger: true, loading: disableMutation.isPending }}
              overlayClassName="merchant-disable-popconfirm"
              overlayInnerStyle={{ maxWidth: 360 }}
              onConfirm={() => disableMutation.mutate(row.id)}
            >
              <Button type="link" size="small" danger loading={disableMutation.isPending}>
                {t('merchants.disable')}
              </Button>
            </Popconfirm>
          )}
          {row.status === 'DISABLED' && (
            <Button type="link" size="small" loading={enableMutation.isPending} onClick={() => enableMutation.mutate(row.id)}>
              {t('merchants.enable')}
            </Button>
          )}
          <Popconfirm
            title={t('merchants.deleteConfirmTitle')}
            description={t('merchants.deleteConfirmDesc', {
              name: i18n.language === 'zh' ? row.display_name_zh : row.display_name_en,
              id: row.id,
            })}
            okText={t('merchants.deleteConfirmOk')}
            cancelText={t('common.cancel')}
            okButtonProps={{ danger: true, loading: deleteMutation.isPending }}
            overlayClassName="merchant-delete-popconfirm"
            overlayInnerStyle={{ maxWidth: 360 }}
            onConfirm={() => deleteMutation.mutate(row.id)}
          >
            <Button type="link" size="small" danger loading={deleteMutation.isPending}>
              {t('merchants.delete')}
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <>
      <Card title={t('merchants.title')} className="page-card">
        <Table rowKey="id" loading={merchantsQuery.isLoading} dataSource={merchantsQuery.data ?? []} columns={columns} />
      </Card>
      <Drawer open={!!detailId} onClose={() => setDetailId(null)} title={detailId ?? ''} width={560}>
        {detailQuery.data && (
          <div className="page-stack">
            <p><strong>{t('merchants.status')}:</strong> <StatusTag status={detailQuery.data.status} /></p>
            <p><strong>A2A:</strong> {detailQuery.data.a2a_endpoint}</p>
            <p><strong>UCP:</strong> {detailQuery.data.ucp_profile_url}</p>
            <p><strong>JWKS:</strong> {detailQuery.data.jwks_url}</p>
            <JsonPreview value={detailQuery.data.capabilities_json} />
          </div>
        )}
      </Drawer>
    </>
  )
}
