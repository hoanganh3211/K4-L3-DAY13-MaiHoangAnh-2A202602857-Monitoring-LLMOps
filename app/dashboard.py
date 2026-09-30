"""Six-panel dashboard generated only from structured runtime logs."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from statistics import mean
import json

import yaml

from .metrics import percentile
from .logging_config import LOG_PATH

ROOT = Path(__file__).resolve().parents[1]


def read_window(now=None):
    now = now or datetime.now(timezone.utc)
    rows = []
    malformed = 0
    if LOG_PATH.exists():
        for line in LOG_PATH.read_text(encoding='utf-8').splitlines():
            try:
                row = json.loads(line)
                stamp = datetime.fromisoformat(row['ts'].replace('Z', '+00:00'))
                if now - timedelta(minutes=60) <= stamp <= now:
                    rows.append(row)
            except (ValueError, KeyError, TypeError):
                malformed += 1
    return rows, malformed, now


def aggregate(rows):
    received = [r for r in rows if r['event'] == 'request_received']
    sent = [r for r in rows if r['event'] == 'response_sent']
    failed = [r for r in rows if r['event'] == 'request_failed']
    tools = [r for r in rows if r.get('tool_name') == 'retrieval' and isinstance(r.get('tool_success'), bool)]
    cost = defaultdict(float)
    for r in sent:
        cost[r['ts'][:16]] += r['cost_usd']
    return {
        'latency': {**{f'P{p}': percentile([r['latency_ms'] for r in sent], p) if sent else None for p in (50, 95, 99)},
                    'TTFT P95': percentile([r['ttft_ms'] for r in sent], 95) if sent else None},
        'traffic': dict(sorted(Counter(r['ts'][:16] for r in received).items())),
        'errors': {'Error rate': len(failed) / len(received) * 100 if received else None,
                   'Retrieval success': sum(r['tool_success'] for r in tools) / len(tools) * 100 if tools else None},
        'cost': dict(sorted(cost.items())),
        'tokens': {k: sum(r[k] for r in sent) for k in ('tokens_in', 'tokens_out')},
        'quality': {'Mean': mean(r['quality_score'] for r in sent) if sent else None},
        'count': len(received), 'total_cost': sum(cost.values()),
        'error_breakdown': dict(Counter(r['error_type'] for r in failed)),
    }


def chart(values, threshold=None):
    pairs = list(values.items())
    if not pairs or all(v is None for _, v in pairs):
        return '<p class="empty">No data in this time window</p>'
    maximum = max([float(v or 0) for _, v in pairs] + [float(threshold or 0), 1]) * 1.15
    height = max(100, len(pairs) * 30 + 20)
    svg = [f'<svg viewBox="0 0 560 {height}" role="img" aria-label="Observed values and threshold">']
    for i, (label, value) in enumerate(pairs):
        y = 12 + i * 30
        svg.append(f'<text x="0" y="{y+14}">{escape(label)}</text>')
        if value is not None:
            width = float(value) / maximum * 280
            svg.append(f'<rect x="180" y="{y}" width="{width}" height="18" rx="3" fill="#38bdf8"/>')
        label_value = 'No data' if value is None else f'{value:.6g}'
        svg.append(f'<text x="470" y="{y+14}">{label_value}</text>')
    if threshold is not None:
        x = 180 + threshold / maximum * 280
        svg.append(f'<line x1="{x}" x2="{x}" y1="0" y2="{height}" stroke="#fb7185" stroke-dasharray="5 4"/>')
    return ''.join(svg) + '</svg>'


def render_dashboard(now=None):
    rows, malformed, now = read_window(now)
    data = aggregate(rows)
    config = yaml.safe_load((ROOT / 'config/dashboard.yaml').read_text(encoding='utf-8-sig'))['dashboard']
    panels = []
    for p in config['panels']:
        key = p['id']
        t = p['threshold']
        extra = ''
        if key == 'traffic':
            extra = f"Total requests: {data['count']}"
        if key == 'cost':
            extra = f"Window total: ${data['total_cost']:.6f}; threshold applies to total, not minute buckets."
        if key == 'errors':
            extra = f"Retrieval success guardrail ≥ 90%. Error breakdown: {escape(json.dumps(data['error_breakdown']))}"
        panels.append(f'<section><h2>{escape(p["title"])}</h2><p>{escape(p["unit"])} · {escape(t["aggregation"])} {escape(t["operator"])} {t["value"]}</p>'
                      + chart(data[key], None if key == 'cost' else t['value'])
                      + (chart({'Window total': data['total_cost']}, t['value']) if key == 'cost' else '')
                      + f'<small>{extra}</small></section>')
    start = now - timedelta(minutes=60)
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta http-equiv="refresh" content="30">
<title>Monitoring & LLMOps · Mai Hoàng Anh</title><style>
body{{background:#0b1220;color:#e2e8f0;font:15px system-ui;margin:28px}}h1{{margin-bottom:6px}}h2{{font-size:18px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}}section{{background:#162238;border:1px solid #334155;border-radius:12px;padding:20px}}
svg{{width:100%}}svg text{{fill:#e2e8f0;font-size:12px}}p,small{{color:#a9bdd4}}.empty{{padding:30px}}@media(max-width:850px){{.grid{{grid-template-columns:1fr}}}}
</style><h1>Monitoring & LLMOps</h1><p>Mai Hoàng Anh · 2A202602857 · Source: data/logs.jsonl</p>
<p>UTC {start.isoformat(timespec='seconds')} → {now.isoformat(timespec='seconds')} · 60 minutes · refresh 30s · skipped malformed lines: {malformed}</p>
<div class="grid">{''.join(panels)}</div><p>Dashed line = panel threshold. Quality is a heuristic, not a human evaluation. No data does not mean healthy.</p></html>'''
