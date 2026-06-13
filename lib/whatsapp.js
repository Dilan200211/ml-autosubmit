/**
 * WhatsApp Notification via CallMeBot
 * Free WhatsApp messaging API - no business account needed.
 *
 * Setup: Save +34 644 51 95 23 as "CallMeBot" on WhatsApp,
 * send "I allow callmebot to send me messages" to get your API key.
 */

async function sendWhatsApp(phone, apiKey, message) {
  if (!phone || !apiKey) {
    console.warn('WhatsApp not configured, skipping notification');
    return false;
  }

  try {
    // Clean phone number (remove spaces, dashes, +)
    const cleanPhone = phone.replace(/[\s\-\+]/g, '');
    const encodedMsg = encodeURIComponent(message);

    const url = `https://api.callmebot.com/whatsapp.php?phone=${cleanPhone}&text=${encodedMsg}&apikey=${apiKey}`;

    const res = await fetch(url);

    if (res.ok) {
      console.log('WhatsApp notification sent successfully');
      return true;
    } else {
      console.error(`WhatsApp send failed: ${res.status}`);
      return false;
    }
  } catch (err) {
    console.error('WhatsApp notification error:', err.message);
    return false;
  }
}

/**
 * Send a submission result notification.
 */
async function notifySubmission(phone, apiKey, { url, status, account, campaign, error = null }) {
  const emoji = status === 'success' ? '✅' : '❌';
  let message = `${emoji} *MonsterLab Submission*\n`;
  message += `Account: ${account}\n`;
  message += `Campaign: ${campaign}\n`;
  message += `URL: ${url}\n`;
  message += `Status: ${status.toUpperCase()}`;
  if (error) {
    message += `\nError: ${error}`;
  }

  return sendWhatsApp(phone, apiKey, message);
}

/**
 * Send a batch summary notification.
 */
async function notifyBatchComplete(phone, apiKey, { total, success, failed, campaign }) {
  let message = `📊 *Batch Complete*\n`;
  message += `Campaign: ${campaign}\n`;
  message += `Total: ${total}\n`;
  message += `✅ Success: ${success}\n`;
  message += `❌ Failed: ${failed}`;

  return sendWhatsApp(phone, apiKey, message);
}

module.exports = { sendWhatsApp, notifySubmission, notifyBatchComplete };
