import { NextResponse } from 'next/server';
import { getSupabase } from '@/lib/supabase';
import { MonsterLabAPI } from '@/lib/monsterlab';
import { notifySubmission, notifyBatchComplete } from '@/lib/whatsapp';

const BATCH_SIZE = 5; // Process up to 5 items per cron invocation
const DELAY_BETWEEN_MS = 2000; // 2 seconds between submissions

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

// GET /api/cron?secret=xxx — process pending queue items
export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const secret = searchParams.get('secret');

  // Verify cron secret
  const cronSecret = process.env.CRON_SECRET || 'ml-cron-2024-secret';
  if (secret !== cronSecret) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  try {
    const db = getSupabase();

    // Get API key
    let apiKey = process.env.MONSTERLAB_API_KEY;
    if (!apiKey) {
      const { data: keyRow } = await db
        .from('settings')
        .select('value')
        .eq('key', 'monsterlab_api_key')
        .single();
      apiKey = keyRow?.value;
    }

    if (!apiKey) {
      return NextResponse.json({ success: false, error: 'No API key configured' });
    }

    // Get WhatsApp settings
    const { data: waSettings } = await db
      .from('settings')
      .select('key, value')
      .in('key', ['whatsapp_phone', 'whatsapp_api_key']);

    const waConfig = {};
    (waSettings || []).forEach(s => { waConfig[s.key] = s.value; });

    // Fetch pending items with account info
    const { data: pendingItems, error: fetchError } = await db
      .from('queue')
      .select('*, accounts(username, campaign_id, campaign_name, campaign_password)')
      .eq('status', 'pending')
      .order('created_at', { ascending: true })
      .limit(BATCH_SIZE);

    if (fetchError) throw fetchError;

    if (!pendingItems || pendingItems.length === 0) {
      return NextResponse.json({ success: true, processed: 0, message: 'No pending items' });
    }

    const api = new MonsterLabAPI(apiKey);
    const results = { processed: 0, success: 0, failed: 0 };

    for (const item of pendingItems) {
      // Mark as processing
      await db.from('queue').update({ status: 'processing' }).eq('id', item.id);

      try {
        const account = item.accounts;
        const campaignId = account?.campaign_id;
        const password = account?.campaign_password;

        const result = await api.submitClip(item.url, campaignId, { password });

        // Mark success
        const submissionId = result?.data?.submissionId || result?.submissionId || null;
        await db.from('queue').update({
          status: 'success',
          submission_id: submissionId,
          processed_at: new Date().toISOString(),
        }).eq('id', item.id);

        results.success++;

        // WhatsApp notification (individual)
        if (waConfig.whatsapp_phone && waConfig.whatsapp_api_key) {
          await notifySubmission(waConfig.whatsapp_phone, waConfig.whatsapp_api_key, {
            url: item.url,
            status: 'success',
            account: account?.username || 'Unknown',
            campaign: account?.campaign_name || campaignId,
          }).catch(() => {}); // Don't fail on notification error
        }

      } catch (err) {
        // Mark failed
        await db.from('queue').update({
          status: 'failed',
          error_message: err.message?.substring(0, 500),
          processed_at: new Date().toISOString(),
        }).eq('id', item.id);

        results.failed++;

        // WhatsApp notification (failure)
        if (waConfig.whatsapp_phone && waConfig.whatsapp_api_key) {
          await notifySubmission(waConfig.whatsapp_phone, waConfig.whatsapp_api_key, {
            url: item.url,
            status: 'failed',
            account: item.accounts?.username || 'Unknown',
            campaign: item.accounts?.campaign_name || 'Unknown',
            error: err.message,
          }).catch(() => {});
        }
      }

      results.processed++;

      // Rate limit delay between submissions
      if (results.processed < pendingItems.length) {
        await sleep(DELAY_BETWEEN_MS);
      }
    }

    // Send batch summary if multiple items processed
    if (results.processed > 1 && waConfig.whatsapp_phone && waConfig.whatsapp_api_key) {
      await notifyBatchComplete(waConfig.whatsapp_phone, waConfig.whatsapp_api_key, {
        total: results.processed,
        success: results.success,
        failed: results.failed,
        campaign: 'Multiple',
      }).catch(() => {});
    }

    return NextResponse.json({ success: true, ...results });
  } catch (err) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
