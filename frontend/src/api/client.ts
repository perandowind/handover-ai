const baseUrl = (import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000').replace(/\/$/, '')

async function request(path: string, options: RequestInit): Promise<Response> {
  const response = await fetch(`${baseUrl}/api${path}`, options)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.message ?? `요청 실패 (${response.status})`)
  }
  return response
}
export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : '요청에 실패했습니다.'
}


export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  return (await request(path, options)).json() as Promise<T>
}

export async function apiPdf(path: string, options: RequestInit): Promise<Blob> {
  const response = await request(path, options)
  if (!response.headers.get('Content-Type')?.toLowerCase().startsWith('application/pdf')) {
    throw new Error('PDF 응답 형식이 올바르지 않습니다.')
  }
  return response.blob()
}
