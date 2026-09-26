"""Builds dashboard.html from state/ — open locally anytime to see the experiment."""
import json, datetime as dt
from pathlib import Path

STATE = Path(__file__).parent / "state"

def rows():
    p = STATE / "log.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []

def build():
    ev = rows()
    published = [e for e in ev if e["event"] == "published"]
    topics = [e for e in ev if e["event"] == "topic_selected"]
    lib = sorted(Path(__file__).parent.glob("content_library/*.md"))
    halted = (STATE / "HALTED").exists()
    metrics = []
    mp = STATE / "metrics.jsonl"
    if mp.exists():
        metrics = [json.loads(l) for l in mp.read_text().splitlines() if l.strip()]

    bar = "".join(
        f'<div class="bar" style="height:{min(100, 10 + len([x for x in published if x["ts"][:10]==d]) * 30)}px" title="{d}"></div>'
        for d in sorted({e["ts"][:10] for e in ev})[-30:])

    html = f"""<!doctype html><html><head><meta charset="utf-8"><title>AUTONOMOUS-30</title>
<style>
body{{font-family:system-ui;max-width:820px;margin:40px auto;padding:0 16px;background:#0d1117;color:#e6edf3}}
h1{{font-size:22px}} .stat{{display:inline-block;background:#161b22;border:1px solid #30363d;
border-radius:8px;padding:14px 20px;margin:6px}} .stat b{{font-size:26px;display:block}}
.bars{{display:flex;gap:3px;align-items:flex-end;height:110px;margin:18px 0}}
.bar{{width:14px;background:#2f81f7;border-radius:2px 2px 0 0}}
.warn{{color:#f85149}} .ok{{color:#3fb950}} table{{border-collapse:collapse;width:100%;font-size:13px}}
td,th{{border:1px solid #30363d;padding:6px 8px;text-align:left}}</style></head><body>
<h1>AUTONOMOUS-30 — Attention Asset Experiment</h1>
<p>Status: <b class="{'warn' if halted else 'ok'}">{'HALTED — human intervention required' if halted else 'RUNNING unattended'}</b></p>
<div class="stat"><b>{len(published)}</b>posts published</div>
<div class="stat"><b>{len(topics)}</b>topics selected</div>
<div class="stat"><b>{len(lib)}</b>long-form assets</div>
<div class="stat"><b>{(metrics[-1].get('followers') if metrics else '—')}</b>current followers</div>
<h3>Publishing activity (last 30 days)</h3><div class="bars">{bar}</div>
<h3>Recent topics</h3><table><tr><th>Date</th><th>Topic</th></tr>
{"".join(f"<tr><td>{t['ts'][:10]}</td><td>{t.get('topic','')[:90]}</td></tr>" for t in topics[-12:])}
</table><p style="color:#8b949e;font-size:12px">Generated {dt.datetime.utcnow():%Y-%m-%d %H:%M} UTC</p>
</body></html>"""
    Path(__file__).parent.joinpath("dashboard.html").write_text(html)
    print("dashboard.html written")

if __name__ == "__main__":
    build()
