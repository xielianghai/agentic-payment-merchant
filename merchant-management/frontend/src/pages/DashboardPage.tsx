import { Card, Col, Row, Statistic, Table } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getDashboard, getOperationLogs } from '@/services/api'

interface Props {
  merchantId: string
}

type DashboardStatTone = 'success' | 'warning' | 'danger'

const STAT_TONE_COLORS: Record<DashboardStatTone, string> = {
  success: '#389e0d',
  warning: '#d4b106',
  danger: '#cf1322',
}

const DASHBOARD_CARDS: ReadonlyArray<{
  labelKey: string
  dataKey: string
  tone?: DashboardStatTone
}> = [
  { labelKey: 'dashboard.merchantsTotal', dataKey: 'merchants_total' },
  { labelKey: 'dashboard.merchantsActive', dataKey: 'merchants_active', tone: 'success' },
  { labelKey: 'dashboard.kybPending', dataKey: 'kyb_pending', tone: 'warning' },
  { labelKey: 'dashboard.contractsPending', dataKey: 'contracts_pending', tone: 'warning' },
  { labelKey: 'dashboard.capabilitiesTotal', dataKey: 'capabilities_total' },
  { labelKey: 'dashboard.certExpiring', dataKey: 'cert_expiring', tone: 'danger' },
  { labelKey: 'dashboard.mandateFailTotal', dataKey: 'mandate_fail_total', tone: 'danger' },
  { labelKey: 'dashboard.onboardingPending', dataKey: 'onboarding_pending', tone: 'warning' },
]

export function DashboardPage({ merchantId }: Props) {
  const { t } = useTranslation()
  const dashboardQuery = useQuery({ queryKey: ['dashboard'], queryFn: getDashboard })
  const logsQuery = useQuery({ queryKey: ['logs', 'recent'], queryFn: () => getOperationLogs({ limit: 8 }) })

  const cards = DASHBOARD_CARDS

  return (
    <div className="page-stack">
      <Row gutter={[16, 16]}>
        {cards.map(({ labelKey, dataKey, tone }) => (
          <Col xs={24} sm={12} lg={6} key={dataKey}>
            <Card className={tone ? `dashboard-stat dashboard-stat--${tone}` : 'dashboard-stat'}>
              <Statistic
                title={t(labelKey)}
                value={dashboardQuery.data?.[dataKey as keyof typeof dashboardQuery.data] ?? 0}
                loading={dashboardQuery.isLoading}
                valueStyle={tone ? { color: STAT_TONE_COLORS[tone] } : undefined}
              />
            </Card>
          </Col>
        ))}
      </Row>

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
