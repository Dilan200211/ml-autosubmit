import { NextResponse } from 'next/server';
import { MonsterLabAPI } from '@/lib/monsterlab';
import { getSupabase } from '@/lib/supabase';

// GET /api/campaigns — fetch campaigns from MonsterLab
export async function GET() {
  try {
    // Get API key from env or Supabase settings
    let apiKey = process.env.MONSTERLAB_API_KEY;

    if (!apiKey) {
      const db = getSupabase();
      const { data } = await db
        .from('settings')
        .select('value')
        .eq('key', 'monsterlab_api_key')
        .single();
      apiKey = data?.value;
    }

    if (!apiKey) {
      return NextResponse.json(
        { success: false, error: 'MonsterLab API key not configured' },
        { status: 400 }
      );
    }

    const api = new MonsterLabAPI(apiKey);
    const result = await api.getCampaigns();

    return NextResponse.json({
      success: true,
      data: result?.data || result || [],
    });
  } catch (err) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
