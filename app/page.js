'use client';

import { useState, useEffect, useCallback } from 'react';

/* ── Toast Helper ── */
function Toast({ toasts, onDismiss }) {
  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`toast toast-${t.type}`}
          onClick={() => onDismiss(t.id)}
        >
          <span>{t.type === 'success' ? '✅' : t.type === 'error' ? '❌' : 'ℹ️'}</span>
          <span>{t.message}</span>
        </div>
      ))}
    </div>
  );
}

/* ── Loading Skeletons ── */
function StatsSkeleton() {
  return (
    <div className="stats-grid">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="stat-card">
          <div className="skeleton skeleton-text shorter" style={{ marginBottom: 12 }} />
          <div className="skeleton skeleton-stat" />
          <div className="skeleton skeleton-text short" />
        </div>
      ))}
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="card-static">
      {[1, 2, 3, 4, 5].map((i) => (
        <div key={i} style={{ display: 'flex', gap: 16, padding: '12px 0', borderBottom: '1px solid rgba(176,38,255,0.06)' }}>
          <div className="skeleton" style={{ width: 60, height: 14 }} />
          <div className="skeleton" style={{ flex: 1, height: 14 }} />
          <div className="skeleton" style={{ width: 100, height: 14 }} />
          <div className="skeleton" style={{ width: 80, height: 14 }} />
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState(null);
  const [recent, setRecent] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [loading, setLoading] = useState(true);

  // Quick submit state
  const [quickUrl, setQuickUrl] = useState('');
  const [quickAccount, setQuickAccount] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const addToast = useCallback((message, type = 'info') => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const fetchData = useCallback(async () => {
    try {
      const [statsRes, historyRes, accountsRes] = await Promise.all([
        fetch('/api/stats'),
        fetch('/api/history?limit=10'),
        fetch('/api/accounts'),
      ]);

      if (statsRes.ok) {
        const data = await statsRes.json();
        setStats(data);
      }

      if (historyRes.ok) {
        const data = await historyRes.json();
        setRecent(data.items || data);
      }

      if (accountsRes.ok) {
        const data = await accountsRes.json();
        setAccounts(data.accounts || data || []);
      }
    } catch (err) {
      console.error('Failed to fetch dashboard data:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleQuickSubmit = async (e) => {
    e.preventDefault();
    if (!quickUrl.trim() || !quickAccount) {
      addToast('Enter a URL and select an account', 'error');
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch('/api/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          urls: [quickUrl.trim()],
          accountId: quickAccount,
        }),
      });

      if (res.ok) {
        addToast('Clip submitted successfully!', 'success');
        setQuickUrl('');
        fetchData();
      } else {
        const data = await res.json();
        addToast(data.error || 'Submission failed', 'error');
      }
    } catch {
      addToast('Network error', 'error');
    } finally {
      setSubmitting(false);
    }
  };

  const formatTime = (dateStr) => {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return d.toLocaleDateString();
  };

  const statusEmoji = (status) => {
    switch (status) {
      case 'success': return '✅';
      case 'failed': return '❌';
      case 'processing': return '⚡';
      case 'pending': return '⏳';
      default: return '•';
    }
  };

  return (
    <>
      <Toast toasts={toasts} onDismiss={dismissToast} />

      <div className="page-header">
        <h2>Dashboard</h2>
        <p>Overview of today&apos;s submissions and activity</p>
      </div>

      {/* ── Stats Cards ── */}
      {loading ? (
        <StatsSkeleton />
      ) : (
        <div className="stats-grid">
          <div className="stat-card total">
            <div className="stat-icon">📦</div>
            <div className="stat-value">{stats?.total ?? 0}</div>
            <div className="stat-label">Total Today</div>
          </div>
          <div className="stat-card pending">
            <div className="stat-icon">⏳</div>
            <div className="stat-value">{stats?.pending ?? 0}</div>
            <div className="stat-label">Pending</div>
          </div>
          <div className="stat-card success">
            <div className="stat-icon">✅</div>
            <div className="stat-value">{stats?.success ?? 0}</div>
            <div className="stat-label">Success</div>
          </div>
          <div className="stat-card failed">
            <div className="stat-icon">❌</div>
            <div className="stat-value">{stats?.failed ?? 0}</div>
            <div className="stat-label">Failed</div>
          </div>
        </div>
      )}

      {/* ── Quick Submit ── */}
      <form className="quick-submit" onSubmit={handleQuickSubmit}>
        <input
          type="url"
          placeholder="Paste clip URL here..."
          value={quickUrl}
          onChange={(e) => setQuickUrl(e.target.value)}
        />
        <select
          value={quickAccount}
          onChange={(e) => setQuickAccount(e.target.value)}
        >
          <option value="">Select account</option>
          {accounts.map((acc) => (
            <option key={acc.id} value={acc.id}>
              {acc.username} — {acc.campaign_name || acc.campaign_id}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="btn btn-primary"
          disabled={submitting}
        >
          {submitting ? '⏳' : '🚀'} Submit
        </button>
      </form>

      {/* ── Recent Submissions ── */}
      <div className="section-header">
        <h3>Recent Submissions</h3>
        <a href="/history" className="btn btn-ghost btn-sm">View All →</a>
      </div>

      {loading ? (
        <TableSkeleton />
      ) : !recent || recent.length === 0 ? (
        <div className="card-static">
          <div className="empty-state">
            <div className="empty-icon">📭</div>
            <p>No submissions yet. Use the form above or go to Submit to get started!</p>
          </div>
        </div>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Status</th>
                <th>URL</th>
                <th>Account</th>
                <th>Time</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((item) => (
                <tr key={item.id}>
                  <td>
                    <span className={`badge badge-${item.status}`}>
                      {statusEmoji(item.status)} {item.status}
                    </span>
                  </td>
                  <td className="url-cell" title={item.url}>{item.url}</td>
                  <td>{item.accounts?.username || item.account_username || '—'}</td>
                  <td className="text-muted text-sm">{formatTime(item.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
