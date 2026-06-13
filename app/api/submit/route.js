import { NextResponse } from 'next/server';
import { getSupabase } from '@/lib/supabase';

// POST /api/submit — add URL(s) to the queue for an account
export async function POST(request) {
  try {
    const body = await request.json();
    const { account_id, urls } = body;

    if (!account_id) {
      return NextResponse.json(
        { success: false, error: 'account_id is required' },
        { status: 400 }
      );
    }

    // Normalize URLs input (string or array)
    let urlList = [];
    if (typeof urls === 'string') {
      urlList = urls
        .split('\n')
        .map(u => u.trim())
        .filter(u => u.length > 0);
    } else if (Array.isArray(urls)) {
      urlList = urls.map(u => u.trim()).filter(u => u.length > 0);
    }

    if (urlList.length === 0) {
      return NextResponse.json(
        { success: false, error: 'No valid URLs provided' },
        { status: 400 }
      );
    }

    // Add http prefix if needed
    urlList = urlList.map(u => {
      if (!u.startsWith('http://') && !u.startsWith('https://')) {
        return 'https://' + u;
      }
      return u;
    });

    const db = getSupabase();

    // Check for duplicates (pending or processing)
    const { data: existing } = await db
      .from('queue')
      .select('url')
      .eq('account_id', account_id)
      .in('status', ['pending', 'processing'])
      .in('url', urlList);

    const existingUrls = new Set((existing || []).map(e => e.url));
    const newUrls = urlList.filter(u => !existingUrls.has(u));
    const duplicates = urlList.length - newUrls.length;

    if (newUrls.length === 0) {
      return NextResponse.json({
        success: true,
        added: 0,
        duplicates,
        message: 'All URLs are already in the queue',
      });
    }

    // Insert into queue
    const rows = newUrls.map(url => ({
      account_id,
      url,
      status: 'pending',
    }));

    const { error } = await db.from('queue').insert(rows);
    if (error) throw error;

    return NextResponse.json({
      success: true,
      added: newUrls.length,
      duplicates,
    });
  } catch (err) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
