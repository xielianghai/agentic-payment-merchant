import { Select } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { getMerchants } from '@/services/api'

interface Props {
  value: string
  onChange: (value: string) => void
}

export function MerchantSelector({ value, onChange }: Props) {
  const { t, i18n } = useTranslation()
  const merchantsQuery = useQuery({ queryKey: ['merchants'], queryFn: () => getMerchants() })
  const merchants = merchantsQuery.data ?? []

  useEffect(() => {
    if (merchantsQuery.isLoading || merchantsQuery.isFetching) return
    if (!merchants.length) return
    if (!merchants.some((m) => m.id === value)) {
      onChange(merchants[0].id)
    }
  }, [merchants, value, onChange, merchantsQuery.isLoading, merchantsQuery.isFetching])

  return (
    <Select
      style={{ minWidth: 260 }}
      value={merchants.some((m) => m.id === value) ? value : undefined}
      onChange={onChange}
      loading={merchantsQuery.isLoading}
      placeholder={t('common.selectMerchant')}
      options={merchants.map((m) => ({
        value: m.id,
        label: i18n.language === 'zh' ? m.display_name_zh : m.display_name_en,
      }))}
    />
  )
}
