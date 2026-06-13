import { NextResponse } from 'next/server';
import { getSupabase } from '@/lib/supabase';

// GET /api/accounts — list all accounts
export async function GET() {
  try {
    const db = getSupabase();
    const { data, error } = await db
      .from('accounts')
      .select('*')
      .order('created_at', { ascending: false });

    if (error) throw error;
    return NextResponse.json({ success: true, data });
  } catch (err) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

// POST /api/accounts — create a new account
export async function POST(request) {
  try {
    const body = await request.json();
    const { username, campaign_id, campaign_name, campaign_password } = body;

    if (!username || !campaign_id) {
      return NextResponse.json(
        { success: false, error: 'Username and campaign_id are required' },
        { status: 400 }
      );
    }

    const db = getSupabase();
    const { data, error } = await db
      .from('accounts')
      .insert({
        username: username.replace('@', ''),
        campaign_id,
        campaign_name: campaign_name || null,
        campaign_password: campaign_password || null,
      })
      .select()
      .single();

    if (error) throw error;
    return NextResponse.json({ success: true, data });
  } catch (err) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

// DELETE /api/accounts?id=xxx — delete an account
export async function DELETE(request) {
  try {
    const { searchParams } = new URL(request.url);
    const id = searchParams.get('id');

    if (!id) {
      return NextResponse.json({ success: false, error: 'Account ID required' }, { status: 400 });
    }

    const db = getSupabase();
    const { error } = await db.from('accounts').delete().eq('id', id);

    if (error) throw error;
    return NextResponse.json({ success: true });
  } catch (err) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

// PATCH /api/accounts — toggle active status
export async function PATCH(request) {
  try {
    const body = await request.json();
    const { id, is_active } = body;

    if (!id) {
      return NextResponse.json({ success: false, error: 'Account ID required' }, { status: 400 });
    }

    const db = getSupabase();
    const { data, error } = await db
      .from('accounts')
      .update({ is_active })
      .eq('id', id)
      .select()
      .single();

    if (error) throw error;
    return NextResponse.json({ success: true, data });
  } catch (err) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
