import { Activity, CircleCheck, CircleX, Radar, RefreshCw, Server, ShieldAlert } from 'lucide-react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Link } from 'react-router-dom'
import { formatTime, get } from '../api'
import type { Device, Incident, NetworkHealth } from '../api'
import { Badge, Empty, Loading, Notice, PageHeader } from '../components'
import { useData } from '../hooks'

const loadHealth = (signal: AbortSignal) => get<NetworkHealth>('/network-health', signal)
const loadDevices = (signal: AbortSignal) => get<Device[]>('/devices', signal)
const loadIncidents = (signal: AbortSignal) => get<Incident[]>('/incidents', signal)
const timeLabel = (value: string) => new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })

export function Overview() {
  const health = useData(loadHealth, 15_000)
  const devices = useData(loadDevices, 15_000)
  const incidents = useData(loadIncidents, 15_000)
  const summary = health.data?.history.at(-1)
  const open = incidents.data?.filter(item => !['resolved', 'closed'].includes(item.status))
  const latest = [...(incidents.data ?? [])].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)).slice(0, 5)
  const cards = [
    { title: 'Total devices', value: devices.data?.length, icon: Server, tone: 'cyan', note: 'Registered in inventory' },
    { title: 'Online devices', value: summary?.online, icon: CircleCheck, tone: 'green', note: 'SNMP scrape responding' },
    { title: 'Offline devices', value: summary?.offline, icon: CircleX, tone: 'red', note: `${summary?.unknown ?? '—'} with unknown health` },
    { title: 'Open incidents', value: open?.length, icon: ShieldAlert, tone: 'amber', note: 'Awaiting resolution' },
    { title: 'Active anomalies', value: health.data?.active_anomalies, icon: Radar, tone: 'violet', note: 'Latest scores over 1 hour' },
  ]
  return <>
    <PageHeader title="Network Overview" description="Device availability, incidents, and anomalies across your network."
      action={<button className="button button-secondary" onClick={() => { health.refresh(); devices.refresh(); incidents.refresh() }}><RefreshCw size={16} />Refresh</button>} />
    {(health.error || devices.error || incidents.error) && <Notice error message={health.error || devices.error || incidents.error} />}
    <div className="kpi-grid">{cards.map(({ title, value, icon: Icon, tone, note }) => <section key={title} className="card kpi">
      <div className="kpi-title"><span>{title}</span><span className={`kpi-icon tone-${tone}`}><Icon size={17} /></span></div>
      <strong>{value ?? '—'}</strong><p>{note}</p>
    </section>)}</div>
    <section className="card">
      <div className="card-heading"><div><h2><Activity size={18} />Network health</h2><p>Device counts over the last 30 minutes</p></div><span className="meta">{summary ? `Updated ${timeLabel(summary.at)}` : ''}</span></div>
      <div className="chart-legend"><span><i className="swatch online" />Online</span><span><i className="swatch offline" />Offline</span><span><i className="swatch unknown" />Unknown</span></div>
      <div className="chart" aria-label="Online, offline, and unknown device counts over time">
        {health.data ? <ResponsiveContainer width="100%" height="100%" minWidth={0}>
          <LineChart data={health.data.history} margin={{ left: -18, right: 14, top: 8, bottom: 4 }}>
            <CartesianGrid vertical={false} stroke="#263246" strokeDasharray="4 5" />
            <XAxis dataKey="at" tickFormatter={timeLabel} minTickGap={54} tick={{ fill: '#9aaac1', fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis allowDecimals={false} domain={[0, count => Math.max(1, count)]} tick={{ fill: '#9aaac1', fontSize: 12 }} axisLine={false} tickLine={false} />
            <Tooltip labelFormatter={label => typeof label === 'string' ? formatTime(label) : ''}
              contentStyle={{ background: '#111b2a', border: '1px solid #31435a', borderRadius: 8 }} />
            <Line name="Online" type="stepAfter" dataKey="online" stroke="#51dbc1" strokeWidth={2.5} dot={false} isAnimationActive={false} />
            <Line name="Offline" type="stepAfter" dataKey="offline" stroke="#fb8193" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line name="Unknown" type="stepAfter" dataKey="unknown" stroke="#a6b4c9" strokeWidth={2} strokeDasharray="4 3" dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer> : health.loading ? <Loading /> : <Empty>Network health is unavailable.</Empty>}
      </div>
    </section>
    <section className="card section-gap">
      <div className="card-heading"><div><h2>Latest incidents</h2><p>Recently updated incident records</p></div><Link to="/incidents" className="text-link">View all incidents</Link></div>
      {latest.length ? <div className="table-scroll"><table><thead><tr><th>Incident</th><th>Severity</th><th>Status</th><th>Updated</th></tr></thead>
        <tbody>{latest.map(item => <tr key={item.id}><td><Link className="row-link" to={`/incidents/${item.id}`}>{item.title}</Link></td><td><Badge value={item.severity} /></td><td><Badge value={item.status} /></td><td>{formatTime(item.updated_at)}</td></tr>)}</tbody>
      </table></div> : incidents.loading ? <Loading /> : <Empty>No incidents available.</Empty>}
    </section>
  </>
}
