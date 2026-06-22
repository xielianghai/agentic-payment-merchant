import { App as AntdApp, Button, Card, Col, Drawer, Row, Space, Statistic, Table } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createDisputeExport,
  getMonitoring,
  getReconciliationRuns,
  runReconciliation,
} from '@/services/api'
import { StatusTag } from '@/components/StatusTag'
import { JsonPreview } from '@/components/JsonPreview'
import type { ReconciliationRun } from '@/services/api'

interface Props {
  merchantId: string
}

export function ReconciliationPage({ merchantId }: Props) {
  const { t } = useTranslation()
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const [selectedRun, setSelectedRun] = useState<ReconciliationRun | null>(null)

  const monitoringQuery = useQuery({ queryKey: ['monitoring', merchantId], queryFn: () => getMonitoring(merchantId) })
  const runsQuery = useQuery({ queryKey: ['reconciliation', merchantId], queryFn: () => getReconciliationRuns(merchantId) })

  const runMutation = useMutation({
    mutationFn: () => runReconciliation(merchantId),
    onSuccess: () => {
      message.success(t('reconciliation.runSuccess'))
      void queryClient.invalidateQueries({ queryKey: ['reconciliation', merchantId] })
      void queryClient.invalidateQueries({ queryKey: ['monitoring', merchantId] })
    },
  })
  const exportMutation = useMutation({
    mutationFn: () => createDisputeExport(merchantId),
    onSuccess: () => message.success(t('reconciliation.exportSuccess')),
  })

  const stats = monitoringQuery.data?.transaction_stats

  const columns = [
    { title: 'ID', dataIndex: 'id', key: 'id' },
    { title: t('reconciliation.total'), dataIndex: 'total_items', key: 'total_items' },
    { title: t('reconciliation.matched'), dataIndex: 'matched_items', key: 'matched_items' },
    { title: t('reconciliation.mismatch'), dataIndex: 'mismatch_items', key: 'mismatch_items' },
    { title: t('reconciliation.mandateFail'), dataIndex: 'mandate_verify_fail_count', key: 'mandate_fail' },
    { title: t('reconciliation.completedAt'), dataIndex: 'completed_at', key: 'completed_at' },
    {
      title: t('reconciliation.actions'),
      key: 'actions',
      render: (_: unknown, row: ReconciliationRun) => (
        <Button size="small" onClick={() => setSelectedRun(row)}>{t('common.view')}</Button>
      ),
    },
  ]

  return (
    <div className="page-stack">
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={6}><Card><Statistic title={t('reconciliation.txTotal')} value={stats?.total_transactions ?? 0} /></Card></Col>
        <Col xs={24} sm={6}><Card><Statistic title={t('reconciliation.txCompleted')} value={stats?.completed_transactions ?? 0} /></Card></Col>
        <Col xs={24} sm={6}><Card><Statistic title={t('reconciliation.receiptIndex')} value={stats?.receipt_index_count ?? 0} /></Card></Col>
        <Col xs={24} sm={6}><Card><Statistic title={t('reconciliation.mandateFail')} value={stats?.mandate_verify_fail_count ?? 0} /></Card></Col>
      </Row>

      <Card
        title={t('reconciliation.title')}
        extra={
          <Space>
            <Button type="primary" loading={runMutation.isPending} onClick={() => runMutation.mutate()}>{t('reconciliation.run')}</Button>
            <Button loading={exportMutation.isPending} onClick={() => exportMutation.mutate()}>{t('reconciliation.export')}</Button>
          </Space>
        }
      >
        <Table rowKey="id" loading={runsQuery.isLoading} dataSource={runsQuery.data ?? []} columns={columns} />
      </Card>

      <Drawer open={!!selectedRun} onClose={() => setSelectedRun(null)} title={t('reconciliation.runDetail')} width={720}>
        {selectedRun && (
          <div className="page-stack">
            <h4>{t('reconciliation.fileSummary')}</h4>
            <JsonPreview value={selectedRun.file_summary_json} />
            <h4>{t('reconciliation.items')}</h4>
            <Table
              rowKey="id"
              size="small"
              dataSource={selectedRun.items ?? []}
              columns={[
                { title: t('transactions.orderId'), dataIndex: 'order_id' },
                { title: t('transactions.mandate'), dataIndex: 'mandate_ref' },
                { title: t('transactions.receipt'), dataIndex: 'receipt_ref' },
                { title: t('transactions.status'), dataIndex: 'status', render: (s: string) => <StatusTag status={s} /> },
                { title: t('reconciliation.reason'), dataIndex: 'mismatch_reason' },
              ]}
            />
          </div>
        )}
      </Drawer>
    </div>
  )
}
