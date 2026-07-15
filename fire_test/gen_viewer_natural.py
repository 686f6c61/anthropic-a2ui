"""Genera el viewer HTML final para la prueba natural."""

import json
from pathlib import Path

fire_dir = Path(__file__).parent
results = fire_dir / "results_natural"
output = fire_dir / "viewer.html"

summary = json.load(open(results / "summary.json"))

embedded = {}
for r in summary["results"]:
  if r.get("has_json"):
    ms = (
        r["model"]
        .replace("claude-", "")
        .replace("-20251001", "")
        .replace("-20250929", "")
    )
    p = results / f"{ms}__{r['id']}.json"
    if p.exists():
      embedded[f"{ms}__{r['id']}"] = json.load(open(p))

data_json = json.dumps({"s": summary, "e": embedded}, ensure_ascii=False)

TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>anthropic-a2ui - Fire test</title>
<link rel="icon" href="data:,">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200">
<style>
:root {
  --bg: #faf9f7;
  --fg: #3d3d3d;
  --muted: #8a8a8a;
  --border: #e8e6e3;
  --surface: #ffffff;
  --surface-2: #f4f2ef;
  --accent: #7c9885;
  --ok: #7c9885;
  --err: #c17b6e;
  --warn: #d4a574;
  --prompt-bg: #f4f2ef;
  --code-bg: #2d2d2d;
  --code-fg: #e0e0e0;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.6;
  font-size: 15px;
}
.a2ui-render-area, .a2ui-render-area * {
  color: #2d2d2d;
}
.a2ui-render-area {
  background: #ffffff;
  color: #2d2d2d;
}
header {
  padding: 28px 32px 20px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}
header h1 {
  font-size: 22px;
  font-weight: 700;
  color: var(--fg);
  letter-spacing: -0.3px;
}
header p {
  font-size: 13px;
  color: var(--muted);
  margin-top: 6px;
}
#stats {
  display: flex;
  gap: 24px;
  padding: 14px 32px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  color: var(--muted);
  flex-wrap: wrap;
}
#stats b {
  color: var(--fg);
  font-size: 16px;
  font-weight: 700;
}
#stats .ok-num { color: var(--ok); }
#filter {
  display: flex;
  gap: 8px;
  padding: 12px 32px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--border);
}
#filter button {
  padding: 7px 16px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--muted);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  border-radius: 20px;
  transition: all 0.2s;
}
#filter button:hover {
  border-color: var(--accent);
  color: var(--fg);
}
#filter button.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}
main {
  max-width: 920px;
  margin: 0 auto;
  padding: 32px 24px;
}
.case {
  margin-bottom: 28px;
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  background: var(--surface);
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.case-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 24px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
  gap: 8px;
}
.case-head h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--fg);
}
.case-head .case-meta {
  font-size: 12px;
  color: var(--muted);
}
.badge {
  font-size: 11px;
  padding: 4px 12px;
  border-radius: 20px;
  font-weight: 600;
  white-space: nowrap;
}
.badge.ok {
  background: var(--ok);
  color: #fff;
}
.badge.invalid {
  background: var(--err);
  color: #fff;
}
.badge.no-a2ui {
  background: var(--warn);
  color: #fff;
}
.case-body { padding: 0; }
.prompt-section {
  padding: 18px 24px;
  border-bottom: 1px solid var(--border);
  background: var(--prompt-bg);
}
.prompt-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--muted);
  margin-bottom: 8px;
}
.input-mode {
  display: inline-flex;
  margin-left: 8px;
  padding: 2px 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  color: var(--muted);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0;
  text-transform: none;
}
.prompt-text {
  font-size: 14px;
  color: var(--fg);
  line-height: 1.7;
  white-space: pre-wrap;
  font-style: italic;
}
.usage-section {
  padding: 12px 24px;
  border-bottom: 1px solid var(--border);
  font-size: 11px;
  color: var(--muted);
  line-height: 1.8;
}
.usage-section b {
  color: var(--fg);
  font-weight: 600;
}
.error-section {
  padding: 14px 24px;
  border-bottom: 1px solid var(--border);
  background: #faf0ee;
}
.error-text {
  font-size: 12px;
  color: var(--err);
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}
.render-section {
  padding: 28px 24px;
  background: #ffffff;
  color: #2d2d2d;
  border-bottom: 1px solid var(--border);
  min-height: 60px;
}
.render-error {
  font-style: italic;
  color: var(--muted);
  font-size: 13px;
}
.json-section {
  padding: 14px 24px;
  background: var(--surface);
}
.json-toggle {
  font-size: 12px;
  color: var(--accent);
  cursor: pointer;
  font-family: monospace;
  font-weight: 600;
}
.json-toggle:hover {
  text-decoration: underline;
}
.json-code {
  display: none;
  margin-top: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
  font-family: "SF Mono", Monaco, "Cascadia Code", monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
  background: var(--code-bg);
  color: var(--code-fg);
  border-radius: 8px;
}
.json-code.open {
  display: block;
}
</style>
</head>
<body>

<header>
  <h1>anthropic-a2ui</h1>
  <p>10 natural prompts x 3 models (Haiku 4.5, Opus 4.7, Opus 4.8) = 30 runs</p>
</header>

<div id="stats"></div>
<div id="filter"></div>
<main id="cases"></main>

<script>
window.__DATA__ = __DATA_JSON_PLACEHOLDER__;
</script>

<script type="module">
import { MessageProcessor } from 'https://cdn.jsdelivr.net/npm/@a2ui/web_core@0.10.3/v0_9/+esm';
import { ContextProvider } from 'https://cdn.jsdelivr.net/npm/@lit/context@1.1.6/+esm';
import { renderMarkdown } from 'https://cdn.jsdelivr.net/npm/@a2ui/markdown-it@0.1.0/+esm';
import { A2uiSurface, basicCatalog, Context } from 'https://cdn.jsdelivr.net/npm/@a2ui/lit@0.10.1/v0_9/+esm';

if (!customElements.get('a2ui-surface')) {
  customElements.define('a2ui-surface', A2uiSurface);
}

// The official Lit renderer turns Text variants into Markdown internally.
// Provide its sanitized renderer so heading variants become semantic HTML
// rather than exposing Markdown markers to the user.
new ContextProvider(document.body, {
  context: Context.markdown,
  initialValue: renderMarkdown,
});

const D = window.__DATA__;
let filterModel = 'all';

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

function modelShort(m) {
  return m.replace('claude-','').replace('-20251001','').replace('-20250929','');
}

function renderStats() {
  const s = D.s;
  const st = s.stats || {};
  const el = document.getElementById('stats');
  el.innerHTML =
    '<b class="ok-num">' + st.ok + '</b> valid &nbsp; ' +
    '<b>' + (st.invalid||0) + '</b> invalid &nbsp; ' +
    '<b>' + (st.no_a2ui||0) + '</b> no A2UI &nbsp; ' +
    '<b>' + (st.error||0) + '</b> errors &nbsp; ' +
    '<span style="color:var(--muted);font-size:12px">/ ' + s.total + ' total</span>';
}

function renderFilter() {
  const el = document.getElementById('filter');
  const models = ['all', 'haiku-4-5', 'opus-4-7', 'opus-4-8'];
  let html = '';
  for (const m of models) {
    const label = m === 'all' ? 'All models' : m;
    const cls = filterModel === m ? 'active' : '';
    html += '<button class="' + cls + '" data-m="' + m + '">' + esc(label) + '</button>';
  }
  el.innerHTML = html;
  el.querySelectorAll('button').forEach(function(btn) {
    btn.addEventListener('click', function() {
      filterModel = this.dataset.m;
      renderFilter();
      renderCases();
    });
  });
}

function renderCases() {
  const s = D.s;
  const e = D.e;
  const container = document.getElementById('cases');
  container.innerHTML = '';

  for (const r of s.results) {
    const ms = modelShort(r.model);
    if (filterModel !== 'all' && ms !== filterModel) continue;

    const key = ms + '__' + r.id;
    const a2j = e[key];
    const hasJson = a2j != null;
    const input = r.input || {mode: 'text', content: r.prompt || ''};
    const inputMode = input.mode === 'voice' ? 'Voz transcrita' : 'Texto escrito';
    const attemptMeta = r.attempts > 1 ? ' &middot; ' + r.attempts + ' intentos' : '';

    let usageHtml = '';
    if (r.usage) {
      const u = r.usage;
      usageHtml = '<div class="usage-section">' +
        '<b>Components:</b> ' + esc(u.components.join(', ')) + ' &nbsp; ' +
        '<b>Functions:</b> ' + esc(u.functions.join(', ') || '\\u2014') + ' &nbsp; ' +
        '<b>Messages:</b> ' + esc(u.messages.join(', ')) +
        '</div>';
    }

    const div = document.createElement('div');
    div.className = 'case';
    div.innerHTML =
      '<div class="case-head">' +
        '<div><h3>' + esc(r.description) + '</h3></div>' +
        '<div><span class="case-meta">' + esc(ms) + ' &middot; ' + r.elapsed_ms + 'ms' + attemptMeta + '</span> ' +
        '<span class="badge ' + r.status + '">' + r.status.toUpperCase() + '</span></div>' +
      '</div>' +
      '<div class="case-body">' +
        '<div class="prompt-section">' +
          '<div class="prompt-label">Entrada enviada a Claude' +
            '<span class="input-mode">' + esc(inputMode) + '</span></div>' +
          '<div class="prompt-text">' + esc(input.content) + '</div>' +
        '</div>' +
        usageHtml +
        (r.error ? '<div class="error-section"><div class="error-text">' + esc(r.error) + '</div></div>' : '') +
        '<div class="render-section a2ui-render-area"><div id="surf-' + key + '"></div></div>' +
        (hasJson
          ? '<div class="json-section"><div class="json-toggle" data-key="' + key + '">View JSON</div><pre class="json-code" id="json-' + key + '"></pre></div>'
          : '') +
      '</div>';

    container.appendChild(div);

    if (hasJson) {
      const jsonEl = div.querySelector('#json-' + key);
      if (jsonEl) jsonEl.textContent = JSON.stringify(a2j, null, 2);

      const toggle = div.querySelector('.json-toggle');
      if (toggle) {
        toggle.addEventListener('click', function() {
          const code = this.nextElementSibling;
          code.classList.toggle('open');
          this.textContent = code.classList.contains('open') ? 'Hide JSON' : 'View JSON';
        });
      }

      const surf = div.querySelector('#surf-' + key);
      try {
        const proc = new MessageProcessor([basicCatalog]);
        proc.onSurfaceCreated(function(sf) {
          const el = document.createElement('a2ui-surface');
          el.surface = sf;
          surf.innerHTML = '';
          surf.appendChild(el);
        });
        const msgs = Array.isArray(a2j) ? a2j : [a2j];
        proc.processMessages(msgs);
      } catch(err) {
        surf.innerHTML = '<div class="render-error">Error: ' + esc(err.message) + '</div>';
      }
    }
  }
}

renderStats();
renderFilter();
renderCases();
</script>
</body>
</html>"""

html = TEMPLATE.replace("__DATA_JSON_PLACEHOLDER__", data_json)
with open(output, "w", encoding="utf-8") as f:
  f.write(html)

print(f"Viewer: file://{output}")
print(f"Size: {output.stat().st_size // 1024} KB")
print(f"JSONs: {len(embedded)}")
