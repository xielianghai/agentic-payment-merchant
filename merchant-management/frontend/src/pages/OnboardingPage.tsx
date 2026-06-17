import { App as AntdApp, Button, Card, Descriptions, Form, Input, Select, Space, Steps, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createMerchant,
  getOnboarding,
  onboardMerchant,
  reviewKyb,
  signContract,
  submitKyb,
} from '@/services/api'
import { StatusTag } from '@/components/StatusTag'

interface Props {
  merchantId: string
  onMerchantCreated?: (merchantId: string) => void
}

export function OnboardingPage({ merchantId, onMerchantCreated }: Props) {
  const { t } = useTranslation()
  const { message } = AntdApp.useApp()
  const queryClient = useQueryClient()
  const [form] = Form.useForm()
  const [createForm] = Form.useForm()
  const [showCreate, setShowCreate] = useState(false)

  const onboardingQuery = useQuery({
    queryKey: ['onboarding', merchantId],
    queryFn: () => getOnboarding(merchantId),
  })

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['onboarding', merchantId] })
    void queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    void queryClient.invalidateQueries({ queryKey: ['merchants'] })
    void queryClient.invalidateQueries({ queryKey: ['logs'] })
  }

  const invalidateAll = () => {
    invalidate()
    void queryClient.invalidateQueries({ queryKey: ['onboarding'] })
  }

  const submitKybMutation = useMutation({
    mutationFn: (values: Record<string, string>) => submitKyb(merchantId, values),
    onSuccess: () => { message.success(t('onboarding.kybSubmitted')); invalidate() },
  })
  const approveKybMutation = useMutation({
    mutationFn: (approved: boolean) => reviewKyb(merchantId, approved),
    onSuccess: () => { message.success(t('onboarding.kybReviewed')); invalidate() },
  })
  const signContractMutation = useMutation({
    mutationFn: () => signContract(merchantId, 'merchant_admin@demo.com'),
    onSuccess: () => { message.success(t('onboarding.contractSigned')); invalidate() },
  })
  const onboardMutation = useMutation({
    mutationFn: () => onboardMerchant(merchantId),
    onSuccess: () => { message.success(t('onboarding.success')); invalidate() },
    onError: (err: Error) => message.error(err.message),
  })
  const createMutation = useMutation({
    mutationFn: (values: {
      name: string
      display_name_en?: string
      display_name_zh?: string
      vertical?: string
      legal_name?: string
      registration_no?: string
      contact_email?: string
      backend_base_url?: string
      country?: string
    }) => createMerchant(values),
    onSuccess: (merchant) => {
      message.success(t('onboarding.merchantCreated', { id: merchant.id }))
      createForm.resetFields()
      setShowCreate(false)
      invalidateAll()
      onMerchantCreated?.(merchant.id)
    },
    onError: (err: Error) => message.error(err.message),
  })

  const data = onboardingQuery.data
  const kyb = data?.kyb
  const contract = data?.contract
  const currentStep = !kyb ? 0 : kyb.status !== 'APPROVED' ? 1 : contract?.status !== 'SIGNED' ? 2 : 3

  return (
    <div className="page-stack">
      <Card
        title={t('onboarding.createTitle')}
        extra={
          <Button type="primary" onClick={() => setShowCreate((v) => !v)}>
            {showCreate ? t('common.cancel') : t('onboarding.createMerchant')}
          </Button>
        }
      >
        {showCreate && (
          <Form
            form={createForm}
            layout="vertical"
            onFinish={(v) => createMutation.mutate(v)}
            initialValues={{ vertical: 'airline', country: 'SG' }}
          >
            <Form.Item name="name" label={t('onboarding.merchantName')} rules={[{ required: true }]}>
              <Input placeholder="Demo Hotel Group" />
            </Form.Item>
            <Form.Item name="display_name_en" label={t('onboarding.displayNameEn')}>
              <Input placeholder="Demo Hotel Group" />
            </Form.Item>
            <Form.Item name="display_name_zh" label={t('onboarding.displayNameZh')}>
              <Input placeholder="演示酒店集团" />
            </Form.Item>
            <Form.Item name="vertical" label={t('onboarding.vertical')} rules={[{ required: true }]}>
              <Select
                options={[
                  { value: 'airline', label: t('onboarding.verticalAirline') },
                  { value: 'hotel', label: t('onboarding.verticalHotel') },
                  { value: 'travel', label: t('onboarding.verticalTravel') },
                ]}
              />
            </Form.Item>
            <Form.Item name="legal_name" label={t('onboarding.legalName')}>
              <Input />
            </Form.Item>
            <Form.Item name="registration_no" label={t('onboarding.registrationNo')}>
              <Input />
            </Form.Item>
            <Form.Item name="contact_email" label={t('onboarding.contactEmail')}>
              <Input />
            </Form.Item>
            <Form.Item name="backend_base_url" label={t('onboarding.backendUrl')}>
              <Input placeholder="http://127.0.0.1:9000" />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={createMutation.isPending}>
              {t('onboarding.createMerchant')}
            </Button>
          </Form>
        )}
        {!showCreate && (
          <Typography.Text type="secondary">{t('onboarding.createHint')}</Typography.Text>
        )}
      </Card>

      <Card title={t('onboarding.title')} loading={onboardingQuery.isLoading}>
        <Typography.Paragraph>{t('onboarding.description')}</Typography.Paragraph>
        <Steps
          current={currentStep}
          items={[
            { title: t('onboarding.stepKyb') },
            { title: t('onboarding.stepReview') },
            { title: t('onboarding.stepContract') },
            { title: t('onboarding.stepActivate') },
          ]}
          style={{ marginBottom: 24 }}
        />

        <Card type="inner" title={t('onboarding.kybTitle')} style={{ marginBottom: 16 }}>
          {kyb ? (
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label={t('onboarding.legalName')}>{kyb.legal_name}</Descriptions.Item>
              <Descriptions.Item label={t('onboarding.registrationNo')}>{kyb.registration_no}</Descriptions.Item>
              <Descriptions.Item label={t('onboarding.vertical')}>{kyb.vertical}</Descriptions.Item>
              <Descriptions.Item label={t('onboarding.status')}><StatusTag status={kyb.status} /></Descriptions.Item>
            </Descriptions>
          ) : (
            <Form form={form} layout="vertical" onFinish={(v) => submitKybMutation.mutate(v)}>
              <Form.Item name="legal_name" label={t('onboarding.legalName')} rules={[{ required: true }]}>
                <Input defaultValue="HEG Flight Pte Ltd" />
              </Form.Item>
              <Form.Item name="registration_no" label={t('onboarding.registrationNo')} rules={[{ required: true }]}>
                <Input defaultValue="201912345A" />
              </Form.Item>
              <Form.Item name="contact_email" label={t('onboarding.contactEmail')} rules={[{ required: true }]}>
                <Input defaultValue="compliance@hegflight.demo" />
              </Form.Item>
              <Form.Item name="vertical" label={t('onboarding.vertical')} initialValue="airline">
                <Input />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={submitKybMutation.isPending}>
                {t('onboarding.submitKyb')}
              </Button>
            </Form>
          )}
          {kyb?.status === 'PENDING' && (
            <Space style={{ marginTop: 16 }}>
              <Button type="primary" loading={approveKybMutation.isPending} onClick={() => approveKybMutation.mutate(true)}>
                {t('onboarding.approveKyb')}
              </Button>
              <Button danger loading={approveKybMutation.isPending} onClick={() => approveKybMutation.mutate(false)}>
                {t('onboarding.rejectKyb')}
              </Button>
            </Space>
          )}
        </Card>

        <Card type="inner" title={t('onboarding.contractTitle')} style={{ marginBottom: 16 }}>
          {contract && (
            <Descriptions bordered size="small" column={1}>
              <Descriptions.Item label={t('onboarding.contractVersion')}>{contract.template_version}</Descriptions.Item>
              <Descriptions.Item label={t('onboarding.status')}><StatusTag status={contract.status} /></Descriptions.Item>
              {contract.signed_at && (
                <Descriptions.Item label={t('onboarding.signedAt')}>{contract.signed_at}</Descriptions.Item>
              )}
            </Descriptions>
          )}
          {contract?.status === 'PENDING' && kyb?.status === 'APPROVED' && (
            <Button type="primary" style={{ marginTop: 16 }} loading={signContractMutation.isPending} onClick={() => signContractMutation.mutate()}>
              {t('onboarding.signContract')}
            </Button>
          )}
        </Card>

        <Button
          type="primary"
          size="large"
          loading={onboardMutation.isPending}
          disabled={contract?.status !== 'SIGNED'}
          onClick={() => onboardMutation.mutate()}
        >
          {t('onboarding.oneClick')}
        </Button>
      </Card>

      {data?.tasks && data.tasks.length > 0 && (
        <Card title={t('onboarding.taskHistory')}>
          {data.tasks.map((task) => (
            <div key={task.id} className="task-row">
              <Space>
                <StatusTag status={task.status} />
                <Typography.Text strong>{task.step}</Typography.Text>
                <Typography.Text type="secondary">{task.created_at}</Typography.Text>
              </Space>
            </div>
          ))}
        </Card>
      )}
    </div>
  )
}
