/**
 * Telegram Connector — mirrors delivery.py _send_telegram()
 *
 * Reads TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID from env.
 * Gracefully no-ops when not configured (dev / local environments).
 * Uses XO bot token — no new bot created (D-3C-05).
 */

const https = require('https');

const MAX_LEN = 4096;

function _configured() {
  return !!(process.env.TELEGRAM_BOT_TOKEN && process.env.TELEGRAM_CHAT_ID);
}

function _stripSlack(text) {
  // Strip Slack mrkdwn markers so they don't appear raw in Telegram
  return text
    .replace(/<([^|>]+)\|([^>]+)>/g, '$2')  // <url|label> → label
    .replace(/<[^>]+>/g, '')                 // remaining <...>
    .replace(/\*([^*]+)\*/g, '<b>$1</b>')   // *bold* → <b>bold</b>
    .replace(/_([^_]+)_/g, '<i>$1</i>')     // _italic_ → <i>italic</i>
    .replace(/`([^`]+)`/g, '<code>$1</code>'); // `code` → <code>code</code>
}

function _truncate(text) {
  if (text.length <= MAX_LEN) return text;
  return text.slice(0, MAX_LEN - 1).trimEnd() + '…';
}

/**
 * Send a message to the configured Telegram chat.
 * @param {string} text  — HTML-formatted text (or plain text)
 * @returns {Promise<{ok: boolean, error?: string}>}
 */
function sendTelegram(text) {
  if (!_configured()) {
    return Promise.resolve({ ok: false, error: 'TELEGRAM_BOT_TOKEN not configured' });
  }

  const token  = process.env.TELEGRAM_BOT_TOKEN;
  const chatId = process.env.TELEGRAM_CHAT_ID;
  const body   = JSON.stringify({
    chat_id:                  chatId,
    text:                     _truncate(_stripSlack(text)),
    parse_mode:               'HTML',
    disable_web_page_preview: true,
  });

  return new Promise((resolve) => {
    const req = https.request({
      hostname: 'api.telegram.org',
      port:     443,
      path:     `/bot${token}/sendMessage`,
      method:   'POST',
      headers: {
        'Content-Type':   'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
    }, (res) => {
      let data = '';
      res.on('data', c => { data += c; });
      res.on('end', () => {
        try {
          const json = JSON.parse(data);
          if (json.ok) {
            resolve({ ok: true });
          } else {
            resolve({ ok: false, error: json.description || 'Telegram API error' });
          }
        } catch {
          resolve({ ok: false, error: 'JSON parse error' });
        }
      });
    });
    req.on('error', (e) => resolve({ ok: false, error: e.message }));
    req.setTimeout(8000, () => { req.destroy(); resolve({ ok: false, error: 'Timeout' }); });
    req.write(body);
    req.end();
  });
}

module.exports = { sendTelegram, configured: _configured };
