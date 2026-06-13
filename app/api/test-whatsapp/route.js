import { NextResponse } from 'next/server';
import { getSupabase } from '@/lib/supabase';
import { sendWhatsApp } from '@/lib/whatsapp';

// POST /api/test-whatsapp — send a test WhatsApp notification
export async function POST() {
  try {
    const db = getSupabase();

    const { data: settings } = await db
      .from('settings')
      .select('key, value')
      .in('key', ['whatsapp_phone', 'whatsapp_api_key']);

    const config = {};
    (settings || []).forEach(s => { config[s.key] = s.value; });

    if (!config.whatsapp_phone || !config.whatsapp_api_key) {
      return NextResponse.json(
        { success: false, error: 'WhatsApp phone or API key not configured' },
        { status: 400 }
      );
    }

    const result = await sendWhatsApp(
      config.whatsapp_phone,
      config.whatsapp_api_key,
      '🧪 Test notification from MonsterLab AutoSubmit! Your WhatsApp integration is working.'
    );

    return NextResponse.json({ success: result });
  } catch (err) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}
