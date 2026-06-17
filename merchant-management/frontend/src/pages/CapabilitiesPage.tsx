import { App as AntdApp, Button, Card, Drawer, Form, Input, Space, Table } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createCapability,
  getCapabilities,
  offlineCapability,
  publishCapability,
  validateCapability,
} from '@/services/api'
import { StatusTag } from '@/components/StatusTag'
import { JsonPreview } from '@/components/JsonPreview'
import type { Capability } from '@/services/api'

interface Props {
  merchantId: string
}

export function CapabilitiesPage({ merchantId }: Props) {
  const { t, i18n } = useTranslation()
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const [drawerCap, setDrawerCap] = useState<Capability | null>(null)
  const [form] = Form.useForm()

  const capsQuery = useQuery({
    queryKey: ['capabilities', merchantId],
    queryFn: () => getCapabilities(merchantId),
  })

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['capabilities', merchantId] })

  const createMutation = useMutation({
    mutationFn: (values: Partial<Capability>) => createCapability(merchantId, values),
    onSuccess: () => { message.success(t('capabilities.created')); invalidate(); form.resetFields() },
  })
  const validateMutation = useMutation({
    mutationFn: (capId: string) => validateCapability(merchantId, capId),
    onSuccess: () => { message.success(t('capabilities.validated')); invalidate() },
  })
  const publishMutation = useMutation({
    mutationFn: (capId: string) => publishCapability(merchantId, capId),
    onSuccess: () => { message.success(t('capabilities.published')); invalidate() },
  })
  const offlineMutation = useMutation({
    mutationFn: (capId: string) => offlineCapability(merchantId, capId),
    onSuccess: () => { message.success(t('capabilities.offline')); invalidate() },
  })

  const columns = [
    { title: t('capabilities.id'), dataIndex: 'capability_id', key: 'capability_id' },
    { title: t('capabilities.descriptor'), dataIndex: 'descriptor', key: 'descriptor' },
    { title: t('capabilities.vertical'), dataIndex: 'vertical', key: 'vertical' },
    { title: t('capabilities.version'), dataIndex: 'version', key: 'version' },
    {
      title: t('capabilities.status'),
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <StatusTag status={s} />,
    },
    {
      title: t('capabilities.actions'),
      key: 'actions',
      render: (_: unknown, row: Capability) => (
        <Space wrap>
          <Button size="small" onClick={() => setDrawerCap(row)}>{t('common.view')}</Button>
          <Button size="small" onClick={() => validateMutation.mutate(row.capability_id)}>{t('capabilities.validate')}</Button>
          <Button size="small" type="primary" onClick={() => publishMutation.mutate(row.capability_id)}>{t('capabilities.publish')}</Button>
          <Button size="small" danger onClick={() => offlineMutation.mutate(row.capability_id)}>{t('capabilities.offlineAction')}</Button>
        </Space>
      ),
    },
  ]

  return (
    <div className="page-stack">
      <Card title={t('capabilities.title')} loading={capsQuery.isLoading}>
        <Table rowKey="id" dataSource={capsQuery.data ?? []} columns={columns} />
      </Card>

      <Card title={t('capabilities.createTitle')}>
        <Form form={form} layout="vertical" onFinish={(v) => createMutation.mutate(v)}>
          <Form.Item name="capability_id" label={t('capabilities.id')} rules={[{ required: true }]}>
            <Input placeholder="dev.ucp.travel.hotel.booking" />
          </Form.Item>
          <Form.Item name="descriptor" label={t('capabilities.descriptor')} rules={[{ required: true }]}>
            <Input placeholder="hotel_booking" />
          </Form.Item>
          <Form.Item name="vertical" label={t('capabilities.vertical')} initialValue="hotel">
            <Input />
          </Form.Item>
          <Form.Item name="description_en" label={t('capabilities.descEn')}>
            <Input />
          </Form.Item>
          <Form.Item name="description_zh" label={t('capabilities.descZh')}>
            <Input />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={createMutation.isPending}>{t('capabilities.create')}</Button>
        </Form>
      </Card>

      <Drawer
        open={!!drawerCap}
        onClose={() => setDrawerCap(null)}
        title={drawerCap?.capability_id}
        width={640}
      >
        {drawerCap && (
          <div className="page-stack">
            <p>{i18n.language === 'zh' ? drawerCap.description_zh : drawerCap.description_en}</p>
            <h4>{t('capabilities.lineItems')}</h4>
            <JsonPreview value={drawerCap.line_items_schema} />
            <h4>{t('capabilities.config')}</h4>
            <JsonPreview value={drawerCap.config_json} />
          </div>
        )}
      </Drawer>
    </div>
  )
}
