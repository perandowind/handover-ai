const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${baseUrl}/api${path}`, options)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.message ?? `요청 실패 (${response.status})`)
  }
  return response.json() as Promise<T>
}
export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '요청에 실패했습니다.'
}
