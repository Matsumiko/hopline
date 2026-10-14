# NekoBox Testing Modes Research

## Scope

Read-only review of the NekoBox source at <https://github.com/qr243vbi/NekoBox>, branch `main`, to map the six user-visible test modes to their network behavior and decide which behavior belongs in Hopline health monitoring.

## Findings

| Mode | NekoBox request path | What it measures | Hopline disposition |
|---|---|---|---|
| URL test | `MainWindow::runURLTest` → RPC `Test` → `BatchURLTest`/`urlTest` in `core/server/test_utils.go` | One warm-up `HEAD`, then one measured `GET` through the selected outbound. It records request latency and transport errors. The core URL test does not validate response status/body. | Active health probe. Hopline may use stricter success policy: tunnel established, expected HTTP status, and bounded latency. |
| Full test | `runSpeedTest(FULL)` → `SpeedTestRequest` with download and upload | Speedtest.net server discovery, latency selection, download EWMA, then upload EWMA. Download and upload are sequential. | On-demand diagnostic only. |
| Download test | `runSpeedTest(DL)` | Speedtest.net discovery plus download payload and EWMA download rate. | On-demand diagnostic only. |
| Upload test | `runSpeedTest(UL)` | Speedtest.net discovery plus POST upload payload and EWMA upload rate. | On-demand diagnostic only. |
| Country test | `runSpeedTest(COUNTRY)` → `countryTest` | Speedtest.net server metadata and latency to the selected server. `server_country` is the test server's country, not proof of the node exit IP country. | On-demand location diagnostic only. Use a real IP-geolocation endpoint if exit-country verification becomes a requirement. |
| Simple download test | `runSpeedTest(SIMPLEDL)` → `simpleDownloadTest` | GET to configurable `simple_dl_url`, response latency, and bytes-per-second while copying the body. | On-demand diagnostic; not the default liveness probe because it consumes bandwidth and depends on one URL. |

## Source evidence

- UI labels and actions: [`src/nekobox/ui/mainwindow.ui`](https://github.com/qr243vbi/NekoBox/blob/main/src/nekobox/ui/mainwindow.ui#L1197-L1275).
- UI dispatch: [`src/gharqad/ui/mainwindow.cpp`](https://github.com/qr243vbi/NekoBox/blob/main/src/gharqad/ui/mainwindow.cpp#L1765-L1818).
- RPC request/result handling, polling, and cancellation: [`src/gharqad/ui/mainwindow_rpc.cpp`](https://github.com/qr243vbi/NekoBox/blob/main/src/gharqad/ui/mainwindow_rpc.cpp#L79-L180) and [`#L536-L631`](https://github.com/qr243vbi/NekoBox/blob/main/src/gharqad/ui/mainwindow_rpc.cpp#L536-L631).
- Mode enum (`FULL`, `DL`, `UL`, `SIMPLEDL`, `COUNTRY`): [`src/nekobox/dataStore/Const.hpp`](https://github.com/qr243vbi/NekoBox/blob/main/src/nekobox/dataStore/Const.hpp#L32-L42).
- URL test and simple-download implementation: [`core/server/test_utils.go`](https://github.com/qr243vbi/NekoBox/blob/main/core/server/test_utils.go#L112-L201) and [`#L280-L340`](https://github.com/qr243vbi/NekoBox/blob/main/core/server/test_utils.go#L280-L340).
- Speedtest discovery, country, and speed-test orchestration: [`core/server/test_utils.go`](https://github.com/qr243vbi/NekoBox/blob/main/core/server/test_utils.go#L214-L430).
- Speedtest GET/POST and EWMA measurement: [`core/server/speedtest/request.go`](https://github.com/qr243vbi/NekoBox/blob/main/core/server/speedtest/request.go#L163-L200) and related `server.go`/`data_manager.go`.
- Active autotester policy: [`src/gharqad/stats/autotester/ProxyAutoTester.cpp`](https://github.com/qr243vbi/NekoBox/blob/main/src/gharqad/stats/autotester/ProxyAutoTester.cpp#L34-L65) and [`#L143-L194`](https://github.com/qr243vbi/NekoBox/blob/main/src/gharqad/stats/autotester/ProxyAutoTester.cpp#L143-L194).
- Defaults: [`src/nekobox/dataStore/DataStore.hpp`](https://github.com/qr243vbi/NekoBox/blob/main/src/nekobox/dataStore/DataStore.hpp#L176-L215). The URL test default is `http://cp.cloudflare.com/`; simple download defaults to `http://cachefly.cachefly.net/1mb.test`; URL and speed tests have separate timeouts.

## Hopline decision

1. `ActiveProbeScheduler` remains the periodic health mechanism and tests each node through its own sing-box-authenticated outbound.
2. URL/HTTP probing is the only NekoBox-like mode suitable for periodic health. It is bounded, low-cost, and tests reachability through the selected node.
3. Full/download/upload/country/simple-download are not silently added to periodic health. They require explicit diagnostic commands and separate traffic/retention policy.
4. Hopline's HTTP probe is stricter than NekoBox's raw URL test: an HTTP status in `200..399` is required after CONNECT. This avoids treating an authentication page or provider error as a healthy node.
5. Country verification is not inferred from a speed-test server's country metadata. A future country feature must use an explicit geolocation target and be recorded separately from node health.

## Verification boundary

Forced node selection is a routing invariant, not a health-test mode. The gateway must try only `node-<id>` and must not fall back when that node cannot establish a tunnel. Periodic health probes and forced-node smoke tests therefore remain separate acceptance checks.
