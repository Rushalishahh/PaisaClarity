/*
 * One small wrapper around fetch used by every page, so auth and error
 * handling can't drift between them:
 *
 * - attaches the Bearer token from localStorage when logged in
 * - JSON bodies are serialized automatically; FormData bodies are passed
 *   through untouched (the browser must set the multipart Content-Type
 *   with its boundary - setting it manually breaks the upload)
 * - on 401 the token is cleared and the user is sent to /login
 * - non-2xx responses throw ApiError with the backend's `detail` message
 *   (FastAPI puts the human-readable error there)
 */
import { API_BASE } from './config'

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message)
    this.name = 'ApiError'
    this.status = status // 0 means the network itself failed (backend down)
    this.data = data
  }
}

export async function api(path, { method = 'GET', body, headers = {} } = {}) {
  const opts = { method, headers: { ...headers } }

  const token = localStorage.getItem('token')
  if (token) opts.headers.Authorization = `Bearer ${token}`

  if (body instanceof FormData) {
    opts.body = body
  } else if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }

  let res
  try {
    res = await fetch(`${API_BASE}${path}`, opts)
  } catch {
    throw new ApiError('Cannot reach the server — is the backend running?', 0, null)
  }

  if (res.status === 401) {
    localStorage.removeItem('token')
    window.location.assign('/login')
    throw new ApiError('Session expired — please log in again.', 401, null)
  }

  let data = null
  try {
    data = await res.json()
  } catch {
    // Empty or non-JSON body (e.g. 204) - treat as null.
  }

  if (!res.ok) {
    const detail = data?.detail
    const message =
      typeof detail === 'string' ? detail : data?.message || `Request failed (${res.status})`
    throw new ApiError(message, res.status, data)
  }

  return data
}
