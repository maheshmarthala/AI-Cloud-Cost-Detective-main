export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('token');
  const response = await fetch(`/api${path}`, { ...init, headers: {
    'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers
  }});
  if (response.status === 401 && !path.startsWith('/auth/')) {
    localStorage.removeItem('token'); window.location.assign('/login');
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof body.detail === 'string' ? body.detail : (response.status === 502 || response.status === 504 ? 'Backend server unreachable. Make sure Uvicorn is running on port 8000.' : 'Request failed. Check your input and try again.');
    throw new Error(detail);
  }
  return body;
}
