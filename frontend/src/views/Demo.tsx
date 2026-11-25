import { FlaskConical, Network, Play, RotateCcw, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, describeError, get } from '../api'
import { Badge, Empty, Loading, Notice, PageHeader } from '../components'
import { useData } from '../hooks'

type Scenario = { id: string; title: string; description: string; active_incident_id: number | null }
type ScenarioResult = { scenario: string; incident_id: number | null; status: 'active' | 'resolved' | 'inactive' }
const loadScenarios = (signal: AbortSignal) => get<Scenario[]>('/simulator/scenarios', signal)

export function Demo() {
  const scenarios = useData(loadScenarios)
  const navigate = useNavigate()
  const [pending, setPending] = useState('')
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')

  async function perform(key: string, action: () => Promise<void>) {
    setPending(key)
    setError('')
    setMessage('')
    try {
      await action()
    } catch (error) {
      setError(describeError(error))
    } finally {
      setPending('')
      scenarios.refresh()
    }
  }

  async function trigger(scenario: Scenario) {
    const { data } = await api.post<ScenarioResult>(`/simulator/trigger/${encodeURIComponent(scenario.id)}`)
    if (data.incident_id === null) throw new Error('The simulator did not return an incident.')
    navigate(`/incidents/${data.incident_id}`)
  }

  async function recoverAll() {
    const active = (scenarios.data ?? []).filter(scenario => scenario.active_incident_id !== null)
    let recovered = 0
    for (const scenario of active) {
      const { data } = await api.post<ScenarioResult>(`/simulator/recover/${encodeURIComponent(scenario.id)}`)
      if (data.status === 'resolved') recovered++
    }
    setMessage(`Recovered ${recovered} simulated scenario(s).`)
  }

  return <>
    <PageHeader title="Demo Simulator" description="Run simulated outages, inspect their incidents and RCA, then verify simulated recovery."
      action={<button className="button button-secondary" disabled={!!pending} onClick={() => void perform('seed', async () => {
        await api.post('/simulator/seed-topology')
        setMessage('The HCM-HQ-Lab topology is ready.')
      })}><Network size={16} />{pending === 'seed' ? 'Seeding…' : 'Seed topology'}</button>} />
    {(error || scenarios.error) && <Notice error message={error || scenarios.error} />}
    {message && <Notice message={message} />}
    <section className="card">
      <div className="card-heading"><div><h2><FlaskConical size={18} />Outage scenarios</h2><p>Scenario events and recovery checks use isolated demo data.</p></div></div>
      {scenarios.data?.length ? <div className="scenario-list">{scenarios.data.map((scenario, index) => <article className="candidate" key={scenario.id}>
        <h3>{index + 1}. {scenario.title}</h3><p>{scenario.description}</p>
        {scenario.active_incident_id !== null && <p><Badge value="running" /> <Link className="text-link" to={`/incidents/${scenario.active_incident_id}`}>View incident</Link></p>}
        <button className="button" disabled={!!pending} onClick={() => void perform(scenario.id, () => trigger(scenario))}><Play size={16} />{pending === scenario.id ? 'Starting…' : scenario.active_incident_id === null ? 'Run scenario' : 'Open incident'}</button>
      </article>)}</div> : scenarios.loading ? <Loading /> : <Empty>No scenarios available.</Empty>}
    </section>
    <section className="card section-gap">
      <div className="card-heading"><div><h2>Demo controls</h2><p>Recover active scenarios or clear their incident and anomaly history.</p></div></div>
      <div className="card-content button-row flex-wrap">
        <button className="button button-secondary" disabled={!!pending || !scenarios.data?.some(scenario => scenario.active_incident_id !== null)}
          onClick={() => void perform('recover', recoverAll)}><ShieldCheck size={16} />{pending === 'recover' ? 'Recovering…' : 'Recover All'}</button>
        <button className="button button-secondary danger" disabled={!!pending || !scenarios.data}
          onClick={() => {
            if (window.confirm('Clear all simulated incidents and anomalies? The lab topology will be kept.')) {
              void perform('reset', async () => {
                const { data } = await api.post<{ deleted_incidents: number }>('/simulator/reset')
                setMessage(`Cleared ${data.deleted_incidents} simulated incident(s). The lab topology was kept.`)
              })
            }
          }}><RotateCcw size={16} />{pending === 'reset' ? 'Resetting…' : 'Reset Demo Data'}</button>
      </div>
    </section>
  </>
}
