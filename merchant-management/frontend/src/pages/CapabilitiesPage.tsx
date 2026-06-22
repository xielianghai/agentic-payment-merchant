import { App as AntdApp, Button, Card, Descriptions, Drawer, Form, Input, Popconfirm, Space, Table } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createCapability,
  deleteCapability,
  getCapabilities,
  offlineCapability,
  publishCapability,
  validateCapability,
} from '@/services/api'
import { StatusTag } from '@/components/StatusTag'
import { JsonPreview } from '@/components/JsonPreview'
import type { Capability } from '@/services/api'
import {
  DEFAULT_CAPABILITY_VERSION,
  defaultConfigJson,
  defaultLineItemsSchema,
  parseJsonField,
  resolveSchemaUrl,
  stringifyJson,
} from '@/utils/capabilitySchema'

interface Props {
  merchantId: string
}

const CREATE_INITIAL_VALUES = {
  version: DEFAULT_CAPABILITY_VERSION,
  vertical: 'hotel',
  config_json: '{}',
  line_items_schema: stringifyJson(defaultLineItemsSchema('hotel')),
}

export function CapabilitiesPage({ merchantId }: Props) {
  const { t } = useTranslation()
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const [drawerCap, setDrawerCap] = useState<Capability | null>(null)
  const [form] = Form.useForm()
  const watchedCapabilityId = Form.useWatch('capability_id', form)
  const watchedVersion = Form.useWatch('version', form)
  const watchedVertical = Form.useWatch('vertical', form)

  const capsQuery = useQuery({
    queryKey: ['capabilities', merchantId],
    queryFn: () => getCapabilities(merchantId),
  })

  const invalidate = () => void queryClient.invalidateQueries({ queryKey: ['capabilities', merchantId] })

  const applySchemaDefaults = (capabilityId?: string, version?: string, vertical?: string) => {
    const id = (capabilityId ?? '').trim()
    const ver = version || DEFAULT_CAPABILITY_VERSION
    const schemaUrl = resolveSchemaUrl(id, ver)
    if (schemaUrl) {
      form.setFieldValue('schema_url', schemaUrl)
    }
    const config = defaultConfigJson(id)
    if (Object.keys(config).length > 0) {
      form.setFieldValue('config_json', stringifyJson(config))
    }
    const lineItems = defaultLineItemsSchema(vertical)
    if (Object.keys(lineItems).length > 0) {
      form.setFieldValue('line_items_schema', stringifyJson(lineItems))
    }
  }

  const createMutation = useMutation({
    mutationFn: (values: Record<string, string>) => {
      let configJson: Record<string, unknown> = {}
      let lineItemsSchema: Record<string, unknown> = {}
      try {
        configJson = parseJsonField(values.config_json, {})
        lineItemsSchema = parseJsonField(values.line_items_schema, defaultLineItemsSchema(values.vertical))
      } catch {
        throw new Error(t('capabilities.jsonInvalid'))
      }
      return createCapability(merchantId, {
        capability_id: values.capability_id,
        descriptor: values.descriptor,
        vertical: values.vertical,
        description_en: values.description_en,
        description_zh: values.description_zh,
        version: values.version || DEFAULT_CAPABILITY_VERSION,
        schema_url: values.schema_url,
        config_json: configJson,
        line_items_schema: lineItemsSchema,
      })
    },
    onSuccess: () => {
      message.success(t('capabilities.created'))
      invalidate()
      form.resetFields()
      form.setFieldsValue(CREATE_INITIAL_VALUES)
    },
    onError: (err: Error) => message.error(err.message),
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
  const deleteMutation = useMutation({
    mutationFn: (capId: string) => deleteCapability(merchantId, capId),
    onSuccess: (_data, capId) => {
      message.success(t('capabilities.deleteSuccess', { id: capId }))
      if (drawerCap?.capability_id === capId) setDrawerCap(null)
      invalidate()
    },
    onError: (err: Error) => message.error(err.message),
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
          <Popconfirm
            title={t('capabilities.deleteConfirmTitle')}
            description={t('capabilities.deleteConfirmDesc', { id: row.capability_id })}
            okText={t('capabilities.deleteConfirmOk')}
            cancelText={t('common.cancel')}
            okButtonProps={{ danger: true, loading: deleteMutation.isPending }}
            onConfirm={() => deleteMutation.mutate(row.capability_id)}
          >
            <Button size="small" danger>{t('capabilities.delete')}</Button>
          </Popconfirm>
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
        <Form
          form={form}
          layout="vertical"
          initialValues={CREATE_INITIAL_VALUES}
          onFinish={(v) => createMutation.mutate(v)}
        >
          <Form.Item name="capability_id" label={t('capabilities.id')} rules={[{ required: true }]}>
            <Input
              placeholder="dev.ucp.travel.hotel.booking"
              onBlur={() => applySchemaDefaults(watchedCapabilityId, watchedVersion, watchedVertical)}
            />
          </Form.Item>
          <Form.Item name="descriptor" label={t('capabilities.descriptor')} rules={[{ required: true }]}>
            <Input placeholder="hotel_booking" />
          </Form.Item>
          <Form.Item name="vertical" label={t('capabilities.vertical')}>
            <Input
              onBlur={() => {
                const lineItems = defaultLineItemsSchema(form.getFieldValue('vertical'))
                if (Object.keys(lineItems).length > 0) {
                  form.setFieldValue('line_items_schema', stringifyJson(lineItems))
                }
              }}
            />
          </Form.Item>
          <Form.Item name="version" label={t('capabilities.version')} rules={[{ required: true }]}>
            <Input placeholder={DEFAULT_CAPABILITY_VERSION} />
          </Form.Item>
          <Form.Item
            name="schema_url"
            label={t('capabilities.schemaUrl')}
            extra={t('capabilities.schemaUrlHint')}
          >
            <Input placeholder="https://ucp.dev/2026-01-23/schemas/shopping/cart.json" />
          </Form.Item>
          <Form.Item name="description_en" label={t('capabilities.descEn')}>
            <Input />
          </Form.Item>
          <Form.Item name="description_zh" label={t('capabilities.descZh')}>
            <Input />
          </Form.Item>
          <Form.Item
            name="config_json"
            label={t('capabilities.config')}
            extra={t('capabilities.configHint')}
          >
            <Input.TextArea rows={4} placeholder='{"extends": "dev.ucp.shopping.checkout"}' />
          </Form.Item>
          <Form.Item
            name="line_items_schema"
            label={t('capabilities.lineItems')}
            extra={t('capabilities.lineItemsHint')}
          >
            <Input.TextArea rows={4} placeholder='{"type": "hotel", "fields": ["hotel_id", "room_type"]}' />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={createMutation.isPending}>{t('capabilities.create')}</Button>
        </Form>
      </Card>

      <Drawer
        open={!!drawerCap}
        onClose={() => setDrawerCap(null)}
        title={drawerCap?.capability_id}
        width={720}
      >
        {drawerCap && (
          <div className="page-stack">
            <Descriptions bordered size="small" column={1}>
              <Descriptions.Item label={t('capabilities.descriptor')}>{drawerCap.descriptor ?? '—'}</Descriptions.Item>
              <Descriptions.Item label={t('capabilities.vertical')}>{drawerCap.vertical ?? '—'}</Descriptions.Item>
              <Descriptions.Item label={t('capabilities.version')}>{drawerCap.version ?? '—'}</Descriptions.Item>
              <Descriptions.Item label={t('capabilities.status')}>
                <StatusTag status={drawerCap.status} />
              </Descriptions.Item>
              <Descriptions.Item label={t('capabilities.schemaUrl')}>
                {drawerCap.schema_url ? (
                  <a href={drawerCap.schema_url} target="_blank" rel="noreferrer">{drawerCap.schema_url}</a>
                ) : '—'}
              </Descriptions.Item>
              <Descriptions.Item label={t('capabilities.descEn')}>{drawerCap.description_en ?? '—'}</Descriptions.Item>
              <Descriptions.Item label={t('capabilities.descZh')}>{drawerCap.description_zh ?? '—'}</Descriptions.Item>
            </Descriptions>
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
