import { BrowserRouter, Link, NavLink, Route, Routes } from 'react-router-dom'
import Documents from './pages/Documents'
import DocumentDetail from './pages/DocumentDetail'
import Upload from './pages/Upload'
import Generate from './pages/Generate'

export default function App() {
  return <BrowserRouter>
    <header><Link to="/" className="brand">Handover AI</Link><nav aria-label="주 메뉴">
      <NavLink to="/" end>문서 목록</NavLink><NavLink to="/upload">PDF 업로드</NavLink><NavLink to="/generate">인수인계서 생성</NavLink>
    </nav></header>
    <main><Routes>
      <Route path="/" element={<Documents />} />
      <Route path="/generate" element={<Generate />} />
      <Route path="/upload" element={<Upload />} />
      <Route path="/documents/:id" element={<DocumentDetail />} />
      <Route path="*" element={<p>페이지를 찾을 수 없습니다. <Link to="/">문서 목록</Link></p>} />
    </Routes></main>
  </BrowserRouter>
}
