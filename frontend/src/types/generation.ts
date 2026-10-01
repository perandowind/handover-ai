export interface GeneratedSection {
  section_type: 'overview' | 'responsibilities' | 'systems' | 'procedures' |
    'precautions' | 'troubleshooting' | 'contacts' | 'references'
  title: string
  content: string
}

export interface GeneratedDocument {
  title: string
  sections: GeneratedSection[]
}
