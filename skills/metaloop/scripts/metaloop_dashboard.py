#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import metaloop_kernel as kernel  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only MetaLoop dashboard.")
    parser.add_argument("--workspace", default=".", help="Workspace or root to observe.")
    parser.add_argument("--scope", choices=["node", "root"], default="node", help="Observe one node or a root containing node workspaces.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host. Keep localhost unless you understand the risk.")
    parser.add_argument("--port", type=int, default=8765, help="Bind port.")
    args = parser.parse_args(argv)

    workspace = Path(args.workspace).expanduser().resolve()
    server = ThreadingHTTPServer((args.host, args.port), _handler(workspace, args.scope))
    print(f"MetaLoop dashboard: http://{args.host}:{args.port}")
    print(f"workspace: {workspace}")
    print("read-only: no control, routing, activation, or mutation endpoints")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()
    return 0


def _handler(workspace: Path, scope: str) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path in {"/", "/index.html"}:
                self._send_html(_page(workspace, scope))
                return
            if self.path.startswith("/api/summary"):
                self._send_json(_summary(workspace, scope))
                return
            self.send_error(404, "Not Found")

        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write("dashboard: " + format % args + "\n")

        def _send_html(self, body: str) -> None:
            encoded = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _send_json(self, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return DashboardHandler


def _summary(workspace: Path, scope: str) -> dict[str, Any]:
    if scope == "root":
        return kernel._brief_root_summary(kernel._observe_root(workspace))
    return kernel._brief_node_summary(kernel._observe_node(workspace))


def _page(workspace: Path, scope: str) -> str:
    payload = _summary(workspace, scope)
    title = "MetaLoop Dashboard"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f7f7f4;
      --fg: #1f2328;
      --muted: #697077;
      --line: #d8d8d2;
      --panel: #ffffff;
      --accent: #0f766e;
      --warn: #9a3412;
      --bad: #b91c1c;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #111312;
        --fg: #eef1ef;
        --muted: #a8b0ac;
        --line: #303633;
        --panel: #191d1b;
        --accent: #5eead4;
        --warn: #fdba74;
        --bad: #fca5a5;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font: 14px/1.45 ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--fg);
    }}
    header {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 16px;
      padding: 18px 22px;
      border-bottom: 1px solid var(--line);
    }}
    h1 {{ margin: 0; font-size: 18px; letter-spacing: 0; }}
    main {{ padding: 18px 22px 28px; max-width: 1280px; margin: 0 auto; }}
    .meta {{ color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }}
    .grid {{ display: grid; grid-template-columns: repeat(6, minmax(120px, 1fr)); gap: 10px; margin: 14px 0 18px; }}
    .tile {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 10px;
      min-height: 72px;
    }}
    .label {{ color: var(--muted); font-size: 12px; margin-bottom: 4px; }}
    .value {{ font-weight: 650; overflow-wrap: anywhere; }}
    .wide {{ display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(260px, .65fr); gap: 14px; }}
    section {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 12px;
      margin-bottom: 14px;
    }}
    h2 {{ margin: 0 0 8px; font-size: 14px; }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      font: 12px/1.45 ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      color: var(--muted);
    }}
    .node {{
      border-top: 1px solid var(--line);
      padding: 10px 0;
    }}
    .node:first-child {{ border-top: 0; padding-top: 0; }}
    .status {{ color: var(--accent); }}
    .waiting:not(:empty) {{ color: var(--warn); }}
    .bad {{ color: var(--bad); }}
    @media (max-width: 900px) {{
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .wide {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>MetaLoop Dashboard</h1>
    <div class="meta">read-only · scope={html.escape(scope)} · refresh=2s</div>
  </header>
  <main>
    <div class="meta">workspace: {html.escape(str(workspace))}</div>
    <div id="app">{_render(payload)}</div>
  </main>
  <script>
    async function refresh() {{
      try {{
        const res = await fetch('/api/summary', {{cache: 'no-store'}});
        const data = await res.json();
        document.getElementById('app').innerHTML = render(data);
      }} catch (err) {{
        document.getElementById('app').innerHTML = '<section><h2>Refresh failed</h2><pre>' + escapeHtml(String(err)) + '</pre></section>';
      }}
    }}
    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, ch => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[ch]));
    }}
    function tile(label, value, cls='') {{
      return '<div class="tile"><div class="label">' + escapeHtml(label) + '</div><div class="value ' + cls + '">' + escapeHtml(value ?? '-') + '</div></div>';
    }}
    function nodeCard(node) {{
      return '<div class="node">' +
        '<div><strong>' + escapeHtml(node.node_id || '-') + '</strong> <span class="status">' + escapeHtml(node.status || '-') + '</span> <span class="waiting">' + escapeHtml(node.waiting_on || '') + '</span></div>' +
        '<div class="meta">' + escapeHtml(node.workspace || '') + '</div>' +
        '<div>Goal: ' + escapeHtml(node.goal || '-') + '</div>' +
        '<div>Plan: ' + escapeHtml(node.current_plan || '-') + '</div>' +
        '<div>Verification: ' + escapeHtml(node.verification_status || '-') + '</div>' +
        '<div>Next: ' + escapeHtml(node.next_action || '-') + '</div>' +
      '</div>';
    }}
    function render(data) {{
      if (data.schema === 'metaloop.root_brief') {{
        const nodes = (data.nodes || []).map(nodeCard).join('');
        return '<div class="grid">' +
          tile('Nodes', data.node_count) +
          tile('Blocked', data.blocked_count, data.blocked_count ? 'bad' : '') +
          tile('Outbox', data.outbox_count) +
          tile('Inbox', data.inbox_count) +
          tile('Schema', data.schema) +
          tile('Root', data.root) +
          '</div><section><h2>Nodes</h2>' + nodes + '</section><section><h2>Raw Summary</h2><pre>' + escapeHtml(JSON.stringify(data, null, 2)) + '</pre></section>';
      }}
      return '<div class="grid">' +
        tile('Status', data.status) +
        tile('Waiting On', data.waiting_on || '-') +
        tile('Verification', data.verification_status || '-') +
        tile('Decision', data.adaptive_decision || '-') +
        tile('Context', (data.context_state || '-') + ' / ' + (data.context_ready_count || 0)) +
        tile('Controls', (data.pending_controls || []).join(', ') || '-') +
        '</div><div class="wide"><section><h2>Current Work</h2>' +
        '<p><strong>Goal</strong><br>' + escapeHtml(data.goal || '-') + '</p>' +
        '<p><strong>Plan</strong><br>' + escapeHtml(data.current_plan || '-') + '</p>' +
        '<p><strong>Next Action</strong><br>' + escapeHtml(data.next_action || '-') + '</p>' +
        '</section><section><h2>Evidence State</h2>' +
        '<p><strong>Latest Event</strong><br>' + escapeHtml(data.latest_event || '-') + '</p>' +
        '<p><strong>Metric</strong></p><pre>' + escapeHtml(JSON.stringify(data.best_metric || null, null, 2)) + '</pre>' +
        '</section></div><section><h2>Raw Summary</h2><pre>' + escapeHtml(JSON.stringify(data, null, 2)) + '</pre></section>';
    }}
    setInterval(refresh, 2000);
  </script>
</body>
</html>
"""


def _render(payload: dict[str, Any]) -> str:
    escaped = html.escape(json.dumps(payload, indent=2, ensure_ascii=False))
    return f"<section><h2>Loading</h2><pre>{escaped}</pre></section>"


if __name__ == "__main__":
    raise SystemExit(main())
