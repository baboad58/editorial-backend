import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Landing from './components/Landing'
import AccessGate from './components/AccessGate'
import StudioApp from './components/StudioApp'
import Terms from './components/Terms'
import Privacy from './components/Privacy'
import AdminConsole from './components/AdminConsole'
import { isAccessGranted } from './lib/invites'
import { getAdminToken } from './lib/admin'

function ProtectedStudio() {
  if (!isAccessGranted()) {
    return <Navigate to="/acceso" replace />
  }
  return <StudioApp />
}

function ProtectedAdmin() {
  if (!getAdminToken()) return <Navigate to="/" replace />
  return <AdminConsole />
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/acceso" element={<AccessGate />} />
        <Route path="/studio" element={<ProtectedStudio />} />
        <Route path="/terminos" element={<Terms />} />
        <Route path="/privacidad" element={<Privacy />} />
        <Route path="/admin/solicitudes" element={<ProtectedAdmin />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
