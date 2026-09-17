const jsonHeaders = { 'Content-Type': 'application/json' };

async function readJson(response) {
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(payload.error || `Request failed with ${response.status}`);
  }

  return payload;
}

export async function getSession() {
  const response = await fetch('/api/session');
  return readJson(response);
}

export async function getLoginUrl() {
  const response = await fetch('/api/login');
  return readJson(response);
}

export async function logout() {
  const response = await fetch('/api/logout', { method: 'POST' });
  return readJson(response);
}

export async function getPlaylists() {
  const response = await fetch('/api/playlists');
  return readJson(response);
}

export async function analyzePlaylist(payload) {
  const response = await fetch('/api/analyze', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });

  return readJson(response);
}

export async function getInsights(payload) {
  const response = await fetch('/api/insights', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });

  return readJson(response);
}

export async function getWrapped(payload) {
  const response = await fetch('/api/wrapped', {
    method: 'POST',
    headers: jsonHeaders,
    body: JSON.stringify(payload),
  });

  return readJson(response);
}
