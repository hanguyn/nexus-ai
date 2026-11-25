import { Activity, AudioLines, FlaskConical, LayoutGrid, Network, ShieldAlert } from 'lucide-react'
import { lazy, Suspense } from 'react'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router-dom'
import { Loading } from './components'
import { Devices } from './views/Devices'
import { Incidents, IncidentDetail } from './views/Incidents'
import { Anomalies } from './views/Anomalies'
import { Demo } from './views/Demo'

const Overview = lazy(() => import('./views/Overview').then(module => ({ default: module.Overview })))

const navigation = [
  { label: 'Overview', path: '/', icon: LayoutGrid },
  { label: 'Device Inventory', path: '/devices', icon: Network },
  { label: 'Incident Center', path: '/incidents', icon: ShieldAlert },
  { label: 'Anomaly Detection', path: '/anomalies', icon: AudioLines },
  { label: 'Demo Simulator', path: '/demo', icon: FlaskConical },
]

export function App() {
  const { pathname } = useLocation()
  const section = navigation.find(item => item.path === '/' ? pathname === '/' : pathname.startsWith(item.path))
  return <div className="app-layout">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className="sidebar">
      <Link className="brand" to="/"><span className="brand-icon"><Network size={22} /></span><span>NEXUS <strong>AI</strong><small>NETWORK OPERATIONS</small></span></Link>
      <nav aria-label="Main navigation">{navigation.map(({ label, path, icon: Icon }) =>
        <NavLink key={path} to={path} end={path === '/'}><Icon size={18} />{label}</NavLink>
      )}</nav>
    </aside>
    <div className="workspace">
      <header className="topbar"><span>Operations</span><span className="topbar-divider">/</span><strong>{section?.label || 'Page not found'}</strong><Activity className="topbar-icon" size={18} aria-hidden="true" /></header>
      <main id="main-content"><Routes>
        <Route path="/" element={<Suspense fallback={<Loading />}><Overview /></Suspense>} />
        <Route path="/devices" element={<Devices />} />
        <Route path="/incidents" element={<Incidents />} />
        <Route path="/incidents/:id" element={<IncidentDetail />} />
        <Route path="/anomalies" element={<Anomalies />} />
        <Route path="/demo" element={<Demo />} />
        <Route path="*" element={<div className="card"><h1>Page not found</h1><Link className="text-link" to="/">Back to overview</Link></div>} />
      </Routes></main>
    </div>
  </div>
}
