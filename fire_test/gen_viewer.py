"""Genera el viewer HTML final: limpio, con prompts, B/N, renderizado A2UI."""

import json
from pathlib import Path

fire_dir = Path(__file__).parent
results_ex = fire_dir / "results_exhaustive"
results_simple = fire_dir / "results"
output = fire_dir / "viewer.html"

summary_ex = json.load(open(results_ex / "summary.json"))
summary_simple = json.load(open(results_simple / "summary.json"))

embedded = {}
for r in summary_ex["results"]:
    if r.get("has_json"):
        ms = r["model"].replace("claude-", "").replace("-20251001", "").replace("-20250929", "")
        p = results_ex / f"{ms}__{r['id']}.json"
        if p.exists():
            embedded[f"{ms}__{r['id']}"] = json.load(open(p))
for r in summary_simple["results"]:
    if r.get("has_json"):
        p = results_simple / f"{r['id']}.json"
        if p.exists():
            embedded[f"sonnet45__{r['id']}"] = json.load(open(p))

data_json = json.dumps({"ex": summary_ex, "sm": summary_simple, "e": embedded}, ensure_ascii=False)

TEMPLATE = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>anthropic-a2ui - Prueba de fuego</title>
<style>
:root {
  --bg: #ffffff;
  --fg: #111111;
  --muted: #666666;
  --border: #cccccc;
  --border-strong: #000000;
  --prompt-bg: #f5f5f5;
  --error-bg: #f0f0f0;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--fg);
  line-height: 1.5;
  font-size: 15px;
}
header {
  border-bottom: 2px solid var(--border-strong);
  padding: 20px 32px;
}
header h1 { font-size: 22px; font-weight: 700; }
header p { font-size: 13px; color: var(--muted); margin-top: 4px; }
nav {
  display: flex;
  border-bottom: 1px solid var(--border);
}
nav button {
  padding: 12px 24px;
  border: none;
  border-right: 1px solid var(--border);
  background: var(--bg);
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  color: var(--muted);
}
nav button.active {
  background: var(--border-strong);
  color: var(--bg);
  font-weight: 600;
}
nav button:hover:not(.active) { background: #f0f0f0; color: var(--fg); }

#stats {
  display: flex;
  gap: 16px;
  padding: 12px 32px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  color: var(--muted);
  flex-wrap: wrap;
}
#stats b { color: var(--fg); }

#coverage {
  padding: 12px 32px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}
.cov-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.cov-label { width: 110px; font-weight: 600; }
.cov-bar { flex: 1; max-width: 300px; height: 14px; border: 1px solid var(--border); }
.cov-fill { height: 100%; background: var(--border-strong); }
.cov-fill.partial { background: #999; }
.cov-text { font-size: 12px; color: var(--muted); }
.cov-missing { font-size: 11px; color: var(--fg); }

main { max-width: 960px; margin: 0 auto; padding: 32px 24px; }

.case {
  margin-bottom: 40px;
  border: 1px solid var(--border);
}
.case-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
  gap: 8px;
}
.case-head h3 { font-size: 16px; font-weight: 600; }
.case-head .case-id { font-size: 12px; color: var(--muted); font-family: monospace; margin-right: 8px; }
.case-head .case-model { font-size: 12px; color: var(--muted); }
.badge {
  font-size: 11px;
  padding: 3px 10px;
  border: 1px solid var(--border-strong);
  font-weight: 600;
  white-space: nowrap;
}
.badge.ok { background: var(--border-strong); color: var(--bg); }
.badge.invalid { background: var(--bg); }
.badge.no-a2ui { background: #ddd; border-color: #999; }

.case-body { padding: 20px; }

.prompt-box {
  background: var(--prompt-bg);
  border-left: 4px solid var(--border-strong);
  padding: 14px 18px;
  margin-bottom: 16px;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  font-family: inherit;
}
.prompt-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--muted);
  margin-bottom: 6px;
  display: block;
}

.meta-box {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 16px;
  line-height: 1.7;
}
.meta-box b { color: var(--fg); }

.error-box {
  border: 2px solid var(--border-strong);
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 12px;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-word;
}

.render-box {
  border: 1px solid var(--border);
  padding: 24px;
  min-height: 60px;
  background: var(--bg);
}
.render-error { font-style: italic; color: var(--muted); font-size: 13px; }

.json-toggle {
  display: inline-block;
  margin-top: 12px;
  font-size: 12px;
  color: var(--muted);
  cursor: pointer;
  text-decoration: underline;
  font-family: monospace;
}
.json-toggle:hover { color: var(--fg); }
.json-code {
  display: none;
  margin-top: 12px;
  border: 1px solid var(--border);
  padding: 16px;
  font-family: "SF Mono", Monaco, "Cascadia Code", monospace;
  font-size: 11px;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 500px;
  overflow-y: auto;
  background: #fafafa;
}
.json-code.open { display: block; }
</style>
</head>
<body>

<header>
  <h1>anthropic-a2ui &mdash; Prueba de fuego</h1>
  <p>Claude genera A2UI &middot; validacion con anthropic-a2ui &middot; renderizado con @a2ui/lit</p>
</header>

<nav>
  <button class="active" data-view="ex">Exhaustivo &mdash; 3 modelos</button>
  <button data-view="sm">Simple &mdash; Sonnet 4.5</button>
</nav>

<div id="stats"></div>
<div id="coverage"></div>

<main id="cases"></main>

<script>
window.__DATA__ = __DATA_JSON_PLACEHOLDER__;
</script>

<script type="module">
import { MessageProcessor } from 'https://cdn.jsdelivr.net/npm/@a2ui/web_core@0.10.2/v0_9/+esm';
import { A2uiSurface, basicCatalog } from 'https://cdn.jsdelivr.net/npm/@a2ui/lit@0.10.1/v0_9/+esm';

if (!customElements.get('a2ui-surface')) {
  customElements.define('a2ui-surface', A2uiSurface);
}

const D = window.__DATA__;
let view = 'ex';

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s || '';
  return d.innerHTML;
}

function renderStats() {
  const s = view === 'ex' ? D.ex : D.sm;
  const st = s.stats || {};
  const el = document.getElementById('stats');
  el.innerHTML =
    '<b>' + s.total + '</b> casos &nbsp; ' +
    '<b style="color:#000">' + (st.ok||0) + '</b> validos &nbsp; ' +
    '<b>' + (st.invalid||0) + '</b> invalidos &nbsp; ' +
    '<b>' + (st.no_a2ui||0) + '</b> sin A2UI &nbsp; ' +
    '<b>' + (st.error||0) + '</b> errores';
}

function renderCoverage() {
  const el = document.getElementById('coverage');
  if (view !== 'ex') { el.innerHTML = ''; return; }
  const c = D.ex.coverage;
  const rows = [
    { l: 'Componentes', c: c.components },
    { l: 'Funciones', c: c.functions },
    { l: 'Mensajes', c: c.messages },
    { l: 'Propiedades', c: c.properties },
  ];
  let html = '';
  for (const r of rows) {
    const pct = Math.round(r.c.covered.length * 100 / r.c.total);
    const cls = pct < 100 ? 'partial' : '';
    const missing = r.c.missing.length
      ? ' <span class="cov-missing">Faltan: ' + esc(r.c.missing.join(', ')) + '</span>'
      : '';
    html += '<div class="cov-row">' +
      '<span class="cov-label">' + r.l + '</span>' +
      '<div class="cov-bar"><div class="cov-fill ' + cls + '" style="width:' + pct + '%"></div></div>' +
      '<span class="cov-text">' + r.c.covered.length + '/' + r.c.total + ' (' + pct + '%)</span>' +
      missing + '</div>';
  }
  el.innerHTML = html;
}

function renderCases() {
  const s = view === 'ex' ? D.ex : D.sm;
  const e = D.e;
  const container = document.getElementById('cases');
  container.innerHTML = '';

  for (const r of s.results) {
    const key = view === 'ex'
      ? r.model.replace('claude-','').replace('-20251001','').replace('-20250929','') + '__' + r.id
      : 'sonnet45__' + r.id;
    const a2j = e[key];
    const hasJson = a2j != null;

    // Modelo corto
    const modelShort = view === 'ex'
      ? r.model.replace('claude-','').replace('-20251001','').replace('-20250929','')
      : 'sonnet-4-5';

    const div = document.createElement('div');
    div.className = 'case';
    div.innerHTML =
      '<div class="case-head">' +
        '<div><span class="case-id">' + esc(r.id) + '</span><h3 style="display:inline">' + esc(r.description) + '</h3></div>' +
        '<div><span class="case-model">' + esc(modelShort) + ' &middot; ' + r.elapsed_ms + 'ms</span> <span class="badge ' + r.status + '">' + r.status.toUpperCase() + '</span></div>' +
      '</div>' +
      '<div class="case-body">' +
        // Prompt
        '<div class="prompt-box">' +
          '<span class="prompt-label">Prompt enviado a Claude</span>' +
          esc(r.prompt || '(sin prompt)') +
        '</div>' +
        // Meta (componentes/funciones/mensajes usados)
        (view === 'ex' && r.components_used
          ? '<div class="meta-box">' +
            '<b>Componentes:</b> ' + esc(r.components_used.join(', ')) + '<br>' +
            '<b>Funciones:</b> ' + esc(r.functions_used.join(', ') || '\u2014') + '<br>' +
            '<b>Mensajes:</b> ' + esc(r.messages_used.join(', ')) + ' &nbsp; ' +
            '<b>Props:</b> ' + r.properties_used.length +
            '</div>'
          : '') +
        // Error si hay
        (r.error ? '<div class="error-box">' + esc(r.error) + '</div>' : '') +
        // Render A2UI
        '<div class="render-box"><div id="surf-' + key + '"></div></div>' +
        // Toggle JSON
        (hasJson
          ? '<div class="json-toggle" data-key="' + key + '">Ver JSON A2UI</div>' +
            '<pre class="json-code" id="json-' + key + '"></pre>'
          : '') +
      '</div>';

    container.appendChild(div);

    // Rellenar JSON
    if (hasJson) {
      const jsonEl = div.querySelector('#json-' + key);
      if (jsonEl) jsonEl.textContent = JSON.stringify(a2j, null, 2);

      const toggle = div.querySelector('.json-toggle');
      if (toggle) {
        toggle.addEventListener('click', function() {
          const code = this.nextElementSibling;
          code.classList.toggle('open');
          this.textContent = code.classList.contains('open') ? 'Ocultar JSON' : 'Ver JSON A2UI';
        });
      }

      // Renderizar con A2UI (siempre, incluso invalidos)
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
        surf.innerHTML = '<div class="render-error">Error de renderizado: ' + esc(err.message) + '</div>';
      }
    }
  }
}

function render() {
  renderStats();
  renderCoverage();
  renderCases();
}

// Tabs
document.querySelectorAll('nav button').forEach(function(btn) {
  btn.addEventListener('click', function() {
    document.querySelectorAll('nav button').forEach(function(b) { b.classList.remove('active'); });
    this.classList.add('active');
    view = this.dataset.view;
    render();
  });
});

render();
</script>
</body>
</html>"""

html = TEMPLATE.replace("__DATA_JSON_PLACEHOLDER__", data_json)
with open(output, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Viewer: file://{output}")
print(f"Tamano: {output.stat().st_size // 1024} KB")
print(f"JSONs: {len(embedded)}")