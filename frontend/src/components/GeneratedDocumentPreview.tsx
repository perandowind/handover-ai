import type { GeneratedDocument } from '../types/generation'

export default function GeneratedDocumentPreview({ document }: { document: GeneratedDocument }) {
  const noInformation = document.sections.every(section => section.content === '관련 정보 없음')
  return <section aria-labelledby="preview-heading" className="generation-preview">
    <h2 id="preview-heading">생성 결과 미리보기</h2>
    {noInformation && <p role="status" className="muted">요청을 뒷받침할 관련 정보가 없습니다. 문서 선택이나 요청 내용을 확인하세요.</p>}
    <p className="muted">조회된 내용을 바탕으로 작성한 초안입니다. 사용 전 원문과 대조해 확인하세요.</p>
    <article aria-label={document.title}>
      <h3 className="generated-title">{document.title}</h3>
      {document.sections.map((section, index) => <section key={section.section_type}>
        <h4>{index + 1}. {section.title}</h4>
        <p className={`preserve${section.content === '관련 정보 없음' ? ' muted' : ''}`}>{section.content}</p>
      </section>)}
    </article>
  </section>
}
