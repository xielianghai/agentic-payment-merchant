import { Card, Drawer, Select, Space, Table } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { getTransactions } from '@/services/api'
import { StatusTag } from '@/components/StatusTag'
import { JsonPreview } from '@/components/JsonPreview'
import type { Transaction } from '@/services/api'

interface Props {
  merchantId: string
}

export function TransactionsPage({ merchantId }: Props) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<string | undefined>()
  const [selected, setSelected] = useState<Transaction | null>(null)

  const txsQuery = useQuery({
    queryKey: ['transactions', merchantId, status],
    queryFn: () => getTransactions(merchantId, status ? { status } : undefined),
  })

  const columns = [
    { title: t('transactions.orderId'), dataIndex: 'order_id', key: 'order_id' },
    { title: t('transactions.mandate'), dataIndex: 'mandate_ref', key: 'mandate_ref' },
    { title: t('transactions.receipt'), dataIndex: 'receipt_ref', key: 'receipt_ref' },
    { title: t('transactions.amount'), key: 'amount', render: (_: unknown, r: Transaction) => `${r.amount} ${r.currency}` },
    {
      title: t('transactions.status'),
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => <StatusTag status={s} />,
    },
    { title: t('transactions.auditIndex'), dataIndex: 'audit_index', key: 'audit_index' },
    { title: t('transactions.occurredAt'), dataIndex: 'occurred_at', key: 'occurred_at' },
  ]

  return (
    <>
      <Card
        title={t('transactions.title')}
        extra={
          <Space>
            <Select
              allowClear
              placeholder={t('transactions.filterStatus')}
              style={{ width: 160 }}
              value={status}
              onChange={setStatus}
              options={[
                { value: 'COMPLETED', label: t('status.COMPLETED') },
                { value: 'FAILED', label: t('status.FAILED') },
              ]}
            />
          </Space>
        }
      >
        <Table
          rowKey="id"
          loading={txsQuery.isLoading}
          dataSource={txsQuery.data ?? []}
          columns={columns}
          onRow={(record) => ({ onClick: () => setSelected(record), style: { cursor: 'pointer' } })}
        />
      </Card>
      <Drawer open={!!selected} onClose={() => setSelected(null)} title={selected?.order_id} width={560}>
        {selected && <JsonPreview value={selected.detail_json} />}
      </Drawer>
    </>
  )
}
