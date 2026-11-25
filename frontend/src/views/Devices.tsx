import { ArrowRight, GitBranch, Network, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import type { FormEvent } from 'react'
import { api, describeError, get, humanize } from '../api'
import type { Dependency, Device, NetworkHealth, Site } from '../api'
import { Badge, Empty, Loading, Modal, Notice, PageHeader } from '../components'
import { useData } from '../hooks'

const deviceTypes = ['router', 'switch', 'firewall', 'server']
const dependencyTypes = ['physical_link', 'routing_next_hop', 'vpn_tunnel', 'hosted_service']
const loadInventory = (signal: AbortSignal) => Promise.all([
  get<Device[]>('/devices', signal), get<Site[]>('/sites', signal), get<Dependency[]>('/dependencies', signal),
])
const loadHealth = (signal: AbortSignal) => get<NetworkHealth>('/network-health', signal)

export function Devices() {
  const inventory = useData(loadInventory)
  const health = useData(loadHealth, 15_000)
  const [devices, sites, dependencies] = inventory.data ?? [[], [], []]
  const [modal, setModal] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [modalError, setModalError] = useState('')
  const name = (id: number) => devices.find(device => device.id === id)?.hostname ?? `Device #${id}`

  async function addDevice(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const values = new FormData(event.currentTarget)
    setBusy(true)
    setModalError('')
    try {
      await api.post('/devices', {
        hostname: values.get('hostname'), ip_address: values.get('ip_address'),
        site_id: Number(values.get('site_id')), device_type: values.get('device_type'),
        vendor: values.get('vendor') || null, monitoring_enabled: values.has('monitoring_enabled'),
      })
      setModal(false)
      inventory.refresh()
      health.refresh()
    } catch (error) {
      setModalError(describeError(error))
    } finally {
      setBusy(false)
    }
  }

  async function changeLink(id: number | null, event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    const form = event?.currentTarget
    const values = form ? new FormData(form) : null
    setBusy(true)
    setError('')
    try {
      if (id !== null) await api.delete(`/dependencies/${id}`)
      else if (values) {
        const upstream_device_id = Number(values.get('upstream'))
        const downstream_device_id = Number(values.get('downstream'))
        if (upstream_device_id === downstream_device_id) throw new Error('Choose two different devices.')
        await api.post('/dependencies', { upstream_device_id, downstream_device_id, dependency_type: values.get('link_type') })
        form?.reset()
      }
      inventory.refresh()
    } catch (error) {
      setError(describeError(error))
    } finally {
      setBusy(false)
    }
  }

  return <>
    <PageHeader title="Device Inventory" description="Manage monitored devices and the dependency links between them."
      action={<button className="button" disabled={!sites.length} onClick={() => { setModalError(''); setModal(true) }}><Plus size={18} />Add device</button>} />
    {inventory.error && <Notice error message={inventory.error} />}
    {health.error && <Notice message="Live device health is unavailable." />}
    {inventory.data && !sites.length && <Notice message="The inventory has no sites. Add a site through the inventory API before creating devices." />}
    <section className="card">
      <div className="card-heading"><div><h2><Network size={18} />Sites &amp; devices</h2><p>{sites.length} sites · {devices.length} devices</p></div></div>
      {sites.length > 0 && <div className="site-list">{sites.map(site => <span key={site.id}>{site.name}{site.location ? ` · ${site.location}` : ''}</span>)}</div>}
      {devices.length ? <div className="table-scroll"><table><thead><tr><th>Hostname</th><th>Site</th><th>Address</th><th>Type</th><th>Status</th></tr></thead>
        <tbody>{devices.map(device => <tr key={device.id}>
          <td><strong>{device.hostname}</strong>{device.vendor && <div className="meta">{device.vendor}</div>}</td>
          <td>{sites.find(site => site.id === device.site_id)?.name ?? `Site #${device.site_id}`}</td>
          <td className="mono">{device.ip_address}</td><td>{humanize(device.device_type)}</td>
          <td><Badge value={device.monitoring_enabled ? health.data?.device_statuses[device.id] ?? device.status : 'disabled'} /></td>
        </tr>)}</tbody></table></div> : inventory.loading ? <Loading /> : <Empty>No devices registered.</Empty>}
    </section>
    <section className="card section-gap">
      <div className="card-heading"><div><h2><GitBranch size={18} />Dependency Mapping</h2><p>Track upstream and downstream device relationships.</p></div></div>
      <form className="inline-form" onSubmit={event => void changeLink(null, event)}>
        <label>Upstream<select name="upstream" required defaultValue=""><option disabled value="">Select a device</option>{devices.map(device => <option key={device.id} value={device.id}>{device.hostname}</option>)}</select></label>
        <label>Downstream<select name="downstream" required defaultValue=""><option disabled value="">Select a device</option>{devices.map(device => <option key={device.id} value={device.id}>{device.hostname}</option>)}</select></label>
        <label>Link type<select name="link_type">{dependencyTypes.map(type => <option key={type} value={type}>{humanize(type)}</option>)}</select></label>
        <button className="button button-secondary" disabled={busy || devices.length < 2}><Plus size={16} />Add link</button>
      </form>
      {error && <Notice error message={error} />}
      {dependencies.length ? <div className="table-scroll"><table><thead><tr><th>Directed link</th><th>Type</th><th>Action</th></tr></thead><tbody>
        {dependencies.map(link => <tr key={link.id}><td><span className="dependency-link">{name(link.upstream_device_id)}<ArrowRight size={17} aria-label="to" />{name(link.downstream_device_id)}</span></td>
          <td>{humanize(link.dependency_type)}</td><td><button className="icon-button danger" onClick={() => void changeLink(link.id)} disabled={busy} aria-label={`Remove link from ${name(link.upstream_device_id)} to ${name(link.downstream_device_id)}`}><Trash2 size={17} /></button></td></tr>)}
      </tbody></table></div> : <Empty>No dependency links defined.</Empty>}
    </section>
    {modal && <Modal title="Add device" close={() => { if (!busy) setModal(false) }}>
      <form className="modal-form" onSubmit={addDevice}>
        <label>Hostname<input name="hostname" required maxLength={253} /></label>
        <label>IP address or DNS name<input name="ip_address" required maxLength={253} /></label>
        <label>Site<select name="site_id" required defaultValue=""><option disabled value="">Select a site</option>{sites.map(site => <option key={site.id} value={site.id}>{site.name}</option>)}</select></label>
        <label>Device type<select name="device_type">{deviceTypes.map(type => <option key={type}>{type}</option>)}</select></label>
        <label>Vendor <span className="meta">Optional</span><input name="vendor" maxLength={255} /></label>
        <label className="checkbox-label"><input type="checkbox" name="monitoring_enabled" defaultChecked />Enable monitoring</label>
        {modalError && <Notice error message={modalError} />}
        <div className="button-row"><button type="button" className="button button-secondary" disabled={busy} onClick={() => setModal(false)}>Cancel</button><button className="button" disabled={busy}>{busy ? 'Saving…' : 'Add device'}</button></div>
      </form>
    </Modal>}
  </>
}
