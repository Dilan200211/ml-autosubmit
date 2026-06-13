'use client';

import { useState, useEffect, useCallback } from 'react';

export default function SubmitPage() {
  const [accounts, setAccounts] = useState([]);
  const [selectedAccount, setSelectedAccount] = useState('');
  const [singleUrl, setSingleUrl] = useState('');
  const [bulkUrls, setBulkUrls] = useState('');
  const [queue, setQueue] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [submittingBulk, setSubmittingBulk] = useState(false);
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type = 'info') => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  const fetchAccounts = useCallback(async () => {
    try {
      const res = await fetch('/api/accounts');
      if (res.ok) {
        const data = await res.json();
        const accs = (data.accounts || data || []).filter((a) => a.is_active);
        setAccounts(accs);
        if (accs.length > 0 && !selectedAccount) {
          setSelectedAccount(accs[0].id);
        }
      }
    } catch (err) {
      console.error('Failed to fetch accounts:', err);
    }
  }, [selectedAccount]);

  const fetchQueue = useCallback(async () => {
    try {
      const res = await fetch('/api/history?status=pending&limit=20');
      if (res.ok) {
        const data = await res.json();
        setQueue(data.items || data || []);
      }
    } catch (err) {
      console.error('Failed to fetch queue:', err);
    }
  }, []);

  useEffect(() => {
    fetchAccounts();
    fetchQueue();
    const interval = setInterval(fetchQueue, 10000);
    return () => clearInterval(interval);
  }, [fetchAccounts, fetchQueue]);

  const handleSingleSubmit = async (e) => {
    e.preventDefault();
    if (!singleUrl.trim()) {
      addToast('Please enter a URL', 'error');
      return;
    }
    if (!selectedAccount) {
      addToast('Please select an account', 'error');
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch('/api/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          urls: [singleUrl.trim()],
          accountId: selectedAccount,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        addToast(`Submitted! ${data.queued || 1} clip queued`, 'success');
        setSingleUrl('');
        fetchQueue();
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

  const handleBulkSubmit = async () => {
    const urls = bulkUrls
      .split('\n')
      .map((u) => u.trim())
      .filter((u) => u.length > 0);

    if (urls.length === 0) {
      addToast('Paste at least one URL', 'error');
      return;
    }
    if (!selectedAccount) {
      addToast('Please select an account', 'error');
      return;
    }

    setSubmittingBulk(true);
    try {
      const res = await fetch('/api/submit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          urls,
          accountId: selectedAccount,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        addToast(`Bulk submitted! ${data.queued || urls.length} clips queued`, 'success');
        setBulkUrls('');
        fetchQueue();
      } else {
        const data = await res.json();
        addToast(data.error || 'Bulk submission failed', 'error');
      }
    } catch {
      addToast('Network error', 'error');
    } finally {
      setSubmittingBulk(false);
    }
  };

  const lineCount = bulkUrls.split('\n').filter((l) => l.trim()).length;

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
      {/* Toasts */}
      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            <span>{t.type === 'success' ? '✅' : t.type === 'error' ? '❌' : 'ℹ️'}</span>
            <span>{t.message}</span>
          </div>
        ))}
      </div>

      <div className="page-header">
        <h2>Submit Clips</h2>
        <p>Submit single or multiple clip URLs for processing</p>
      </div>

      {/* Account Selector */}
      <div className="card-static mb-24">
        <div className="input-group">
          <label>Account</label>
          <select
            value={selectedAccount}
            onChange={(e) => setSelectedAccount(e.target.value)}
          >
            <option value="">Select account...</option>
            {accounts.map((acc) => (
              <option key={acc.id} value={acc.id}>
                @{acc.username} — {acc.campaign_name || acc.campaign_id}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Single URL Submit */}
      <div className="card-static mb-24">
        <h3 style={{ marginBottom: 16, fontSize: '1rem' }}>🔗 Single URL</h3>
        <form onSubmit={handleSingleSubmit} className="form-row">
          <div className="input-group">
            <input
              type="url"
              placeholder="https://www.instagram.com/reel/..."
              value={singleUrl}
              onChange={(e) => setSingleUrl(e.target.value)}
            />
          </div>
          <button
            type="submit"
            className="btn btn-primary"
            disabled={submitting}
          >
            {submitting ? '⏳ Submitting...' : '🚀 Submit'}
          </button>
        </form>
      </div>

      {/* Bulk URL Submit */}
      <div className="card-static mb-24">
        <div className="section-header" style={{ marginBottom: 16 }}>
          <h3 style={{ fontSize: '1rem' }}>📋 Bulk Submit</h3>
          {lineCount > 0 && (
            <span className="badge badge-pending">{lineCount} URL{lineCount !== 1 ? 's' : ''}</span>
          )}
        </div>
        <div className="input-group">
          <textarea
            placeholder={"Paste multiple URLs, one per line:\nhttps://www.instagram.com/reel/abc...\nhttps://www.instagram.com/reel/def...\nhttps://www.tiktok.com/@user/video/..."}
            value={bulkUrls}
            onChange={(e) => setBulkUrls(e.target.value)}
            rows={6}
          />
        </div>
        <div style={{ marginTop: 16, display: 'flex', justifyContent: 'flex-end' }}>
          <button
            className="btn btn-success btn-lg"
            onClick={handleBulkSubmit}
            disabled={submittingBulk || lineCount === 0}
          >
            {submittingBulk ? '⏳ Submitting...' : `🚀 Submit All (${lineCount})`}
          </button>
        </div>
      </div>

      {/* Live Queue */}
      <div className="section-header">
        <h3>⏳ Pending Queue</h3>
        <span className="text-sm text-muted">{queue.length} item{queue.length !== 1 ? 's' : ''}</span>
      </div>

      {queue.length === 0 ? (
        <div className="card-static">
          <div className="empty-state">
            <div className="empty-icon">✨</div>
            <p>Queue is empty — all caught up!</p>
          </div>
        </div>
      ) : (
        <div className="queue-list">
          {queue.map((item) => (
            <div key={item.id} className="queue-item">
              <span>{statusEmoji(item.status)}</span>
              <span className="queue-url" title={item.url}>{item.url}</span>
              <span className={`badge badge-${item.status}`}>{item.status}</span>
            </div>
          ))}
        </div>
      )}
    </>
  );
}
