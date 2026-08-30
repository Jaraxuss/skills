import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { createRoot } from 'react-dom/client'
import { DashboardPage, EnrollmentListPage, NewEnrollmentPage, ProfilesPage, ReviewRoute } from './pages'
import './style.css'

function App() {
  return <BrowserRouter><Routes><Route path="/" element={<DashboardPage />} /><Route path="/enrollments" element={<EnrollmentListPage />} /><Route path="/enrollments/new" element={<NewEnrollmentPage />} /><Route path="/enrollments/:sessionId" element={<ReviewRoute />} /><Route path="/profiles" element={<ProfilesPage />} /><Route path="*" element={<Navigate to="/" replace />} /></Routes></BrowserRouter>
}

document.title = '声纹建库控制台'
const root = document.getElementById('root')
if (root) createRoot(root).render(<App />)
