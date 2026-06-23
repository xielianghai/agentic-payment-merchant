import { Card, Drawer, Input, Space, Table } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getOperationLogs } from '@/services/api'
import { JsonPreview } from '@/components/JsonPreview'
import { formatLocalDateTime } from '@/utils/formatDateTime'
import type { OperationLog } from '@/services/api'

interface Props {
  merchantId: string
}

export function LogsPage({ merchantId }: Props) {
  const { t, i18n } = useTranslation()
  const [actionFilter, setActionFilter] = useState<string | undefined>()
  const [selected, setSelected] = useState<OperationLog | null>(null)

  const logsQuery = useQuery({
    queryKey: ['logs', merchantId, actionFilter],
    queryFn: () => getOperationLogs({ merchant_id: merchantId, action: actionFilter, limit: 200 }),
  })

  const columns = [
    { title: t('logs.action'), dataIndex: 'action', key: 'action' },
    { title: t('logs.merchant'), dataIndex: 'merchant_id', key: 'merchant_id' },
    { title: t('logs.actor'), dataIndex: 'actor', key: 'actor' },
    {
      title: t('logs.time'),
      dataIndex: 'created_at',
      key: 'created_at',
      render: (value: string) => formatLocalDateTime(value, i18n.language === 'zh' ? 'zh-CN' : 'en-US'),
    },
  ]

  return (
    <>
      <Card
        title={t('logs.title')}
        extra={
          <Space>
            <Input
              allowClear
              placeholder={t('logs.filterAction')}
              style={{ width: 220 }}
              value={actionFilter}
              onChange={(e) => setActionFilter(e.target.value || undefined)}
            />
          </Space>
        }
      >
        <Table
          rowKey="id"
          loading={logsQuery.isLoading}
          dataSource={logsQuery.data ?? []}
          columns={columns}
          onRow={(record) => ({ onClick: () => setSelected(record), style: { cursor: 'pointer' } })}
        />
      </Card>
      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.action} width={560}>
        {selected && <JsonPreview value={selected.detail_json} />}
      </Drawer>
    </>
  )
}
