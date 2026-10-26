# mcp-fortianalyzer

A [Model Context Protocol](https://modelcontextprotocol.io) (MCP) server that
exposes the **FortiAnalyzer JSON-RPC API** as MCP tools, built on
[FastMCP](https://gofastmcp.com).

It gives an MCP client (Claude Desktop, LM Studio, an agent, etc.) read-heavy
SOC / log-analysis access to a FortiAnalyzer appliance: log search, FortiView
queries, reports, incidents, alerts, IoC rescan, DVM device inventory, PCAP
retrieval, and more.

> This build intentionally ships **all read/query tools plus the
> update/acknowledge operations, but not the add/delete/create tools**
> (device add/delete, bulk device add/delete, alert comment creation, and
> incident creation are omitted).

## Configuration

Configuration is read from a `config.yaml` file. By default the server looks
for it in this order:

1. The path in the `FAZ_CONFIG_FILE` environment variable (if set).
2. `config.yaml` in the current working directory.
3. `config.yaml` at the project root.

Start from the committed template and fill in your own values:

```bash
cp config.example.yaml config.yaml
```

`config.yaml` is gitignored (it holds secrets). Example:

```yaml
config:
  fortianalyzer:
    host: 172.18.7.15
    api_key: <your-api-token>
    verify_ssl: false
    log_level: info
    default_adom: root
    auth_token: <your-http-auth-token>
```

Optional keys: `username`, `password`, `ca_bundle`, `timeout`, `max_retries`,
`log_file`, `log_format`, `auth_token`. Any value can be overridden with an
environment variable (e.g. `FORTIANALYZER_HOST`, `FORTIANALYZER_API_TOKEN`,
`FORTIANALYZER_VERIFY_SSL`, `DEFAULT_ADOM`, `LOG_LEVEL`, `FAZ_AUTH_TOKEN`).

`auth_token` (or the `FAZ_AUTH_TOKEN` env var) protects the HTTP endpoint.
When it is not set, the server generates a random token at startup and prints
it (see [Authentication](#authentication)).

## Install

The recommended way to install is with [pipx](https://pipx.pypa.io/), which
installs the `mcp-fortianalyzer` command into an isolated environment:

```bash
# Install pipx itself if you don't have it yet
python -m pip install --user pipx
python -m pipx ensurepath

# Install this project (from a clone of the repository)
pipx install .

# or straight from GitHub
pipx install "git+https://github.com/ratnoub/mcp-fortianalyzer.git"
```

`pipx install .` builds the package and exposes the `mcp-fortianalyzer`
command on your `PATH`. To upgrade after pulling new changes, re-run
`pipx install --force .`.

<details>
<summary>Alternative: install with plain pip (e.g. for development)</summary>

```bash
# Development install (editable)
pip install -e ".[dev]"
```

</details>

## Run

**stdio** (for local MCP clients such as Claude Desktop):

```bash
mcp-fortianalyzer --transport stdio
```

**HTTP** (default — for containerised / remote deployment):

```bash
mcp-fortianalyzer
```

By default the server listens on **`0.0.0.0:5750`** and serves the MCP
endpoint at **`http://<IP>:5750/mcp`**.

### Command-line options

| Flag | Default | Description |
|------|---------|-------------|
| `--transport {stdio,http}` | auto-detect | Transport to use. When unset, a TTY or Docker environment runs HTTP, a piped stdin runs stdio. |
| `--host` | `0.0.0.0` | HTTP bind address. |
| `--port` | `5750` | HTTP bind port. |
| `--path` | `/mcp` | HTTP endpoint path. |
| `--token` | — | Auth token for HTTP mode (see [Authentication](#authentication)). |
| `--no-auth` | off | Disable auth-token enforcement in HTTP mode (not recommended). |
| `--daemon` | off | Run the HTTP server in the background and exit. |

### Running as a background daemon

```bash
mcp-fortianalyzer --daemon --token "my-secret-token"
```

This spawns a detached background process and returns immediately, printing the
PID, endpoint, log file, PID file, and (if a token was generated) the token:

```
FortiAnalyzer MCP server started in the background (daemon mode).
  PID:        47324
  Endpoint:   http://0.0.0.0:5750/mcp
  Log file:   /path/to/mcp-fortianalyzer.log
  PID file:   /path/to/mcp-fortianalyzer.pid
  Auth token: my-secret-token
  Stop with:  taskkill /PID 47324
```

The log and PID files are written to the current directory (override with the
`FAZ_DAEMON_DIR` env var). Stop the daemon with the printed command
(`taskkill /PID <pid>` on Windows, `kill <pid>` on Unix).

### Environment variables

`FAZ_TRANSPORT`, `FAZ_HTTP_HOST`, `FAZ_HTTP_PORT`, `FAZ_AUTH_TOKEN`,
`FAZ_CONFIG_FILE`, and `FAZ_DAEMON_DIR` are honoured as well.

## Authentication

HTTP mode is protected by a bearer token. The token is resolved in this order:

1. The `--token` command-line flag.
2. The `FAZ_AUTH_TOKEN` environment variable.
3. The `auth_token` key in `config.yaml`.
4. A randomly generated token (printed to the console at startup).

Clients send it as a standard `Authorization: Bearer <token>` header. For
example, with the FastMCP client:

```python
from fastmcp import Client

async with Client("http://<IP>:5750/mcp", auth="<token>") as c:
    tools = await c.list_tools()
```

Requests without a valid token are rejected with `401 Unauthorized`. Use
`--no-auth` to disable enforcement (not recommended for anything beyond local
testing).

## Registering with Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fortianalyzer": {
      "command": "mcp-fortianalyzer",
      "env": {
        "FAZ_CONFIG_FILE": "/absolute/path/to/config.yaml"
      }
    }
  }
}
```

## Tools

The server registers **71 tools** across the areas below. All are read/query
operations plus the update/acknowledge workflow steps; the add/delete/create
tools are intentionally omitted.

### Device & VDOM (4)

| Tool | Description |
|------|-------------|
| `get_device_info` | Get detailed information about a specific device.  Retrieves full device configuration and status. |
| `list_device_groups` | List all device groups in an ADOM.  Device groups allow organizing devices for policy and log management. |
| `list_device_vdoms` | List VDOMs for a specific device.  Virtual Domains (VDOMs) are independent virtual instances within a FortiGate device. |
| `search_devices` | Search for devices with filters. |

### Events & Alerts (8)

| Tool | Description |
|------|-------------|
| `acknowledge_alerts` | Acknowledge one or more alerts.  Marks alerts as acknowledged for SOC workflow tracking. |
| `get_alert_count` | Get count of alerts matching criteria. |
| `get_alert_details` | Get extra details for alerts.  Retrieves extended information about alerts including MITRE ATT&CK mappings and additional context. |
| `get_alert_handlers` | Get event alert-handler (detection-rule) definitions.  Reads the alert-handler configuration: each handler's name, id, and its rules (severity, filter, groupby, tags). This is the catalogue of detection rules the appliance runs — a read-only building block for the Wave-2 ``alert_rules`` skill. |
| `get_alert_incident_stats` | Get alert and incident statistics.  Retrieves aggregated statistics for SOC dashboards.  The breakdown returned is fixed -- ``timescale`` only chooses the bucket width. This tool used to take a ``stat_type`` ("severity", "severity-timescale", "status"); the endpoint has no such parameter on 7.6.6 or 8.0.0, so it never selected anything: live, a nonsense value and "severity" returned byte-identical responses while the tool echoed the requested type back as though it had applied. |
| `get_alert_logs` | Get log entries associated with alerts.  Retrieves the original log events that triggered the alerts. |
| `get_alerts` | Get alert events from FortiAnalyzer.  Retrieves security alerts generated by event handlers and correlation rules. |
| `unacknowledge_alerts` | Unacknowledge one or more alerts.  Removes acknowledgment status from alerts. |

### FortiView (3)

| Tool | Description |
|------|-------------|
| `fetch_fortiview` | Fetch FortiView query results by TID.  Retrieves results from a previously started FortiView query. |
| `get_fortiview_data` | Get FortiView data with automatic TID handling.  Convenience function that runs FortiView query and waits for results. Handles the two-step TID workflow automatically. |
| `run_fortiview` | Start a FortiView analytics query.  FortiView provides real-time visibility and analytics dashboards. This starts an async query and returns a TID for fetching results. |

### Incidents (5)

| Tool | Description |
|------|-------------|
| `get_incident` | Get a specific incident by ID.  Retrieves detailed information about a single incident. |
| `get_incident_count` | Get count of incidents matching criteria.  The time window is applied even though FortiAnalyzer does not document it on this endpoint — see ``get_incidents`` for the measurement. |
| `get_incident_stats` | Get incident statistics.  Retrieves aggregated statistics for SOC dashboards including counts by severity, status, and trends. |
| `get_incidents` | Get security incidents from FortiAnalyzer.  Retrieves incidents from the incident management module. Incidents can be created manually or automatically from alerts.  The time window IS applied, though FortiAnalyzer does not document ``time-range`` on this endpoint. Verified on 7.6.6: a window covering an incident's createtime returns it, windows in 2000 and 2099 return nothing, and omitting the window returns everything — the same pattern the documented ``/incident/stats`` gives. Each record also carries ``createtime`` and ``lastupdate``. |
| `update_incident` | Update an existing incident.  Modifies incident properties for SOC workflow management.  There is no assignment/ownership field on this API. This tool used to take an ``assignee``; no such field exists on 7.6.6 or 8.0.0, so it was dropped by the appliance while the call reported success. ``last_user`` records who last touched the record, which is the nearest real field -- it is an audit stamp, not an assignment. |

### IOC (Indicators of Compromise) (6)

| Tool | Description |
|------|-------------|
| `acknowledge_ioc_events` | Acknowledge IOC events.  Marks IOC detection events as acknowledged for SOC tracking.  Identify each event the way the appliance does -- by endpoint plus the timestamp it fired at. This tool used to take a list of ``ioc_ids`` with a ``user``; neither an event-id nor an acknowledging-user field exists in the IOC API on 7.6.6 or 8.0.0, so those never reached the appliance in a form it could act on. |
| `get_ioc_license_state` | Get IOC license state.  Checks the current IOC license status and capabilities. IOC detection requires an active FortiGuard IOC license. |
| `get_ioc_rescan_history` | Get IOC rescan history.  Retrieves history of previous IOC rescan operations. |
| `get_ioc_rescan_status` | Get IOC rescan status.  Check the progress of an IOC rescan operation. |
| `run_and_wait_ioc_rescan` | Run IOC rescan and wait for completion.  Convenience function that starts an IOC rescan and polls until completion. Handles the TID workflow automatically. |
| `run_ioc_rescan` | Start an IOC rescan.  Initiates a rescan of historical logs against current IOC database. Returns a TID for tracking the rescan progress. |

### Logs (10)

| Tool | Description |
|------|-------------|
| `cancel_log_search` | Release a pagination handle (and the FAZ task if still alive).  Call this when you are done paging a query_logs result to free the in-process handle. FortiAnalyzer reaps a completed logsearch task on its own, so the appliance-side cancel is best-effort; clearing the handle always succeeds. |
| `fetch_more_logs` | Fetch another page of a previous query_logs search using its handle.  Because a FortiAnalyzer logsearch tid is single-use, this re-runs the same query (same ADOM, logtype, filter, device, and time window) at the requested offset/limit using the search parameters recorded for `tid`. You normally only pass tid/offset/limit. If the handle is unknown to this server process (expired or from another process), the response is a structured error with error="tid_invalid_or_expired" and a recommendation to re-run query_logs. |
| `get_log_fields` | Get available log fields for a log type -- what you can filter on.  A live traffic response runs to roughly 200 definitions across two lists, which is more context than it is worth reading in full. Pass ``name_filter`` to narrow it to the fields you are actually after ("src", "port", "app"); the counts in the response say how much was dropped so a narrow answer is never mistaken for the whole catalogue. |
| `get_log_search_progress` | Report status of a query_logs pagination handle.  query_logs runs each search synchronously (it returns only after the page has completed), and a FortiAnalyzer logsearch task is single-use and reaped on completion. There is therefore no separately pollable in-progress task: a known handle is already complete. Use fetch_more_logs(tid=...) to retrieve further pages. |
| `get_log_stats` | Get log statistics for an ADOM.  Returns statistics about log storage, rates, and device logging status. |
| `get_logfiles_state` | Get log file state information.  Lists available log files on disk for a device/VDOM. |
| `search_archived_logs` | Search records inside an archived FortiAnalyzer log file. Use `get_logfiles_state` to discover filenames. |
| `get_archived_log_data` | Read a bounded byte range from an archived log file. |
| `get_pcap_file` | Get PCAP file associated with a log entry.  Some logs (like IPS) include associated packet captures. This retrieves the PCAP file data. |
| `query_logs` | Query logs from FortiAnalyzer log database.  This implements the two-step TID-based log search workflow: 1. Start search task (returns TID) 2. Poll for results until complete |

### PCAP (5)

| Tool | Description |
|------|-------------|
| `download_pcap_by_url` | Download PCAP file using a pcapurl from search results.  Use this when you already have the pcapurl from a previous search_ips_logs call. |
| `get_pcap_by_session` | Download PCAP file for a specific session ID.  Searches for an IPS log entry by session ID and downloads the associated PCAP file if available. |
| `list_available_pcaps` | List IPS events that have PCAP files available.  Quick way to see what PCAPs are available before downloading. Returns a summary of each event with session ID for targeted download. |
| `search_and_download_pcaps` | Search for IPS events and download all matching PCAPs.  Convenience function that combines search_ips_logs and PCAP download into a single operation. Useful for bulk forensic collection. |
| `search_ips_logs` | Search IPS/attack logs with advanced filtering.  Search FortiAnalyzer for IPS (Intrusion Prevention System) events with flexible filtering options. Returns log entries that can be used to download associated PCAP files.  This is the right entry point for IPS work -- it filters on CVE and PCAP availability, which query_logs(logtype="attack", filters=[...]) cannot. Note the returned `tid` is NOT a pagination handle (see Returns); raise `limit` instead of trying to page, and pass has_pcap=True when the goal is a PCAP download. |

### Reports (11)

| Tool | Description |
|------|-------------|
| `fetch_report` | Fetch report status and progress by TID.  Check the progress of a running report. |
| `get_report_data` | Download completed report data.  Retrieves the generated report content after completion. The report data is returned as base64-encoded content. |
| `get_report_history` | Get report history - list of generated reports.  Retrieves list of completed/generated reports. |
| `get_running_reports` | Get currently running reports.  Check the status of reports that are currently being generated. Use this after run_report() to monitor progress. |
| `list_report_schedules` | List report schedules, optionally scoped to one layout. Read-only; does not create a missing schedule. |
| `get_report_schedule_details` | Get a report schedule's configuration, including its period fields. Read-only. |
| `list_report_layouts` | List available report layouts in FortiAnalyzer.  IMPORTANT: Layouts are runnable reports. Templates are read-only blueprints. When a user asks to "run a report", you need to search layouts, not templates.  Each layout has a layout-id which is required to run reports. A schedule must exist for the layout before it can be run (created automatically). |
| `list_report_templates` | List available read-only report templates in FortiAnalyzer.  IMPORTANT: Templates are protected blueprints, not runnable reports. To run a report use list_report_layouts() + run_report() instead. Templates are typically cloned into custom layouts via the FortiAnalyzer GUI/CLI.  Returns templates served by the dedicated FAZ endpoint GET /report/adom/{adom}/template/list, which is distinct from the layout endpoint that list_report_layouts() uses. |
| `run_and_wait_report` | Run a report and wait for completion.  IMPORTANT: This runs a LAYOUT, not a template. Use list_report_layouts() to see available reports.  Convenience function that: 1. Looks up the layout-id by title 2. Ensures a schedule exists 3. Runs the report 4. Polls until completion or timeout |
| `run_report` | Run a report in FortiAnalyzer.  IMPORTANT: This runs a LAYOUT, not a template. Templates are read-only blueprints. Use list_report_layouts() to see available reports.  This function: 1. Looks up the layout-id by title (or uses directly if numeric) 2. Ensures a schedule exists for the layout (creates one if needed) 3. Runs the report and returns the TID for tracking  Reports run asynchronously. Use get_running_reports() to check progress and get_report_data() to download the completed report. |
| `save_report` | Download, extract, and save a completed report to disk.  FortiAnalyzer returns reports as base64-encoded ZIP files. This tool downloads the report, decodes it, extracts the contents, and saves the report file(s) to the specified directory. |

### SOAR (2)

| Tool | Description |
|------|-------------|
| `get_indicator_enrichment` | Get IOC reputation/enrichment for an indicator.  Returns the stored reputation for an IP, URL or domain: verdict (``enrichment-reputation`` = Good/Suspicious/Malicious/ NoReputationAvailable), ``enrichment-confidence`` (0-100), status and the indicator/enrichment UUIDs. With detail_level "extended", also attaches the raw ``enrichment-detail`` from the reputation source. Reads existing enrichment only — it does not trigger a new lookup. Requires SOAR licensed with a reputation source that has enriched the indicator. |
| `get_linked_indicators` | Get IOC indicators linked to an alert or an incident.  Returns the SOAR indicators (IP/URL/Domain) associated with a specific alert or incident — the entry point for enriching the indicators that a detection actually involved. Requires SOAR licensed on the FAZ. |

### System (11)

| Tool | Description |
|------|-------------|
| `get_adom` | Get detailed information about a specific ADOM. |
| `get_api_ratelimit` | Get the current API rate limiting configuration.  Returns the configured rate limits for API read and write operations. This feature is available in FortiAnalyzer 7.6.5 and later.  Rate limiting helps protect the FortiAnalyzer from API abuse by limiting the number of requests that can be made per second. |
| `get_device` | Get detailed information about a specific device. |
| `get_ha_status` | Get FortiAnalyzer High Availability (HA) status.  Returns HA cluster status including: - HA mode (standalone, cluster) - Cluster members and their status - Sync status - Primary/secondary role |
| `get_system_status` | Get FortiAnalyzer system status and version information.  Returns comprehensive system status including: - FortiAnalyzer version and build - System hostname - Serial number - Admin domain mode - Platform information - Uptime and load |
| `get_task` | Get detailed status of a specific task. |
| `list_adoms` | List all Administrative Domains (ADOMs) in FortiAnalyzer.  ADOMs are used to partition FortiAnalyzer into separate management domains, each with its own devices, logs, and configurations.  Pass `fields` unless you genuinely need the full object. The default is every field the appliance defines -- around 35 per ADOM, most of them empty placeholders (unused IPv6 DNS slots, blank descriptions, tab_status, logview_customize). fields=["name", "state"] answers "which ADOMs exist and are they enabled" for a fraction of the response. |
| `list_devices` | List all devices registered in an ADOM.  FortiAnalyzer collects logs from FortiGate and other Fortinet devices. This lists all devices configured to send logs to this ADOM.  Pass `fields` unless you genuinely need the full object. The default is roughly 60 fields per device, including credential keys returned as "***REDACTED***" placeholders and unused mgmt.__data zero-arrays. fields=["name", "ip", "os_ver", "platform_str"] covers most inventory questions; add "sn" for serial numbers, which is also what `device` filters on elsewhere in this server. |
| `list_tasks` | List all tasks in FortiAnalyzer.  Tasks represent background operations like report generation, log queries, device synchronization, and other long-running processes. |
| `update_api_ratelimit` | Update the API rate limiting configuration.  Configures rate limits for API read and write operations. This feature is available in FortiAnalyzer 7.6.5 and later. |
| `wait_for_task` | Wait for a task to complete.  Polls the task status until it completes or times out. |

### Traffic (1)

| Tool | Description |
|------|-------------|
| `analyze_policy_traffic` | Break down what traffic each firewall policy actually carried.  Replaces get_policy_traffic_profile, get_policy_port_analysis and get_policy_protocol_summary: the three differed only in which breakdowns they produced, which is now the sample_by parameter.  This is a *bounded sample*, not a census. It scans a fixed number of time slices per policy and stops at a row cap, so check `is_exact` before quoting any number. When it is False, `analysis_mode` is "bounded_sample" and `total_hits` is a floor, not a total.  Use query_logs(sample_by=[...]) instead when you want one aggregate set for one query; this tool fans out across up to MAX_POLICY_IDS policies under a shared query budget and reports each separately. |

### UEBA (5)

| Tool | Description |
|------|-------------|
| `get_endpoint_stats` | Get ADOM-wide UEBA endpoint (asset) count stats for a window.  Returns an aggregate count snapshot for the ADOM over the window: total, new, identified and unidentified endpoint counts. This is an estate-scale denominator, NOT a per-endpoint or time-series record. The FortiAnalyzer requires a time window, so one is always sent. Requires UEBA to be enabled/licensed on the FortiAnalyzer. |
| `get_endpoint_vulnerabilities` | Get CVE/vulnerability records for UEBA endpoints.  Returns the per-endpoint vulnerability list (CVE id, severity, type, description, references) as detected by FortiClient or FortiGate. Requires UEBA to be enabled/licensed on the FortiAnalyzer. |
| `get_endpoints` | Get UEBA endpoint (asset) records from FortiAnalyzer.  Resolves endpoint/asset profiles: name and IP (``epname``/``epip``), the detecting appliance, and the ``user`` association list. Requires UEBA to be enabled/licensed on the FortiAnalyzer. |
| `get_enduser_stats` | Get ADOM-wide UEBA end-user (identity) count stats for a window.  Returns an aggregate count object for the ADOM over the window: total and new end-user counts. This is an estate-scale denominator, NOT a per-user or time-series record. The FortiAnalyzer requires both a window and the requested stat items, so both are always sent. Requires UEBA to be enabled/licensed on the FortiAnalyzer. |
| `get_endusers` | Get UEBA end-user (identity) records from FortiAnalyzer.  Resolves user identity records keyed on ``euname``. With detail_level "extended", also returns ``email``. Requires UEBA to be enabled/licensed on the FAZ. |

## Development

```bash
pip install -e ".[dev]"
ruff check src
pytest
```