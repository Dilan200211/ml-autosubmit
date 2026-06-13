/**
 * Simple PIN-based authentication middleware.
 * Uses a cookie-based session approach.
 */

const crypto = require('crypto');

const SESSION_COOKIE = 'ml_session';
const SESSION_SECRET = process.env.SESSION_SECRET || 'monsterlab-default-secret-change-me';

/**
 * Hash a PIN for secure storage.
 */
function hashPin(pin) {
  return crypto.createHash('sha256').update(pin + SESSION_SECRET).digest('hex');
}

/**
 * Create a session token from a PIN.
 */
function createSessionToken(pin) {
  const payload = `${hashPin(pin)}:${Date.now()}`;
  return Buffer.from(payload).toString('base64');
}

/**
 * Validate a session token.
 */
function validateSession(token, storedPinHash) {
  try {
    const decoded = Buffer.from(token, 'base64').toString();
    const [hash] = decoded.split(':');
    return hash === storedPinHash;
  } catch {
    return false;
  }
}

/**
 * Check if request is authenticated (for API routes).
 * Reads the session cookie and validates against stored PIN hash.
 */
function isAuthenticated(request, storedPinHash) {
  if (!storedPinHash) return true; // No PIN set = no auth required

  const cookieHeader = request.headers.get('cookie') || '';
  const cookies = Object.fromEntries(
    cookieHeader.split(';').map(c => {
      const [key, ...val] = c.trim().split('=');
      return [key, val.join('=')];
    })
  );

  const token = cookies[SESSION_COOKIE];
  if (!token) return false;

  return validateSession(token, storedPinHash);
}

module.exports = { hashPin, createSessionToken, validateSession, isAuthenticated, SESSION_COOKIE };
