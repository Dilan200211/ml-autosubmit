'use client';

import './globals.css';
import { usePathname } from 'next/navigation';
import Link from 'next/link';

const NAV_ITEMS = [
  { href: '/', label: 'Dashboard', icon: '📊' },
  { href: '/accounts', label: 'Accounts', icon: '👤' },
  { href: '/submit', label: 'Submit', icon: '🚀' },
  { href: '/history', label: 'History', icon: '📜' },
  { href: '/settings', label: 'Settings', icon: '⚙️' },
];

export default function RootLayout({ children }) {
  const pathname = usePathname();

  return (
    <html lang="en">
      <head>
        <meta charSet="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <meta name="theme-color" content="#0a0e1a" />
        <meta name="description" content="MonsterLab ClipIt Auto-Submit Dashboard" />
        <title>MonsterLab AutoSubmit</title>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>
        <div className="app-layout">
          {/* Sidebar Navigation */}
          <aside className="sidebar">
            <div className="sidebar-logo">
              <h1>🧪 MonsterLab</h1>
              <span>AutoSubmit Dashboard</span>
            </div>

            <nav className="sidebar-nav">
              {NAV_ITEMS.map((item) => {
                const isActive =
                  item.href === '/'
                    ? pathname === '/'
                    : pathname.startsWith(item.href);

                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`nav-link ${isActive ? 'active' : ''}`}
                  >
                    <span className="nav-icon">{item.icon}</span>
                    <span>{item.label}</span>
                  </Link>
                );
              })}
            </nav>
          </aside>

          {/* Main Content */}
          <main className="main-content">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
