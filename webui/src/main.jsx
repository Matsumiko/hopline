import { StrictMode, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const HEALTH_STATES = ["healthy", "degraded", "dead", "quarantine", "unknown"];

function DocsContent() {
  return (
    <div className="docs-content">
      <section className="docs-section">
        <p className="kicker">Guide</p>
        <h2>Quick start</h2>
        <p>Set the proxy environment variable and use any HTTP client.</p>
        <pre className="code-block">{'export HTTPS_PROXY=http://hopline:your-password@127.0.0.1:18770\ncurl https://api.ipify.org'}</pre>
        <p>The gateway selects a healthy node per connection. Use <code>rotate</code> by default; see routing below for explicit selection.</p>
      </section>

      <section className="docs-section">
        <p className="kicker">Subscriptions</p>
        <h2>Managing sources</h2>
        <p>Add subscription URLs in the <strong>Sources</strong> panel above. The daemon fetches them on schedule or when you click <strong>Sync now</strong>. Subscriptions are stored in the database; the TOML config file seeds them once on startup.</p>
        <p>To <strong>delete</strong> a source, use the red Delete button on its row. The daemon retires the orphan nodes in a background sync.</p>
        <p>Large subscriptions (&gt; 2 000 entries) are clipped to <code>max_nodes</code>. The body must stay under <code>max_body_bytes</code> (10 MiB default).</p>
      </section>

      <section className="docs-section">
        <p className="kicker">Routing</p>
        <h2>Proxy username grammar</h2>
        <p>The username you send in <code>Proxy-Authorization</code> controls how the gateway picks a node.</p>
        <div className="table-wrap"><table><thead><tr><th>Username</th><th>Behaviour</th></tr></thead><tbody>
          <tr><td className="mono">hopline (default)</td><td>rotate — round-robin across healthy nodes.</td></tr>
          <tr><td className="mono">node-&lt;id&gt;</td><td>Force a specific node. No fallback.</td></tr>
          <tr><td className="mono">sticky-&lt;sess&gt;</td><td>Bind session to one node (TTL 10 min). Rebinds if dead.</td></tr>
          <tr><td className="mono">country-&lt;cc&gt;</td><td>Pick a node whose exit geolocation matches the country code.</td></tr>
          <tr><td className="mono">ipv4 / ipv6</td><td>Pick a node proven to egress via that address family.</td></tr>
          <tr><td className="mono">*-sticky-&lt;sess&gt;</td><td>Combine sticky with a country or family route.</td></tr>
        </tbody></table></div>
      </section>

      <section className="docs-section">
        <p className="kicker">Health</p>
        <h2>Node states</h2>
        <div className="table-wrap"><table><thead><tr><th>State</th><th>Meaning</th></tr></thead><tbody>
          <tr><td><span className="health-tag healthy"><i />healthy</span></td><td>Actively probed and responding.</td></tr>
          <tr><td><span className="health-tag degraded"><i />degraded</span></td><td>One or two recent failures; still eligible, but in cooldown.</td></tr>
          <tr><td><span className="health-tag dead"><i />dead</span></td><td>Three consecutive failures; excluded until probed again.</td></tr>
          <tr><td><span className="health-tag quarantine"><i />quarantine</span></td><td>Manually disabled via the panel. Click <strong>Enable</strong> to return.</td></tr>
          <tr><td><span className="health-tag unknown"><i />unknown</span></td><td>Not yet probed. Eligible but unrated.</td></tr>
        </tbody></table></div>
        <p className="muted" style={{marginTop: 16}}>Cooldown: 30 s after a failure. Backoff: 60 s → 120 s → 5 min → 15 min → 1 h. Recovery: three consecutive probe successes.</p>
      </section>

      <section className="docs-section">
        <p className="kicker">CLI</p>
        <h2>Commands</h2>
        <pre className="code-block">{'python3 -m hopline doctor --json          # check prerequisites\npython3 -m hopline status --json           # live pool summary\npython3 -m hopline nodes --json            # full node list\npython3 -m hopline geo --all --limit 10    # refresh country metadata\npython3 -m hopline run --config hopline.toml'}</pre>
        <p>Use <code>--once</code> for a single sync cycle. The <code>test</code> command fetches and parses a subscription without running sing-box.</p>
      </section>
    </div>
  );
}

function formatCount(value) {
  return new Intl.NumberFormat("en-US").format(value ?? 0);
}

function formatLatency(value) {
  return value == null ? "Not available" : `${Math.round(value)} ms`;
}


function formatCheckedAt(value) {
  if (!value) return "Not checked";
  return new Date(value * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function formatUptime(value) {
  if (!value) return "Not available";
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - value));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

async function getJson(path, signal) {
  const response = await fetch(path, { signal, headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`Control API returned HTTP ${response.status}`);
  return response.json();
}

function StatCard({ label, value, detail, accent }) {
  return (
    <article className={`stat-card ${accent ? "stat-card-accent" : ""}`}>
      <p className="eyebrow">{label}</p>
      <strong>{value}</strong>
      <span>{detail}</span>
    </article>
  );
}

function HealthBar({ health, total }) {
  return (
    <div className="health-bar" aria-label="Node health distribution">
      {HEALTH_STATES.map((state) => {
        const count = health?.[state] ?? 0;
        return <span key={state} className={`health-segment ${state}`} style={{ width: `${total ? (count / total) * 100 : 0}%` }} title={`${state}: ${count}`} />;
      })}
    </div>
  );
}

function App() {
  const [status, setStatus] = useState(null);
  const [nodes, setNodes] = useState([]);
  const [query, setQuery] = useState("");
  const [protocol, setProtocol] = useState("all");
  const controllerRef = useRef(null);
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState("all");
  const [error, setError] = useState("");
  const [lastUpdated, setLastUpdated] = useState(null);
  const [syncing, setSyncing] = useState(false);
  const [syncResult, setSyncResult] = useState("");
  const [actionResults, setActionResults] = useState({});
  const [expandedNodes, setExpandedNodes] = useState(new Set());
  const [subscriptions, setSubscriptions] = useState(null);
  const [service, setService] = useState(null);
  const [showDocs, setShowDocs] = useState(false);
  const [addUrl, setAddUrl] = useState("");
  const [addingSub, setAddingSub] = useState(false);
  const [addError, setAddError] = useState("");

  async function nodeAction(nodeId, action) {
    setActionResults((prev) => ({ ...prev, [nodeId]: { ...prev[nodeId], [action]: "pending" } }));
    try {
      const response = await fetch(`/nodes/${nodeId}/${action}`, { method: "POST", headers: { Accept: "application/json" } });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${response.status}`);
      }
      const payload = await response.json();
      setActionResults((prev) => ({ ...prev, [nodeId]: { ...prev[nodeId], [action]: `ok: ${payload.state}` } }));
      refresh();
    } catch (cause) {
      setActionResults((prev) => ({ ...prev, [nodeId]: { ...prev[nodeId], [action]: cause.message || "failed" } }));
    }
  }
  async function refresh() {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError("");
    try {
      const [nextStatus, nextNodes, nextSubscriptions, nextService] = await Promise.all([
        getJson("/status", controller.signal),
        getJson("/nodes", controller.signal),
        getJson("/subscriptions", controller.signal).catch(() => null),
        getJson("/service", controller.signal).catch(() => null),
      ]);
      if (controller.signal.aborted) return;
      setStatus(nextStatus);
      setNodes(nextNodes.nodes ?? []);
      if (nextSubscriptions) setSubscriptions(nextSubscriptions);
      if (nextService) setService(nextService);
      setLastUpdated(new Date());
    } catch (cause) {
      if (cause.name !== "AbortError" && !controller.signal.aborted) setError(cause.message || "Unable to reach the control API.");
    } finally {
      if (controllerRef.current === controller) {
        controllerRef.current = null;
        setLoading(false);
      }
    }
  }

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, 30000);
    return () => {
      window.clearInterval(timer);
      controllerRef.current?.abort();
    };
  }, []);


  async function syncNow() {
    setSyncing(true);
    setSyncResult("");
    try {
      const response = await fetch("/sync", { method: "POST", headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(`Control API returned HTTP ${response.status}`);
      const payload = await response.json();
      setSyncResult(`Synced ${payload.synced} source(s)`);
      refresh();
    } catch (cause) {
      if (cause.name !== "AbortError") setSyncResult(`Sync failed: ${cause.message || "Unknown error"}`);
    } finally {
      setSyncing(false);
    }
  }

  async function addSubscription() {
    const url = addUrl.trim();
    if (!url) return;
    setAddingSub(true);
    setAddError("");
    try {
      const response = await fetch("/subscriptions/add", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ url }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${response.status}`);
      }
      setAddUrl("");
      refresh();
    } catch (cause) {
      setAddError(cause.message || "Failed to add subscription");
    } finally {
      setAddingSub(false);
    }
  }

  async function deleteSubscription(digest) {
    try {
      const response = await fetch("/subscriptions/delete", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ digest }),
      });
      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${response.status}`);
      }
      refresh();
    } catch (cause) {
      setAddError(cause.message || "Failed to delete subscription");
    }
  }

  function toggleNode(nodeId) {
    setExpandedNodes((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  }

  const protocols = useMemo(() => ["all", ...Object.keys(status?.protocols ?? {}).sort()], [status]);
  const filteredNodes = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    return nodes.filter((node) => {
      const matchesQuery = !normalized || [node.id, node.name, node.server, node.geolocation?.country_code].filter(Boolean).some((value) => String(value).toLowerCase().includes(normalized));
      return matchesQuery && (protocol === "all" || node.protocol === protocol) && (health === "all" || node.health === health);
    });
  }, [nodes, query, protocol, health]);

  const healthTotal = Object.values(status?.health ?? {}).reduce((sum, value) => sum + value, 0);
  const healthy = status?.health?.healthy ?? 0;
  const degraded = status?.health?.degraded ?? 0;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup"><span className="brand-mark">H</span><div><strong>hopline</strong><span>local egress control</span></div></div>
        <div className="topbar-meta"><span className="live-dot" /> <span>localhost only</span><button className="refresh-button" onClick={() => setShowDocs((value) => !value)}>{showDocs ? "Close docs" : "Docs"}</button><button className="refresh-button" onClick={syncNow} disabled={syncing}>{syncing ? "Syncing" : "Sync now"}</button><button className="refresh-button" onClick={refresh} disabled={loading}>{loading ? "Refreshing" : "Refresh data"}</button></div>
      </header>

      <main className="content">
        {showDocs ? <DocsContent /> : <>
        <section className="intro-row">
          <div><p className="kicker">Operations / runtime view</p><h1>Node control, without the noise.</h1><p className="lede">A compact view of the active egress pool, health signals, and routing inventory.</p></div>
          <div className="runtime-note"><span className="status-dot" /> <div><strong>Control API</strong><span>{error ? "Connection unavailable" : `:${service?.generation_port ?? "18772"} · ${service?.started_at ? formatUptime(service.started_at) : "running"}`}</span></div></div>
            {syncResult && <div className="sync-result">{syncResult}</div>}
        </section>

        {error && <section className="error-banner" role="alert"><strong>Panel cannot load live data.</strong><span>{error}</span><button onClick={refresh}>Try again</button></section>}

        <section className="stats-grid" aria-label="Runtime summary">
          <StatCard label="Total nodes" value={formatCount(status?.nodes)} detail={`Schema v${status?.schema_version ?? "not available"}`} accent />
          <StatCard label="Healthy pool" value={formatCount(healthy)} detail={`${formatCount(degraded)} degraded`} />
          <StatCard label="Protocols" value={formatCount(Object.keys(status?.protocols ?? {}).length)} detail={`${formatCount(Object.keys(status?.countries ?? {}).length)} country groups`} />
          <StatCard label="Last refresh" value={lastUpdated ? lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Not available"} detail="Auto-refresh every 30 seconds" />
        </section>

        <section className="health-panel panel"><div className="section-heading"><div><p className="eyebrow">Pool health</p><h2>Current distribution</h2></div><span className="muted">{formatCount(healthTotal)} registered nodes</span></div><HealthBar health={status?.health} total={healthTotal} /><div className="legend">{HEALTH_STATES.map((state) => <span key={state}><i className={`legend-dot ${state}`} />{state}<b>{formatCount(status?.health?.[state])}</b></span>)}</div></section>

        <section className="subscriptions-panel panel"><div className="section-heading"><div><p className="eyebrow">Sources</p><h2>Subscriptions</h2></div><span className="muted">{formatCount(subscriptions?.subscriptions?.length ?? 0)} source(s)</span></div><div className="sub-add-row"><input className="sub-add-input" type="text" value={addUrl} onChange={(event) => setAddUrl(event.target.value)} placeholder="https://example.com/rules.json" disabled={addingSub} /><button className="action-btn" onClick={addSubscription} disabled={addingSub || !addUrl.trim()}>{addingSub ? "Adding…" : "Add subscription"}</button></div>{addError && <div className="sub-add-error" role="alert">{addError}</div>}{subscriptions?.subscriptions?.length > 0 && <div className="table-wrap"><table className="sub-table"><thead><tr><th>Source</th><th>Scheme</th><th>Status</th><th>Nodes</th><th>Snapshot</th><th>Updated</th><th></th></tr></thead><tbody>{subscriptions.subscriptions.map((sub) => <tr key={sub.source}><td><span className="sub-source">{sub.source}</span></td><td><span className="protocol-tag">{sub.scheme}</span></td><td><span className={`health-tag ${sub.valid ? "healthy" : "dead"}`}><i />{sub.valid ? "valid" : "invalid"}</span></td><td><span className="source-count">{formatCount(sub.nodes)}</span></td><td className="mono">{sub.snapshot_hash ? sub.snapshot_hash.slice(0, 12) : ""}</td><td className="muted">{sub.updated_at ? new Date(sub.updated_at + "Z").toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : ""}</td><td>{<button className="action-btn danger" onClick={() => deleteSubscription(sub.digest)}>Delete</button>}</td></tr>)}</tbody></table></div>}</section>

        <section className="nodes-panel panel"><div className="section-heading"><div><p className="eyebrow">Inventory</p><h2>Nodes</h2></div><span className="muted">Showing {formatCount(filteredNodes.length)} of {formatCount(nodes.length)}</span></div>
          <div className="filters"><label className="search-field"><span>Search</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ID, server, country" /></label><label><span>Protocol</span><select value={protocol} onChange={(event) => setProtocol(event.target.value)}>{protocols.map((item) => <option key={item} value={item}>{item === "all" ? "All protocols" : item.toUpperCase()}</option>)}</select></label><label><span>Health</span><select value={health} onChange={(event) => setHealth(event.target.value)}><option value="all">All states</option>{HEALTH_STATES.map((item) => <option key={item} value={item}>{item}</option>)}</select></label></div>
          {loading && !nodes.length ? <div className="loading-state"><span className="skeleton wide" /><span className="skeleton" /><span className="skeleton" /></div> : filteredNodes.length ? <div className="table-wrap"><table><thead><tr><th>Node</th><th>Protocol</th><th>Health</th><th>Latency</th><th>Exit metadata</th><th>Last probe</th><th>Actions</th></tr></thead><tbody>{filteredNodes.map((node) => {
              const expanded = expandedNodes.has(node.id);
              return <>
                <tr key={node.id} className={expanded ? "expanded" : ""} onClick={() => toggleNode(node.id)}>
                  <td><div className="node-cell"><strong>{node.name || node.id}</strong><span>{node.id} · {node.server}:{node.port}</span></div></td>
                  <td><span className="protocol-tag">{node.protocol}</span></td>
                  <td><span className={`health-tag ${node.health}`}><i />{node.health}</span></td>
                  <td className="mono">{formatLatency(node.latency_ms)}</td>
                  <td>{node.geolocation ? <div className="geo-cell"><strong>{node.geolocation.country_code}</strong><span>{node.geolocation.ip}</span></div> : <span className="muted">Not available</span>}</td>
                  <td className="muted">{formatCheckedAt(node.geolocation?.checked_at)}</td>
                  <td><div className="row-actions"><button className="action-btn" onClick={(e) => { e.stopPropagation(); nodeAction(node.id, "probe"); }} disabled={actionResults[node.id]?.probe === "pending"}>Probe</button><button className="action-btn" onClick={(e) => { e.stopPropagation(); nodeAction(node.id, "enable"); }} disabled={actionResults[node.id]?.enable === "pending"}>Enable</button><button className="action-btn danger" onClick={(e) => { e.stopPropagation(); nodeAction(node.id, "disable"); }} disabled={actionResults[node.id]?.disable === "pending"}>Disable</button><span className="action-status">{actionResults[node.id]?.probe || actionResults[node.id]?.enable || actionResults[node.id]?.disable || ""}</span></div></td>
                </tr>
                {expanded && <tr className="node-detail"><td colSpan={7}>
                  <div className="node-detail-grid">
                    {node.geolocation && <div className="node-detail-block"><strong>Geolocation</strong><span>{node.geolocation.country} ({node.geolocation.country_code})</span><span>ASN: {node.geolocation.asn || "—"}</span><span>Org: {node.geolocation.organization || "—"}</span><span>Provider: {node.geolocation.provider || "—"}</span><span>Exit IP: {node.geolocation.ip}</span><span>Checked: {formatCheckedAt(node.geolocation.checked_at)}</span></div>}
                    <div className="node-detail-block"><strong>Capabilities</strong><div className="cap-list">{node.capabilities?.ipv4?.capable && <span className="cap-tag">IPv4</span>}{node.capabilities?.ipv6?.capable && <span className="cap-tag">IPv6</span>}{!node.capabilities?.ipv4?.capable && !node.capabilities?.ipv6?.capable && <span className="muted">None reported</span>}</div></div>
                    {node.capabilities?.ipv4?.ip && <div className="node-detail-block"><strong>IPv4 Exit IP</strong><span>{node.capabilities.ipv4.ip}</span><span>Checked: {formatCheckedAt(node.capabilities.ipv4.checked_at)}</span>{node.capabilities.ipv4.last_error && <span className="muted">Error: {node.capabilities.ipv4.last_error}</span>}</div>}
                    {node.capabilities?.ipv6?.ip && <div className="node-detail-block"><strong>IPv6 Exit IP</strong><span>{node.capabilities.ipv6.ip}</span><span>Checked: {formatCheckedAt(node.capabilities.ipv6.checked_at)}</span>{node.capabilities.ipv6.last_error && <span className="muted">Error: {node.capabilities.ipv6.last_error}</span>}</div>}
                    <div className="node-detail-block"><strong>Stats</strong><span>Successes: {formatCount(node.successes)}</span><span>Failures: {formatCount(node.failures)}</span></div>
                  </div>
                </td></tr>}
              </>;
            })}</tbody></table></div> : <div className="empty-state"><strong>No nodes match these filters.</strong><span>Try clearing the search or selecting another health state.</span></div>}
        </section>
      </>}
      </main>
      <footer><span>Hopline control panel</span><span>{lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "Waiting for control API"}</span></footer>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<StrictMode><App /></StrictMode>);
