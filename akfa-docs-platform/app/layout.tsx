import type { Metadata, Viewport } from 'next';

import './globals.css';

export const metadata: Metadata = {
  title: {
    default: 'AKFA VPN — база знаний',
    template: '%s | AKFA VPN',
  },
  description: 'Инструкции по подключению AKFA VPN для Android, iPhone, Windows и macOS.',
};

export const viewport: Viewport = {
  themeColor: '#dc171f',
  colorScheme: 'dark',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
