import { useState } from 'react'
import { AppShell, type PageKey } from '@/components/AppShell'
import { CapabilitiesPage } from '@/pages/CapabilitiesPage'
import { CertificatesPage } from '@/pages/CertificatesPage'
import { DashboardPage } from '@/pages/DashboardPage'
import { LogsPage } from '@/pages/LogsPage'
import { MerchantsPage } from '@/pages/MerchantsPage'
import { OnboardingPage } from '@/pages/OnboardingPage'
import { ReconciliationPage } from '@/pages/ReconciliationPage'
import { SelfServicePage } from '@/pages/SelfServicePage'
import { TransactionsPage } from '@/pages/TransactionsPage'
import { TrustKeysPage } from '@/pages/TrustKeysPage'

export default function App() {
  const [page, setPage] = useState<PageKey>('dashboard')
  const [merchantId, setMerchantId] = useState('heg_flight')

  const navigate = (target: PageKey) => setPage(target)

  const content = (() => {
    switch (page) {
      case 'dashboard':
        return <DashboardPage merchantId={merchantId} />
      case 'onboarding':
        return (
          <OnboardingPage
            merchantId={merchantId}
            onMerchantCreated={setMerchantId}
          />
        )
      case 'merchants':
        return <MerchantsPage />
      case 'capabilities':
        return <CapabilitiesPage merchantId={merchantId} />
      case 'trust':
        return <TrustKeysPage merchantId={merchantId} />
      case 'certificates':
        return <CertificatesPage merchantId={merchantId} />
      case 'selfService':
        return (
          <SelfServicePage
            merchantId={merchantId}
            onNavigate={(p) => navigate(p)}
          />
        )
      case 'transactions':
        return <TransactionsPage merchantId={merchantId} />
      case 'reconciliation':
        return <ReconciliationPage merchantId={merchantId} />
      case 'logs':
        return <LogsPage merchantId={merchantId} />
      default:
        return null
    }
  })()

  return (
    <AppShell
      page={page}
      onPageChange={setPage}
      merchantId={merchantId}
      onMerchantChange={setMerchantId}
    >
      {content}
    </AppShell>
  )
}
