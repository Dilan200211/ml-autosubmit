import { NextResponse } from 'next/server';
import { getSupabase } from '@/lib/supabase';

// GET /api/history — fetch submission history with optional filters
export async function GET(request) {
  try {
    const { searchParams } = new URL(request.url);
    const status = searchParams.get('status');
    const account_id = searchParams.get('account_id');
    const limit = parseInt(searchParams.get('limit') || '50', 10);
    const offset = parseInt(searchParams.get('offset') || '0', 10);

    const db = getSupabase();
    let query = db
      .from('queue')
      .select('*, accounts(username, campaign_name)', { count: 'exact' })
      .order('created_at', { ascending: false })
      .range(offset, offset + limit - 1);

    if (status && status !== 'all') {
      query = query.eq('status', status);
    }
    if (account_id) {
      query = query.eq('account_id', account_id);
    }

    const { data, error, count } = await query;
    if (error) throw error;

    return NextResponse.json({ success: true, data, total: count });
  } catch (err) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
