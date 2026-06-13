-- MonsterLab Auto-Submit Dashboard Schema
-- Run this in Supabase SQL Editor

-- Instagram accounts linked to campaigns
CREATE TABLE IF NOT EXISTS accounts (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  username TEXT NOT NULL,
  campaign_id TEXT NOT NULL,
  campaign_name TEXT,
  campaign_password TEXT,
  is_active BOOLEAN DEFAULT true,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Submission queue
CREATE TABLE IF NOT EXISTS queue (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
  url TEXT NOT NULL,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'success', 'failed')),
  error_message TEXT,
  submission_id TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  processed_at TIMESTAMPTZ
);

-- App settings (API key, WhatsApp, PIN, etc.)
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_queue_status ON queue(status);
CREATE INDEX IF NOT EXISTS idx_queue_account ON queue(account_id);
CREATE INDEX IF NOT EXISTS idx_queue_created ON queue(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_accounts_active ON accounts(is_active);

-- Insert default settings
INSERT INTO settings (key, value) VALUES
  ('monsterlab_api_key', ''),
  ('whatsapp_phone', ''),
  ('whatsapp_api_key', ''),
  ('pin_hash', ''),
  ('cron_secret', 'change-this-to-a-random-string')
ON CONFLICT (key) DO NOTHING;
