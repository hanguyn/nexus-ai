import { CircleCheck, FlaskConical, ListChecks, ScanLine, Sparkles, Workflow } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, describeError, formatNumber, formatTime, get, humanize } from '../api'
import type { Assistant, Candidate, Incident, Run, Verification } from '../api'
import { Badge, Empty, Loading, Notice, PageHeader } from '../components'
import { useData } from '../hooks'

const statuses = ['all', 'new', 'acknowledged', 'investigating', 'resolved', 'closed']
const load = (signal: AbortSignal) => get<Incident[]>('/incidents', signal)

export function Incidents() {
  const list = useData(load, 15_000)
  const [filter, setFilter] = useState('all')
  const rows = list.data?.filter(item => filter === 'all' || item.status === filter) ?? []
  return <>
    <PageHeader title="Incident Center" description="Review incidents, correlated alerts, and root cause analysis." />
    {list.error && <Notice error message={list.error} />}
    <section className="card">
      <div className="card-heading"><div><h2>Incident queue</h2><p>{rows.length} matching incidents</p></div>
        <label className="filter">Status<select value={filter} onChange={event => setFilter(event.target.value)}>{statuses.map(status => <option key={status} value={status}>{humanize(status)}</option>)}</select></label>
      </div>
      {rows.length ? <div className="table-scroll"><table><thead><tr><th>Incident</th><th>Severity</th><th>Status</th><th>Alerts</th><th>Updated</th></tr></thead>
        <tbody>{rows.map(item => <tr key={item.id}><td><Link to={`/incidents/${item.id}`} className="row-link">{item.title}</Link></td><td><Badge value={item.severity} /></td><td><Badge value={item.status} /></td><td>{item.alerts.length}</td><td>{formatTime(item.updated_at)}</td></tr>)}</tbody>
      </table></div> : list.loading ? <Loading /> : <Empty>No incidents match this filter.</Empty>}
    </section>
  </>
}

export function IncidentDetail() {
  const { id } = useParams()
  if (!id || !/^\d+$/.test(id)) return <Notice error message="Invalid incident ID." />
  return <IncidentContent key={id} id={id} />
}

function IncidentContent({ id }: { id: string }) {
  const path = `/incidents/${id}`
  const [loader] = useState(() => (signal: AbortSignal) => Promise.all([
    get<Incident>(path, signal), get<Candidate[]>(`${path}/rca`, signal), get<Assistant>(`${path}/assistant`, signal),
  ]))
  const details = useData(loader)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [statusMessage, setStatusMessage] = useState('')
  const [notes, setNotes] = useState<Record<number, string>>({})
  const [verification, setVerification] = useState<Verification>()

  async function perform(action: string, request: () => Promise<unknown>, success: string) {
    setBusy(action)
    setError('')
    setStatusMessage('')
    try {
      await request()
      setStatusMessage(success)
      details.refresh()
    } catch (error) {
      setError(describeError(error))
    } finally {
      setBusy('')
    }
  }

  function updateRun(run: Run) {
    const status = run.status === 'completed' ? 'pending' : 'completed'
    void perform(`run-${run.id}`, () => api.patch(`/troubleshooting/${run.id}`, {
      status, operator_note: notes[run.id] ?? run.operator_note,
    }), status === 'completed' ? 'Step completed.' : 'Step reopened.')
  }

  if (!details.data) return <><Link to="/incidents" className="text-link">Back to incidents</Link>{details.error ? <Notice error message={details.error} /> : <Loading />}</>
  const [incident, candidates, assistant] = details.data
  const currentVerification = verification ?? assistant.verification
  const recommendation = assistant.recommendation
  const timeline = [
    ...incident.alerts.map(alert => ({ key: `alert-${alert.id}`, at: alert.starts_at, title: alert.alertname, description: alert.instance, badge: alert.status })),
    ...incident.history.map(item => ({ key: `history-${item.id}`, at: item.created_at, title: humanize(item.action), description: item.note, badge: '' })),
  ].sort((a, b) => Date.parse(a.at) - Date.parse(b.at))

  return <>
    <Link to="/incidents" className="text-link back-link">Back to incidents</Link>
    <PageHeader title={incident.title} description={`Incident #${incident.id} · Opened ${formatTime(incident.created_at)}`}
      action={<div className="button-row"><Badge value={incident.severity} /><Badge value={incident.status} /></div>} />
    {(error || details.error) && <Notice error message={error || details.error} />}
    {statusMessage && <Notice message={statusMessage} />}
    <div className="detail-layout">
      <div className="detail-column">
        <section className="card"><div className="card-heading"><div><h2>Alert &amp; incident timeline</h2><p>{incident.alerts.length} linked alerts</p></div></div>
          {timeline.length ? <ol className="timeline">{timeline.map(item => <li key={item.key}><div><strong>{item.title}</strong>{item.badge && <Badge value={item.badge} />}</div><p>{item.description}</p><time dateTime={item.at}>{formatTime(item.at)}</time></li>)}</ol> : <Empty>No timeline events.</Empty>}
        </section>
        <section className="card"><div className="card-heading"><div><h2><Workflow size={18} />RCA ranked candidates</h2><p>Supporting evidence by confidence and rank</p></div>
          <button className="button button-secondary" disabled={!!busy} onClick={() => void perform('analyze', () => api.post(`${path}/analyze`), 'Root cause analysis refreshed.')}><ScanLine size={16} />{busy === 'analyze' ? 'Analyzing…' : 'Analyze'}</button></div>
          {candidates.length ? <div className="candidate-list">{candidates.map(candidate => <article className="candidate" key={candidate.id}>
            <div className="candidate-header"><span className="rank">#{candidate.rank}</span><div><h3>{candidate.candidate_component}</h3><p>{Math.round(candidate.confidence_score * 100)}% confidence</p></div><Badge value={candidate.verification_status} /></div>
            <p>{candidate.summary}</p>
            {candidate.evidence.length > 0 && <div className="evidence-list">{candidate.evidence.map(evidence => <div className="evidence" key={evidence.id} id={`evidence-${evidence.id}`}>
              <strong>{humanize(evidence.evidence_type)}</strong><span className="meta">Evidence #{evidence.id} · {formatTime(evidence.observed_at)}</span><p>{evidence.description}</p>
            </div>)}</div>}
            {candidate.missing_data_json.length > 0 && <div className="missing"><strong>Missing data</strong><ul>{candidate.missing_data_json.map(item => <li key={item}>{item}</li>)}</ul></div>}
          </article>)}</div> : <Empty>No RCA candidates yet.</Empty>}
        </section>
      </div>
      <div className="detail-column">
        <section className="card"><div className="card-heading"><div><h2><Sparkles size={18} />AI Assistant</h2><p>Evidence-based incident explanation</p></div>
          <button className="button button-secondary" disabled={!!busy} onClick={() => void perform('explain', () => api.post(`${path}/explain`), 'Explanation saved.')}><Sparkles size={16} />{busy === 'explain' ? 'Generating…' : 'Explain'}</button>
        </div>
          {recommendation ? <div className="card-content explanation">
            <h3>Executive summary</h3><p>{recommendation.executive_summary}</p>
            <h3>Technical explanation</h3><p>{recommendation.technical_explanation}</p>
            <h3>Impact assessment</h3><p>{recommendation.impact_assessment}</p>
            <h3>Limitations</h3><p>{recommendation.limitations_note}</p>
            <div className="meta">{recommendation.model_provider} · {recommendation.model_name}</div>
          </div> : <Empty>Generate an explanation from the available RCA evidence.</Empty>}
        </section>
        <section className="card"><div className="card-heading"><div><h2><ListChecks size={18} />Troubleshooting Checklist</h2><p>Record diagnostic checks and verify recovery.</p></div></div>
          {assistant.troubleshooting_runs.length ? <div className="card-content checklist">{assistant.troubleshooting_runs.map(run => <article key={run.id}>
            <label className="checkbox-label"><input type="checkbox" disabled={!!busy} checked={run.status === 'completed'} onChange={() => updateRun(run)} />{run.step_title}</label>
            <code>{run.command_or_action}</code>
            <label className="meta">Operator note<input value={notes[run.id] ?? run.operator_note ?? ''} onChange={event => setNotes({ ...notes, [run.id]: event.target.value })} maxLength={4000} /></label>
            {notes[run.id] !== undefined && notes[run.id] !== (run.operator_note ?? '') && <button className="button button-secondary" disabled={!!busy}
              onClick={() => void perform(`note-${run.id}`, () => api.patch(`/troubleshooting/${run.id}`, { status: run.status, operator_note: notes[run.id] }), 'Operator note saved.')}>Save note</button>}
          </article>)}</div> : <Empty>No checklist steps yet.</Empty>}
          <div className="card-content"><button className="button" disabled={!!busy} onClick={() => void perform('verify', async () => {
            const response = await api.post<Verification>(`${path}/verify-recovery`)
            setVerification(response.data)
          }, 'Recovery checks finished.')}><CircleCheck size={16} />{busy === 'verify' ? 'Checking…' : 'Verify Recovery'}</button>
          {currentVerification && <div className="verification"><Badge value={currentVerification.is_recovered ? 'recovered' : 'unconfirmed'} />
            {currentVerification.results.map(result => <p key={result.id}><FlaskConical size={15} /><span>{result.target_metric_or_probe}<span className="meta"> · {result.post_fix_value === null ? 'No fresh data' : formatNumber(result.post_fix_value)}</span></span><Badge value={result.is_recovered ? 'passed' : 'failed'} /></p>)}</div>}</div>
        </section>
      </div>
    </div>
  </>
}
