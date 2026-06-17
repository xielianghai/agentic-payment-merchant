import { Alert, Card, Col, Row, Statistic, Table } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getDashboard, getMonitoring, getOperationLogs } from '@/services/api'

interface Props {
  merchantId: string
}

export function DashboardPage({ merchantId }: Props) {
  const { t } = useTranslation()
  const dashboardQuery = useQuery({ queryKey: ['dashboard'], queryFn: getDashboard })
  const monitoringQuery = useQuery({
    queryKey: ['monitoring', merchantId],
    queryFn: () => getMonitoring(merchantId),
  })
  const logsQuery = useQuery({ queryKey: ['logs', 'recent'], queryFn: () => getOperationLogs({ limit: 8 }) })

  const cards = [
    ['dashboard.merchantsTotal', 'merchants_total'],
    ['dashboard.merchantsActive', 'merchants_active'],
    ['dashboard.kybPending', 'kyb_pending'],
    ['dashboard.contractsPending', 'contracts_pending'],
    ['dashboard.capabilitiesTotal', 'capabilities_total'],
    ['dashboard.certExpiring', 'cert_expiring'],
    ['dashboard.mandateFailTotal', 'mandate_fail_total'],
    ['dashboard.onboardingPending', 'onboarding_pending'],
  ] as const

  return (
    <div className="page-stack">
      <Row gutter={[16, 16]}>
        {cards.map(([labelKey, dataKey]) => (
          <Col xs={24} sm={12} lg={6} key={dataKey}>
            <Card>
              <Statistic
                title={t(labelKey)}
                value={dashboardQuery.data?.[dataKey] ?? 0}
                loading={dashboardQuery.isLoading}
              />
            </Card>
          </Col>
        ))}
      </Row>

      {monitoringQuery.data?.alerts?.some((a) => a.severity === 'high') && (
        <Alert
          type="error"
          showIcon
          message={t('dashboard.mandateAlert')}
          description={t('dashboard.mandateAlertDesc', {
            count: monitoringQuery.data.transaction_stats.mandate_verify_fail_count,
          })}
        />
      )}

      <Card title={t('dashboard.recentLogs')} className="page-card">
        <Table
          rowKey="id"
          size="small"
          pagination={false}
          loading={logsQuery.isLoading}
          dataSource={logsQuery.data ?? []}
          columns={[
            { title: t('logs.action'), dataIndex: 'action', key: 'action' },
            { title: t('logs.merchant'), dataIndex: 'merchant_id', key: 'merchant_id' },
            { title: t('logs.actor'), dataIndex: 'actor', key: 'actor' },
            { title: t('logs.time'), dataIndex: 'created_at', key: 'created_at' },
          ]}
        />
      </Card>
    </div>
  )
}
