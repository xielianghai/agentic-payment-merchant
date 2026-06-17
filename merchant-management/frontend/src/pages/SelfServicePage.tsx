import { App as AntdApp, Button, Card, Col, Row, Space, Statistic } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  createDisputeExport,
  getCapabilities,
  getTransactionStats,
  getTrustKeys,
  rotateTrustKey,
} from '@/services/api'

interface Props {
  merchantId: string
  onNavigate: (page: 'capabilities' | 'transactions') => void
}

export function SelfServicePage({ merchantId, onNavigate }: Props) {
  const { t } = useTranslation()
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()

  const statsQuery = useQuery({ queryKey: ['txStats', merchantId], queryFn: () => getTransactionStats(merchantId) })
  const capsQuery = useQuery({ queryKey: ['capabilities', merchantId], queryFn: () => getCapabilities(merchantId) })
  const keysQuery = useQuery({ queryKey: ['trustKeys', merchantId], queryFn: () => getTrustKeys(merchantId) })

  const rotateMutation = useMutation({
    mutationFn: () => rotateTrustKey(merchantId, 'merchant'),
    onSuccess: () => {
      message.success(t('selfService.keyRotated'))
      void queryClient.invalidateQueries({ queryKey: ['trustKeys', merchantId] })
    },
  })
  const exportMutation = useMutation({
    mutationFn: () => createDisputeExport(merchantId, 'merchant'),
    onSuccess: () => { message.success(t('selfService.exportCreated')) },
  })

  const activeKeys = keysQuery.data?.filter((k) => k.status === 'ACTIVE').length ?? 0
  const publishedCaps = capsQuery.data?.filter((c) => c.status === 'PUBLISHED').length ?? 0

  return (
    <div className="page-stack">
      <Card title={t('selfService.title')}>
        <p>{t('selfService.description')}</p>
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={8}>
            <Statistic title={t('selfService.activeKeys')} value={activeKeys} />
          </Col>
          <Col xs={24} sm={8}>
            <Statistic title={t('selfService.publishedSchemas')} value={publishedCaps} />
          </Col>
          <Col xs={24} sm={8}>
            <Statistic title={t('selfService.transactions')} value={statsQuery.data?.total_transactions ?? 0} />
          </Col>
        </Row>
      </Card>

      <Card title={t('selfService.actions')}>
        <Space wrap>
          <Button type="primary" loading={rotateMutation.isPending} onClick={() => rotateMutation.mutate()}>
            {t('selfService.rotateKey')}
          </Button>
          <Button onClick={() => onNavigate('capabilities')}>{t('selfService.manageSchema')}</Button>
          <Button onClick={() => onNavigate('transactions')}>{t('selfService.viewTransactions')}</Button>
          <Button loading={exportMutation.isPending} onClick={() => exportMutation.mutate()}>
            {t('selfService.exportDispute')}
          </Button>
        </Space>
      </Card>
    </div>
  )
}
