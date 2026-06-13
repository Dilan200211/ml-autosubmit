'use client';

import { useState, useEffect, useCallback } from 'react';

const STATUS_FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'pending', label: '⏳ Pending' },
  { value: 'processing', label: '⚡ Processing' },
  { value: 'success', label: '✅ Success' },
  { value: 'failed', label: '❌ Failed' },
];

export default function HistoryPage() {
  const [items, setItems] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [statusFilter, setStatusFilter] = useState('all');
  const [accountFilter, setAccountFilter] = useState('all');
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const LIMIT = 20;

  const fetchHistory = useCallback(async (offset = 0, append = false) => {
    try {
      let url = `/api/history?limit=${LIMIT}&offset=${offset}`;
      if (statusFilter !== 'all') url += `&status=${statusFilter}`;
      if (accountFilter !== 'all') url += `&accountId=${accountFilter}`;

      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        const newItems = data.items || data || [];

        if (append) {
          setItems((prev) => [...prev, ...newItems]);
        } else {
          setItems(newItems);
        }

        setHasMore(newItems.length === LIMIT);
      }
    } catch (err) {
      console.error('Failed to fetch history:', err);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [statusFilter, accountFilter]);

  const fetchAccounts = useCallback(async () => {
    try {
      const res = await fetch('/api/accounts');
      if (res.ok) {
        const data = await res.json();
        setAccounts(data.accounts || data || []);
      }
    } catch (err) {
      console.error('Failed to fetch accounts:', err);
    }
  }, []);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  useEffect(() => {
    setLoading(true);
    setPage(0);
    fetchHistory(0, false);
  }, [statusFilter, accountFilter, fetchHistory]);

  const handleLoadMore = () => {
    const nextPage = page + 1;
    setPage(nextPage);
    setLoadingMore(true);
    fetchHistory(nextPage * LIMIT, true);
  };

  const formatTime = (dateStr) => {
    if (!dateStr) return '—';
    const d = new Date(dateStr);
    const now = new Date();
    const diff = now - d;
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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
      <div className="page-header">
        <h2>History</h2>
        <p>View all past and current submissions</p>
      </div>

      {/* Filters */}
      <div className="flex gap-16 mb-24" style={{ flexWrap: 'wrap' }}>
        {/* Status Filter */}
        <div className="filter-bar">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              className={`filter-btn ${statusFilter === f.value ? 'active' : ''}`}
              onClick={() => setStatusFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>

        {/* Account Filter */}
        <select
          value={accountFilter}
          onChange={(e) => setAccountFilter(e.target.value)}
          style={{ width: 200, flexShrink: 0 }}
        >
          <option value="all">All Accounts</option>
          {accounts.map((acc) => (
            <option key={acc.id} value={acc.id}>
              @{acc.username}
            </option>
          ))}
        </select>
      </div>

      {/* Table */}
      {loading ? (
        <div className="card-static">
          {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
            <div key={i} style={{ display: 'flex', gap: 16, padding: '14px 0', borderBottom: '1px solid rgba(176,38,255,0.06)' }}>
              <div className="skeleton" style={{ width: 80, height: 14 }} />
              <div className="skeleton" style={{ flex: 1, height: 14 }} />
              <div className="skeleton" style={{ width: 100, height: 14 }} />
              <div className="skeleton" style={{ width: 100, height: 14 }} />
              <div className="skeleton" style={{ width: 80, height: 14 }} />
            </div>
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="card-static">
          <div className="empty-state">
            <div className="empty-icon">📭</div>
            <p>No submissions found with the current filters.</p>
          </div>
        </div>
      ) : (
        <>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Status</th>
                  <th>URL</th>
                  <th>Account</th>
                  <th>Campaign</th>
                  <th>Time</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <span className={`badge badge-${item.status}`}>
                        {statusEmoji(item.status)} {item.status}
                      </span>
                    </td>
                    <td className="url-cell" title={item.url}>
                      {item.url}
                    </td>
                    <td>
                      @{item.accounts?.username || item.account_username || '—'}
                    </td>
                    <td className="text-muted text-sm">
                      {item.accounts?.campaign_name || item.campaign_name || '—'}
                    </td>
                    <td className="text-muted text-sm">
                      {formatTime(item.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Load More */}
          {hasMore && (
            <div className="text-center mt-24">
              <button
                className="btn btn-secondary"
                onClick={handleLoadMore}
                disabled={loadingMore}
              >
                {loadingMore ? '⏳ Loading...' : '↓ Load More'}
              </button>
            </div>
          )}
        </>
      )}

      {/* Summary */}
      {!loading && items.length > 0 && (
        <div className="text-center mt-16 text-sm text-muted">
          Showing {items.length} submission{items.length !== 1 ? 's' : ''}
        </div>
      )}
    </>
  );
}
