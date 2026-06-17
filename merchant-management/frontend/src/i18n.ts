import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'
import en from '@/locales/en.json'
import zh from '@/locales/zh.json'

const storageKey = 'merchant_mgmt_locale'

function initialLanguage() {
  const stored = localStorage.getItem(storageKey)
  return stored === 'zh' || stored === 'en' ? stored : 'zh'
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    zh: { translation: zh },
  },
  lng: initialLanguage(),
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

i18n.on('languageChanged', (lang) => {
  if (lang === 'zh' || lang === 'en') localStorage.setItem(storageKey, lang)
})

export default i18n
