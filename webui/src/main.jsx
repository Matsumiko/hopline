import { StrictMode, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const HEALTH_STATES = ["healthy", "degraded", "dead", "quarantine", "unknown"];

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
  async function refresh() {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setLoading(true);
    setError("");
    try {
      const [nextStatus, nextNodes] = await Promise.all([getJson("/status", controller.signal), getJson("/nodes", controller.signal)]);
      if (controller.signal.aborted) return;
      setStatus(nextStatus);
      setNodes(nextNodes.nodes ?? []);
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
        <div className="topbar-meta"><span className="live-dot" /> <span>localhost only</span><button className="refresh-button" onClick={refresh} disabled={loading}>{loading ? "Refreshing" : "Refresh data"}</button></div>
      </header>

      <main className="content">
        <section className="intro-row">
          <div><p className="kicker">Operations / runtime view</p><h1>Node control, without the noise.</h1><p className="lede">A compact view of the active egress pool, health signals, and routing inventory.</p></div>
          <div className="runtime-note"><span className="status-dot" /> <div><strong>Control API</strong><span>{error ? "Connection unavailable" : "Connected on 127.0.0.1"}</span></div></div>
        </section>

        {error && <section className="error-banner" role="alert"><strong>Panel cannot load live data.</strong><span>{error}</span><button onClick={refresh}>Try again</button></section>}

        <section className="stats-grid" aria-label="Runtime summary">
          <StatCard label="Total nodes" value={formatCount(status?.nodes)} detail={`Schema v${status?.schema_version ?? "not available"}`} accent />
          <StatCard label="Healthy pool" value={formatCount(healthy)} detail={`${formatCount(degraded)} degraded`} />
          <StatCard label="Protocols" value={formatCount(Object.keys(status?.protocols ?? {}).length)} detail={`${formatCount(Object.keys(status?.countries ?? {}).length)} country groups`} />
          <StatCard label="Last refresh" value={lastUpdated ? lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "Not available"} detail="Auto-refresh every 30 seconds" />
        </section>

        <section className="health-panel panel"><div className="section-heading"><div><p className="eyebrow">Pool health</p><h2>Current distribution</h2></div><span className="muted">{formatCount(healthTotal)} registered nodes</span></div><HealthBar health={status?.health} total={healthTotal} /><div className="legend">{HEALTH_STATES.map((state) => <span key={state}><i className={`legend-dot ${state}`} />{state}<b>{formatCount(status?.health?.[state])}</b></span>)}</div></section>

        <section className="nodes-panel panel"><div className="section-heading"><div><p className="eyebrow">Inventory</p><h2>Nodes</h2></div><span className="muted">Showing {formatCount(filteredNodes.length)} of {formatCount(nodes.length)}</span></div>
          <div className="filters"><label className="search-field"><span>Search</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ID, server, country" /></label><label><span>Protocol</span><select value={protocol} onChange={(event) => setProtocol(event.target.value)}>{protocols.map((item) => <option key={item} value={item}>{item === "all" ? "All protocols" : item.toUpperCase()}</option>)}</select></label><label><span>Health</span><select value={health} onChange={(event) => setHealth(event.target.value)}><option value="all">All states</option>{HEALTH_STATES.map((item) => <option key={item} value={item}>{item}</option>)}</select></label></div>
          {loading && !nodes.length ? <div className="loading-state"><span className="skeleton wide" /><span className="skeleton" /><span className="skeleton" /></div> : filteredNodes.length ? <div className="table-wrap"><table><thead><tr><th>Node</th><th>Protocol</th><th>Health</th><th>Latency</th><th>Exit metadata</th><th>Last probe</th></tr></thead><tbody>{filteredNodes.map((node) => <tr key={node.id}><td><div className="node-cell"><strong>{node.name || node.id}</strong><span>{node.id} · {node.server}:{node.port}</span></div></td><td><span className="protocol-tag">{node.protocol}</span></td><td><span className={`health-tag ${node.health}`}><i />{node.health}</span></td><td className="mono">{formatLatency(node.latency_ms)}</td><td>{node.geolocation ? <div className="geo-cell"><strong>{node.geolocation.country_code}</strong><span>{node.geolocation.ip}</span></div> : <span className="muted">Not available</span>}</td><td className="muted">{formatCheckedAt(node.geolocation?.checked_at)}</td></tr>)}</tbody></table></div> : <div className="empty-state"><strong>No nodes match these filters.</strong><span>Try clearing the search or selecting another health state.</span></div>}
        </section>
      </main>
      <footer><span>Hopline control panel</span><span>{lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : "Waiting for control API"}</span></footer>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<StrictMode><App /></StrictMode>);
