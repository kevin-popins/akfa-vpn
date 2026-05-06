export const publicRouteSlugs = {
  android: 'android-happ',
  iphone: 'iphone-happ',
  windows: 'windows-fclashx',
  macos: 'macos-fclashx',
  faq: 'faq',
} as const;

export const publicRoutes = {
  home: '/',
  docs: '/',
  troubleshooting: `/docs/${publicRouteSlugs.faq}`,
  faq: `/docs/${publicRouteSlugs.faq}`,
  android: `/docs/${publicRouteSlugs.android}`,
  iphone: `/docs/${publicRouteSlugs.iphone}`,
  windows: `/docs/${publicRouteSlugs.windows}`,
  macos: `/docs/${publicRouteSlugs.macos}`,
} as const;

export const platformCards = [
  {
    key: 'android',
    title: 'Android / Happ',
    text: 'Установка Happ, копирование ссылки подключения и первый запуск VPN.',
    href: publicRoutes.android,
  },
  {
    key: 'iphone',
    title: 'iPhone / iPad / Happ',
    text: 'Установка из App Store, добавление профиля и разрешение подключения в iOS.',
    href: publicRoutes.iphone,
  },
  {
    key: 'windows',
    title: 'Windows / FlClashX',
    text: 'Скачивание клиента, импорт ссылки и подключение профиля akfa vpn.',
    href: publicRoutes.windows,
  },
  {
    key: 'macos',
    title: 'macOS / FlClashX',
    text: 'Установка DMG, запуск приложения и добавление профиля по ссылке.',
    href: publicRoutes.macos,
  },
  {
    key: 'faq',
    title: 'FAQ',
    text: 'Лимит устройств, проблемы с подключением и что сообщить администратору.',
    href: publicRoutes.faq,
  },
] as const;
