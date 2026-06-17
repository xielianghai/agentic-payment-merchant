import { Select } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getMerchants } from '@/services/api'

interface Props {
  value: string
  onChange: (value: string) => void
}

export function MerchantSelector({ value, onChange }: Props) {
  const { t, i18n } = useTranslation()
  const merchantsQuery = useQuery({ queryKey: ['merchants'], queryFn: () => getMerchants() })

  return (
    <Select
      style={{ minWidth: 260 }}
      value={value}
      onChange={onChange}
      loading={merchantsQuery.isLoading}
      placeholder={t('common.selectMerchant')}
      options={(merchantsQuery.data ?? []).map((m) => ({
        value: m.id,
        label: i18n.language === 'zh' ? m.display_name_zh : m.display_name_en,
      }))}
    />
  )
}
