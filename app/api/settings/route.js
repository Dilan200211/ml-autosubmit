import { NextResponse } from 'next/server';
import { getSupabase } from '@/lib/supabase';

// GET /api/settings — read all settings
export async function GET() {
  try {
    const db = getSupabase();
    const { data, error } = await db.from('settings').select('*');
    if (error) throw error;

    // Convert to key-value object, mask sensitive values
    const settings = {};
    (data || []).forEach(row => {
      if (row.key === 'monsterlab_api_key' && row.value) {
        settings[row.key] = row.value.substring(0, 8) + '...';
        settings[row.key + '_set'] = true;
      } else if (row.key === 'pin_hash') {
        settings['pin_set'] = !!row.value;
      } else {
        settings[row.key] = row.value;
      }
    });

    return NextResponse.json({ success: true, data: settings });
  } catch (err) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

// POST /api/settings — update settings
export async function POST(request) {
  try {
    const body = await request.json();
    const db = getSupabase();

    const updates = [];
    for (const [key, value] of Object.entries(body)) {
      if (key && value !== undefined) {
        updates.push(
          db.from('settings').upsert(
            { key, value: String(value), updated_at: new Date().toISOString() },
            { onConflict: 'key' }
          )
        );
      }
    }

    await Promise.all(updates);
    return NextResponse.json({ success: true, message: 'Settings saved' });
  } catch (err) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
