export interface DocumentSummary {
  id: number
  title: string
  document_type: string
  department: string | null
  source_filename: string
  ocr_status: 'pending' | 'processing' | 'completed' | 'failed'
  parse_status: 'pending' | 'completed' | 'failed'
  created_at: string
  updated_at: string
}
export interface Section {
  id: number
  section_type: string
  section_title: string
  content: string
  sequence: number
  source_page: number | null
}
export interface OcrLine { text: string; confidence: number; bbox: number[][] }
export interface DocumentDetail extends DocumentSummary {
  pages: { id: number; page_number: number; raw_text: string; ocr_json: { lines?: OcrLine[]; [key: string]: unknown } }[]
  sections: Section[]
  handover_items: {
    id: number; section_id: number | null; category: string; task_name: string; description: string
    procedure: string | null; precaution: string | null; importance: number | null
    frequency: string | null; related_system: string | null; contact_info: string | null
  }[]
  processing_error: { code: string; message: string } | null
}
export function isProcessing(doc: DocumentSummary) {
  return doc.ocr_status === 'pending' || doc.ocr_status === 'processing' ||
    (doc.ocr_status === 'completed' && doc.parse_status === 'pending')
}
export const statusLabel: Record<string, string> = {
  pending: '대기', processing: '처리 중', completed: '완료', failed: '실패',
}
