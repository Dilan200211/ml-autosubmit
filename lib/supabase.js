/**
 * Supabase Client
 * Server-side Supabase client for API routes.
 */

const { createClient } = require('@supabase/supabase-js');

let supabase = null;

function getSupabase() {
  if (!supabase) {
    const url = process.env.SUPABASE_URL;
    const key = process.env.SUPABASE_SERVICE_KEY;

    if (!url || !key) {
      throw new Error('Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables');
    }

    supabase = createClient(url, key);
  }
  return supabase;
}

module.exports = { getSupabase };
