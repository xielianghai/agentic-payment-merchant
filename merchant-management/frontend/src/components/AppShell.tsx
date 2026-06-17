import {
  AuditOutlined,
  BarChartOutlined,
  CloudServerOutlined,
  GlobalOutlined,
  KeyOutlined,
  ReconciliationOutlined,
  SafetyCertificateOutlined,
  ShopOutlined,
  SwapOutlined,
  TeamOutlined,
  ThunderboltOutlined,
  UserSwitchOutlined,
} from '@ant-design/icons'
import { ConfigProvider, Layout, Menu, Select, Space, theme } from 'antd'
import zhCN from 'antd/locale/zh_CN'
import enUS from 'antd/locale/en_US'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { MerchantSelector } from '@/components/MerchantSelector'

const { Header, Sider, Content } = Layout

export type PageKey =
  | 'dashboard'
  | 'onboarding'
  | 'merchants'
  | 'capabilities'
  | 'trust'
  | 'certificates'
  | 'selfService'
  | 'transactions'
  | 'reconciliation'
  | 'logs'

interface Props {
  page: PageKey
  onPageChange: (page: PageKey) => void
  merchantId: string
  onMerchantChange: (id: string) => void
  children: React.ReactNode
}

export function AppShell({ page, onPageChange, merchantId, onMerchantChange, children }: Props) {
  const { t, i18n } = useTranslation()
  const locale = i18n.language === 'zh' ? zhCN : enUS

  const menuItems = useMemo(
    () => [
      { key: 'dashboard', icon: <BarChartOutlined />, label: t('nav.dashboard') },
      { key: 'onboarding', icon: <TeamOutlined />, label: t('nav.onboarding') },
      { key: 'merchants', icon: <ShopOutlined />, label: t('nav.merchants') },
      { key: 'capabilities', icon: <ThunderboltOutlined />, label: t('nav.capabilities') },
      { key: 'trust', icon: <KeyOutlined />, label: t('nav.trust') },
      { key: 'certificates', icon: <SafetyCertificateOutlined />, label: t('nav.certificates') },
      { key: 'selfService', icon: <UserSwitchOutlined />, label: t('nav.selfService') },
      { key: 'transactions', icon: <SwapOutlined />, label: t('nav.transactions') },
      { key: 'reconciliation', icon: <ReconciliationOutlined />, label: t('nav.reconciliation') },
      { key: 'logs', icon: <AuditOutlined />, label: t('nav.logs') },
    ],
    [t],
  )

  const showMerchantSelector = !['dashboard', 'merchants', 'logs'].includes(page)

  return (
    <ConfigProvider locale={locale} theme={{ algorithm: theme.defaultAlgorithm }}>
      <Layout className="app-shell">
        <Sider width={240} theme="dark" className="app-sider">
          <div className="app-sider-brand">
            <div className="logo-title">{t('app.title')}</div>
          </div>
          <Menu
            theme="dark"
            mode="inline"
            selectedKeys={[page]}
            items={menuItems}
            onClick={({ key }) => onPageChange(key as PageKey)}
          />
        </Sider>
        <Layout className="app-main">
          <Header className="app-header">
            <Space>
              {showMerchantSelector && (
                <>
                  <CloudServerOutlined />
                  <MerchantSelector value={merchantId} onChange={onMerchantChange} />
                </>
              )}
            </Space>
            <Space className="lang-switcher">
              <GlobalOutlined className="lang-switcher-icon" />
              <Select
                className="lang-switcher-select"
                value={i18n.language.startsWith('zh') ? 'zh' : 'en'}
                onChange={(value) => i18n.changeLanguage(value)}
                options={[
                  { value: 'zh', label: t('lang.zh') },
                  { value: 'en', label: t('lang.en') },
                ]}
              />
            </Space>
          </Header>
          <Content className="app-content">{children}</Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  )
}
