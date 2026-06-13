import { NextResponse } from 'next/server';
import { getSupabase } from '@/lib/supabase';

// GET /api/stats — dashboard statistics
export async function GET() {
  try {
    const db = getSupabase();
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const todayISO = today.toISOString();

    // Get counts by status for today
    const { data: todayItems } = await db
      .from('queue')
      .select('status')
      .gte('created_at', todayISO);

    const stats = {
      total: todayItems?.length || 0,
      pending: 0,
      processing: 0,
      success: 0,
      failed: 0,
    };

    (todayItems || []).forEach(item => {
      if (stats[item.status] !== undefined) {
        stats[item.status]++;
      }
    });

    // Get total pending in queue (all time)
    const { count: queueCount } = await db
      .from('queue')
      .select('*', { count: 'exact', head: true })
      .eq('status', 'pending');

    stats.queue_pending = queueCount || 0;

    // Get account count
    const { count: accountCount } = await db
      .from('accounts')
      .select('*', { count: 'exact', head: true })
      .eq('is_active', true);

    stats.active_accounts = accountCount || 0;

    return NextResponse.json({ success: true, data: stats });
  } catch (err) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
