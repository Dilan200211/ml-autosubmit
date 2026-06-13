'use client';

import { useState, useEffect, useCallback } from 'react';

export default function AccountsPage() {
  const [accounts, setAccounts] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [toasts, setToasts] = useState([]);

  // Form state
  const [formUsername, setFormUsername] = useState('');
  const [formCampaign, setFormCampaign] = useState('');
  const [formPassword, setFormPassword] = useState('');
  const [saving, setSaving] = useState(false);

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
        setAccounts(data.accounts || data || []);
      }
    } catch (err) {
      console.error('Failed to fetch accounts:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchCampaigns = useCallback(async () => {
    try {
      const res = await fetch('/api/campaigns');
      if (res.ok) {
        const data = await res.json();
        setCampaigns(data.campaigns || data || []);
      }
    } catch (err) {
      console.error('Failed to fetch campaigns:', err);
    }
  }, []);

  useEffect(() => {
    fetchAccounts();
    fetchCampaigns();
  }, [fetchAccounts, fetchCampaigns]);

  const handleAddAccount = async (e) => {
    e.preventDefault();
    if (!formUsername.trim() || !formCampaign) {
      addToast('Username and campaign are required', 'error');
      return;
    }

    setSaving(true);
    try {
      const selectedCampaign = campaigns.find(
        (c) => c.id === formCampaign || c.campaignId === formCampaign
      );

      const res = await fetch('/api/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: formUsername.trim(),
          campaign_id: formCampaign,
          campaign_name: selectedCampaign?.name || selectedCampaign?.campaignName || formCampaign,
          campaign_password: formPassword || null,
        }),
      });

      if (res.ok) {
        addToast('Account added!', 'success');
        setFormUsername('');
        setFormCampaign('');
        setFormPassword('');
        setShowModal(false);
        fetchAccounts();
      } else {
        const data = await res.json();
        addToast(data.error || 'Failed to add account', 'error');
      }
    } catch {
      addToast('Network error', 'error');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this account? All queued submissions for it will also be removed.')) return;

    try {
      const res = await fetch(`/api/accounts?id=${id}`, { method: 'DELETE' });
      if (res.ok) {
        addToast('Account deleted', 'success');
        fetchAccounts();
      } else {
        addToast('Failed to delete account', 'error');
      }
    } catch {
      addToast('Network error', 'error');
    }
  };

  const handleToggle = async (id, currentStatus) => {
    try {
      const res = await fetch('/api/accounts', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, is_active: !currentStatus }),
      });

      if (res.ok) {
        addToast(`Account ${currentStatus ? 'deactivated' : 'activated'}`, 'success');
        fetchAccounts();
      } else {
        addToast('Failed to update account', 'error');
      }
    } catch {
      addToast('Network error', 'error');
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
        <h2>Accounts</h2>
        <p>Manage Instagram accounts linked to MonsterLab campaigns</p>
      </div>

      <div className="section-header mb-24">
        <h3>{accounts.length} Account{accounts.length !== 1 ? 's' : ''}</h3>
        <button className="btn btn-primary" onClick={() => setShowModal(true)}>
          ➕ Add Account
        </button>
      </div>

      {/* Account Cards Grid */}
      {loading ? (
        <div className="accounts-grid">
          {[1, 2, 3].map((i) => (
            <div key={i} className="account-card">
              <div className="skeleton skeleton-text" style={{ width: '60%', height: 18 }} />
              <div className="skeleton skeleton-text" style={{ width: '80%', height: 14, marginTop: 12 }} />
              <div className="skeleton skeleton-text" style={{ width: '40%', height: 14, marginTop: 8 }} />
            </div>
          ))}
        </div>
      ) : accounts.length === 0 ? (
        <div className="card-static">
          <div className="empty-state">
            <div className="empty-icon">👤</div>
            <p>No accounts yet. Add an Instagram account to start submitting clips.</p>
          </div>
        </div>
      ) : (
        <div className="accounts-grid">
          {accounts.map((acc) => (
            <div key={acc.id} className="account-card">
              <div className="account-header">
                <span className="account-username">@{acc.username}</span>
                <span className={`badge ${acc.is_active ? 'badge-active' : 'badge-inactive'}`}>
                  {acc.is_active ? '● Active' : '○ Inactive'}
                </span>
              </div>
              <div className="account-campaign">
                📂 {acc.campaign_name || acc.campaign_id}
              </div>
              <div className="text-xs text-muted" style={{ marginBottom: 12 }}>
                🔑 Password: {acc.campaign_password ? '••••••••' : 'Not set'}
              </div>
              <div className="account-actions">
                <button
                  className={`btn btn-sm ${acc.is_active ? 'btn-ghost' : 'btn-secondary'}`}
                  onClick={() => handleToggle(acc.id, acc.is_active)}
                >
                  {acc.is_active ? '⏸ Deactivate' : '▶ Activate'}
                </button>
                <button
                  className="btn btn-sm btn-danger"
                  onClick={() => handleDelete(acc.id)}
                >
                  🗑 Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ── Add Account Modal ── */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>➕ Add Account</h3>
            <form onSubmit={handleAddAccount}>
              <div className="input-group mb-16">
                <label>Instagram Username</label>
                <input
                  type="text"
                  placeholder="username (without @)"
                  value={formUsername}
                  onChange={(e) => setFormUsername(e.target.value)}
                  autoFocus
                />
              </div>

              <div className="input-group mb-16">
                <label>Campaign</label>
                <select
                  value={formCampaign}
                  onChange={(e) => setFormCampaign(e.target.value)}
                >
                  <option value="">Select campaign...</option>
                  {campaigns.map((c) => (
                    <option key={c.id || c.campaignId} value={c.id || c.campaignId}>
                      {c.name || c.campaignName || c.id}
                    </option>
                  ))}
                </select>
              </div>

              <div className="input-group mb-16">
                <label>Password (optional)</label>
                <input
                  type="password"
                  placeholder="Campaign password if required"
                  value={formPassword}
                  onChange={(e) => setFormPassword(e.target.value)}
                />
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => setShowModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={saving}
                >
                  {saving ? '⏳ Saving...' : '✓ Add Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
  );
}
