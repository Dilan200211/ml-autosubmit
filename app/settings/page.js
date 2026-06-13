'use client';

import { useState, useEffect, useCallback } from 'react';

export default function SettingsPage() {
  const [settings, setSettings] = useState({
    monsterlab_api_key: '',
    whatsapp_phone: '',
    whatsapp_api_key: '',
  });

  const [pin, setPin] = useState('');
  const [pinConfirm, setPinConfirm] = useState('');
  const [loading, setLoading] = useState(true);
  const [toasts, setToasts] = useState([]);

  // Show/hide toggles
  const [showApiKey, setShowApiKey] = useState(false);
  const [showWhatsappKey, setShowWhatsappKey] = useState(false);
  const [showPin, setShowPin] = useState(false);

  // Saving states
  const [savingApi, setSavingApi] = useState(false);
  const [savingWhatsapp, setSavingWhatsapp] = useState(false);
  const [savingPin, setSavingPin] = useState(false);
  const [testingNotif, setTestingNotif] = useState(false);

  const addToast = useCallback((message, type = 'info') => {
    const id = Date.now();
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000);
  }, []);

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await fetch('/api/settings');
        if (res.ok) {
          const data = await res.json();
          const s = {};
          if (Array.isArray(data)) {
            data.forEach((item) => {
              s[item.key] = item.value;
            });
          } else if (data.settings) {
            Object.assign(s, data.settings);
          } else {
            Object.assign(s, data);
          }
          setSettings((prev) => ({ ...prev, ...s }));
        }
      } catch (err) {
        console.error('Failed to fetch settings:', err);
      } finally {
        setLoading(false);
      }
    };

    fetchSettings();
  }, []);

  const saveSetting = async (key, value) => {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value }),
    });
    return res.ok;
  };

  const handleSaveApiKey = async () => {
    setSavingApi(true);
    try {
      const ok = await saveSetting('monsterlab_api_key', settings.monsterlab_api_key);
      addToast(ok ? 'API key saved!' : 'Failed to save API key', ok ? 'success' : 'error');
    } catch {
      addToast('Network error', 'error');
    } finally {
      setSavingApi(false);
    }
  };

  const handleSaveWhatsapp = async () => {
    setSavingWhatsapp(true);
    try {
      const ok1 = await saveSetting('whatsapp_phone', settings.whatsapp_phone);
      const ok2 = await saveSetting('whatsapp_api_key', settings.whatsapp_api_key);
      addToast(ok1 && ok2 ? 'WhatsApp settings saved!' : 'Failed to save some settings', ok1 && ok2 ? 'success' : 'error');
    } catch {
      addToast('Network error', 'error');
    } finally {
      setSavingWhatsapp(false);
    }
  };

  const handleTestNotification = async () => {
    setTestingNotif(true);
    try {
      const res = await fetch('/api/settings/test-notification', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });

      if (res.ok) {
        addToast('Test notification sent! Check your WhatsApp.', 'success');
      } else {
        const data = await res.json();
        addToast(data.error || 'Failed to send test notification', 'error');
      }
    } catch {
      addToast('Network error', 'error');
    } finally {
      setTestingNotif(false);
    }
  };

  const handleSavePin = async () => {
    if (!pin) {
      addToast('Enter a PIN', 'error');
      return;
    }
    if (pin !== pinConfirm) {
      addToast('PINs do not match', 'error');
      return;
    }
    if (pin.length < 4) {
      addToast('PIN must be at least 4 characters', 'error');
      return;
    }

    setSavingPin(true);
    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'pin', value: pin }),
      });

      if (res.ok) {
        addToast('Login PIN updated!', 'success');
        setPin('');
        setPinConfirm('');
      } else {
        addToast('Failed to save PIN', 'error');
      }
    } catch {
      addToast('Network error', 'error');
    } finally {
      setSavingPin(false);
    }
  };

  const maskValue = (val) => {
    if (!val) return '';
    if (val.length <= 6) return '••••••';
    return val.slice(0, 4) + '••••' + val.slice(-4);
  };

  if (loading) {
    return (
      <>
        <div className="page-header">
          <h2>Settings</h2>
          <p>Configure API keys, notifications, and security</p>
        </div>
        {[1, 2, 3].map((i) => (
          <div key={i} className="settings-section" style={{ marginBottom: 20 }}>
            <div className="skeleton skeleton-text" style={{ width: '30%', height: 18, marginBottom: 16 }} />
            <div className="skeleton skeleton-text" style={{ height: 42, marginBottom: 12 }} />
            <div className="skeleton skeleton-text" style={{ width: '20%', height: 36 }} />
          </div>
        ))}
      </>
    );
  }

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
        <h2>Settings</h2>
        <p>Configure API keys, notifications, and security</p>
      </div>

      {/* ── MonsterLab API Key ── */}
      <div className="settings-section">
        <h3>🔑 MonsterLab API Key</h3>
        <div className="settings-row">
          <div className="input-group">
            <label>API Key</label>
            <div className="password-wrapper">
              <input
                type={showApiKey ? 'text' : 'password'}
                placeholder="ml_your_api_key_here"
                value={settings.monsterlab_api_key}
                onChange={(e) =>
                  setSettings((prev) => ({ ...prev, monsterlab_api_key: e.target.value }))
                }
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowApiKey(!showApiKey)}
                title={showApiKey ? 'Hide' : 'Show'}
              >
                {showApiKey ? '🙈' : '👁'}
              </button>
            </div>
          </div>
          <button
            className="btn btn-primary"
            onClick={handleSaveApiKey}
            disabled={savingApi}
          >
            {savingApi ? '⏳' : '💾'} Save
          </button>
        </div>
        <p className="text-xs text-muted mt-8">
          Get your API key from monsterlab.io → Account &amp; API. Starts with &quot;ml_&quot;
        </p>
      </div>

      {/* ── WhatsApp Notifications ── */}
      <div className="settings-section">
        <h3>📱 WhatsApp Notifications</h3>
        <div className="settings-row">
          <div className="input-group">
            <label>Phone Number</label>
            <input
              type="text"
              placeholder="+1234567890"
              value={settings.whatsapp_phone}
              onChange={(e) =>
                setSettings((prev) => ({ ...prev, whatsapp_phone: e.target.value }))
              }
            />
          </div>
          <div className="input-group">
            <label>CallMeBot API Key</label>
            <div className="password-wrapper">
              <input
                type={showWhatsappKey ? 'text' : 'password'}
                placeholder="Your CallMeBot API key"
                value={settings.whatsapp_api_key}
                onChange={(e) =>
                  setSettings((prev) => ({ ...prev, whatsapp_api_key: e.target.value }))
                }
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowWhatsappKey(!showWhatsappKey)}
                title={showWhatsappKey ? 'Hide' : 'Show'}
              >
                {showWhatsappKey ? '🙈' : '👁'}
              </button>
            </div>
          </div>
        </div>
        <div className="flex gap-12 mt-16">
          <button
            className="btn btn-primary"
            onClick={handleSaveWhatsapp}
            disabled={savingWhatsapp}
          >
            {savingWhatsapp ? '⏳' : '💾'} Save
          </button>
          <button
            className="btn btn-secondary"
            onClick={handleTestNotification}
            disabled={testingNotif || !settings.whatsapp_phone || !settings.whatsapp_api_key}
          >
            {testingNotif ? '⏳ Sending...' : '🔔 Test Notification'}
          </button>
        </div>
        <p className="text-xs text-muted mt-8">
          Setup: Save +34 644 51 95 23 as &quot;CallMeBot&quot; on WhatsApp, send &quot;I allow callmebot to send me messages&quot; to get your API key.
        </p>
      </div>

      {/* ── Login PIN ── */}
      <div className="settings-section">
        <h3>🔒 Login PIN</h3>
        <div className="settings-row">
          <div className="input-group">
            <label>New PIN</label>
            <div className="password-wrapper">
              <input
                type={showPin ? 'text' : 'password'}
                placeholder="Enter new PIN (min 4 chars)"
                value={pin}
                onChange={(e) => setPin(e.target.value)}
              />
              <button
                type="button"
                className="password-toggle"
                onClick={() => setShowPin(!showPin)}
                title={showPin ? 'Hide' : 'Show'}
              >
                {showPin ? '🙈' : '👁'}
              </button>
            </div>
          </div>
          <div className="input-group">
            <label>Confirm PIN</label>
            <input
              type="password"
              placeholder="Confirm PIN"
              value={pinConfirm}
              onChange={(e) => setPinConfirm(e.target.value)}
            />
          </div>
          <button
            className="btn btn-primary"
            onClick={handleSavePin}
            disabled={savingPin}
          >
            {savingPin ? '⏳' : '🔒'} Set PIN
          </button>
        </div>
        <p className="text-xs text-muted mt-8">
          Protect your dashboard with a login PIN. Leave empty to disable authentication.
        </p>
      </div>
    </>
  );
}
