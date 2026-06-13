/**
 * MonsterLab ClipIt API Client (JavaScript/Fetch)
 * Port of the Python API client for serverless use.
 */

const DEFAULT_BASE_URL = 'https://monsterlab.io';

class MonsterLabAPI {
  constructor(apiKey, baseUrl = DEFAULT_BASE_URL) {
    this.apiKey = apiKey;
    this.baseUrl = baseUrl.replace(/\/+$/, '');
  }

  async _request(method, path, { body = null, auth = true } = {}) {
    const url = `${this.baseUrl}${path}`;
    const headers = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };

    if (auth) {
      headers['Authorization'] = `ApiKey ${this.apiKey}`;
    }

    const options = { method, headers };
    if (body) {
      options.body = JSON.stringify(body);
    }

    const maxRetries = 3;
    for (let attempt = 0; attempt < maxRetries; attempt++) {
      try {
        const res = await fetch(url, options);

        if (res.status === 429) {
          const retryAfter = parseInt(res.headers.get('retry-after') || '5', 10);
          console.warn(`Rate limited, waiting ${retryAfter}s...`);
          await new Promise(r => setTimeout(r, retryAfter * 1000));
          continue;
        }

        if (res.status === 401 || res.status === 403) {
          throw new Error(`Authentication failed (${res.status}): Invalid or inactive API key.`);
        }

        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
          throw new Error(data.message || data.error || `API error (${res.status})`);
        }

        return data;
      } catch (err) {
        if (attempt === maxRetries - 1) throw err;
        await new Promise(r => setTimeout(r, (attempt + 1) * 1000));
      }
    }
  }

  async validateKey() {
    try {
      const data = await this._request('POST', '/api/clips/validate-key', {
        body: { apiKey: this.apiKey },
        auth: false,
      });
      return !!data?.valid;
    } catch {
      return false;
    }
  }

  async getCampaigns() {
    return this._request('GET', '/api/clips/campaigns');
  }

  async submitClip(url, campaignId = null, { password = null, label = null, notes = null } = {}) {
    const payload = { url };
    if (campaignId) payload.campaignId = campaignId;
    if (password) payload.password = password;
    if (label) payload.label = label;
    if (notes) payload.notes = notes;

    console.log(`Submitting clip${campaignId ? ` to campaign ${campaignId}` : ''}: ${url}`);
    return this._request('POST', '/api/clips/submit', { body: payload });
  }

  async getAccountInfo() {
    return this._request('GET', '/api/clips/account');
  }
}

module.exports = { MonsterLabAPI };
