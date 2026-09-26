"""
AUTONOMOUS-30 agent core.
Runs the full unattended loop: scout -> score -> draft -> critic -> queue
-> publish -> analyze -> adapt. Works on GitHub Actions cron or local cron.
$0 stack: free LLM API + Telegram Bot API + optional X API. State in state/*.json.
"""
import json, os, re, sys, time, datetime as dt
from pathlib import Path

import requests

ROOT = Path(__file__).parent
STATE = ROOT / "state"; STATE.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))

try:
    import yaml
    CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
except ImportError:
    raise SystemExit("pyyaml required: pip install pyyaml")
import prompts as P

# ---------------------------------------------------------------- utilities
def log(event: str, **kv):
    rec = {"ts": dt.datetime.utcnow().isoformat() + "Z", "event": event, **kv}
    with open(STATE / "log.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(rec)

def load(name, default):
    p = STATE / name
    return json.loads(p.read_text()) if p.exists() else default

def save(name, obj):
    (STATE / name).write_text(json.dumps(obj, indent=2))

def jload(text):
    """Extract strict JSON from an LLM reply, tolerating stray fences."""
    m = re.search(r"(\{.*\}|\[.*\])", text, re.S)
    return json.loads(m.group(1)) if m else None

# ---------------------------------------------------------------- llm layer
def llm(user, system=P.IDENTITY, temperature=0.7):
    base = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    key = os.environ["LLM_API_KEY"]
    model = os.environ.get("LLM_MODEL", "llama-3.3-70b-versatile")
    r = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={"model": model, "temperature": temperature,
              "messages": [{"role": "system", "content": system},
                           {"role": "user", "content": user}]},
        timeout=90)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]

def guarded_llm(user, **kw):
    """LLM call with the kill-switch: halts after N consecutive failures."""
    fails = load("fail_counter.json", {"n": 0})
    try:
        out = llm(user, **kw)
        save("fail_counter.json", {"n": 0})
        return out
    except Exception as e:
        fails["n"] += 1
        save("fail_counter.json", fails)
        log("llm_error", consecutive=fails["n"], error=str(e))
        if fails["n"] >= CFG["kill_conditions"]["consecutive_api_errors"]:
            save("HALTED", {"reason": "consecutive_api_errors", "at": dt.datetime.utcnow().isoformat()})
            raise SystemExit("HALTED: consecutive API errors")
        raise

# ---------------------------------------------------------------- scout
def fetch_trends():
    items, headers = [], {"User-Agent": "autonomous30/1.0 (experiment)"}
    for sub in CFG["sources"]["subreddits"]:
        try:
            r = requests.get(f"https://www.reddit.com/r/{sub}/hot.json?limit=12",
                             headers=headers, timeout=20)
            for p in r.json().get("data", {}).get("children", []):
                d = p["data"]
                if d.get("score", 0) < 20 or d.get("is_self") is False and not d.get("selftext"):
                    continue
                items.append({"topic": d["title"], "source": f"r/{sub}",
                              "heat": d.get("score", 0),
                              "snip": (d.get("selftext") or "")[:400]})
        except Exception as e:
            log("scout_error", source=sub, error=str(e))
    # RSS feeds (light parsing, no external deps)
    import xml.etree.ElementTree as ET
    for feed in CFG["sources"]["rss"]:
        try:
            r = requests.get(feed, headers=headers, timeout=20)
            for it in ET.fromstring(r.content).iter("item"):
                items.append({"topic": (it.findtext("title") or "").strip(),
                              "source": feed.split("/")[2], "heat": 0,
                              "snip": (it.findtext("description") or "")[:400]})
        except Exception as e:
            log("scout_error", source=feed, error=str(e))
    return items

def score_trends(items):
    if not items:
        return None
    strat = load("strategy.json", {})
    dd = strat.get("double_down_on", [])
    blob = "\n".join(f"- {i['topic']} (heat {i['heat']}, r/{i['source']})" for i in items[:40])
    if dd:
        blob += f"\n\nSTRATEGY NOTE: yesterday the analyst said to double down on: {', '.join(dd)}"
    raw = guarded_llm(P.TREND_SCORER.format(topics=blob))
    data = jload(raw)
    if isinstance(data, dict) and data.get("skip"):
        log("scout_skip", reason="all topics scored below 5")
        return None
    if not data:
        return items[0]
    best = max(data, key=lambda x: x.get("score", 0)) if isinstance(data, list) else data
    return best

# ---------------------------------------------------------------- draft/critic
def draft(topic):
    return guarded_llm(P.WRITER.format(**topic), temperature=0.8)

def critique_loop(content_json):
    threshold = CFG["quality"]["critic_threshold"]
    for attempt in range(CFG["quality"]["max_rewrites"] + 1):
        verdict = jload(guarded_llm(P.CRITIC.format(content=content_json[:6000])))
        score = (verdict or {}).get("score", 0)
        log("critic_pass", attempt=attempt, score=score)
        if score >= threshold or attempt == CFG["quality"]["max_rewrites"]:
            return content_json, score
        problems = "; ".join((verdict or {}).get("problems", []))
        content_json = guarded_llm(P.REWRITER.format(problems=problems, content=content_json[:6000]))
    return content_json, score

# ---------------------------------------------------------------- publishers
class Telegram:
    def __init__(self):
        self.tok = os.environ["TELEGRAM_BOT_TOKEN"]
        self.chat = os.environ["TELEGRAM_CHAT_ID"]
        self.fails = load("tg_fails.json", {"n": 0})

    def post(self, text):
        r = requests.post(f"https://api.telegram.org/bot{self.tok}/sendMessage",
                          json={"chat_id": self.chat, "text": text[:4000],
                                "parse_mode": "HTML", "disable_web_page_preview": False},
                          timeout=30)
        if not r.ok:
            self.fails["n"] += 1; save("tg_fails.json", self.fails)
            log("publish_error", platform="telegram", error=r.text[:200])
            if self.fails["n"] >= CFG["kill_conditions"]["telegram_post_failures"]:
                save("HALTED", {"reason": "telegram_failures"})
                raise SystemExit("HALTED: telegram failures")
            return False
        save("tg_fails.json", {"n": 0})
        return True

class XPoster:
    """Optional. Falls back silently if keys are absent."""
    def __init__(self):
        self.keys = [os.environ.get(k) for k in
                     ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_SECRET")]
        self.ok = all(self.keys)

    def post(self, text):
        if not self.ok:
            return False
        try:
            import tweepy  # pip install tweepy (optional)
            client = tweepy.Client(
                consumer_key=self.keys[0], consumer_secret=self.keys[1],
                access_token=self.keys[2], access_token_secret=self.keys[3])
            for chunk in [text[i:i + 270] for i in range(0, min(len(text), 540), 270)]:
                client.create_tweet(text=chunk)
            return True
        except Exception as e:
            log("publish_error", platform="x", error=str(e)[:200])
            return False

# ---------------------------------------------------------------- analyst
def analyze():
    metrics = load("metrics.jsonl", [])
    last7 = [m for m in metrics
             if dt.datetime.fromisoformat(m["ts"].replace("Z", "")) >
                dt.datetime.utcnow() - dt.timedelta(days=7)]
    out = guarded_llm(P.ANALYST.format(metrics=json.dumps(last7, indent=1)[:6000]))
    verdict = jload(out) or {}
    save("strategy.json", verdict)
    save("metrics_summary.json", {"last7": last7, "strategy": verdict,
                                  "computed": dt.datetime.utcnow().isoformat() + "Z"})
    log("analyst_update", strategy=verdict.get("explanation", ""))

def record_metrics(views=None, followers=None):
    entry = {"ts": dt.datetime.utcnow().isoformat() + "Z"}
    try:  # Telegram channel stats, free, no extra permissions
        tok = os.environ["TELEGRAM_BOT_TOKEN"]
        chat = os.environ["TELEGRAM_CHAT_ID"]
        r = requests.post(f"https://api.telegram.org/bot{tok}/getChat",
                          json={"chat_id": chat}, timeout=20)
        if r.ok:
            entry["followers"] = r.json()["result"].get("member_count")
    except Exception:
        pass
    metrics = load("metrics.jsonl", [])
    metrics.append(entry)
    save("metrics.jsonl", metrics)

# ---------------------------------------------------------------- main loop
def run(mode):
    if (STATE / "HALTED").exists():
        raise SystemExit("Agent is HALTED — see state/HALTED")

    if mode == "produce":                      # 13:30 UTC
        items = fetch_trends()
        topic = score_trends(items)
        if not topic:
            return
        log("topic_selected", **{k: topic.get(k) for k in ("topic", "angle", "score")})
        content = draft(topic)
        final, score = critique_loop(content)
        data = jload(final)
        if not data:
            data = {"posts": [final[:1000]], "longform": ""}
        queue = load("queue.json", [])
        queue.append({"due": str(dt.date.today()), "topic": topic.get("topic"),
                      "posts": data.get("posts", []),
                      "longform": data.get("longform", ""), "critic_score": score})
        save("queue.json", queue)

    elif mode == "publish":                    # 14:00 / 19:00 UTC
        tg, x = Telegram(), XPoster()
        today, lib = str(dt.date.today()), STATE.parent / "content_library"
        lib.mkdir(exist_ok=True)
        for q in [q for q in load("queue.json", []) if q["due"] <= today]:
            for post in q["posts"][:CFG["cadence"]["posts_per_day"]]:
                tg.post(post) and log("published", platform="telegram",
                                      topic=q["topic"], preview=post[:80])
                if x.post(post):
                    log("published", platform="x", topic=q["topic"])
            if q["longform"]:
                fname = re.sub(r"[^a-z0-9]+", "-", q["topic"].lower())[:50]
                (lib / f"{today}-{fname}.md").write_text(q["longform"])
                log("archived", file=f"{today}-{fname}.md")
            q["due"] = "done"
        save("queue.json", load("queue.json", []))

    elif mode == "analyze":                    # 22:00 UTC
        record_metrics()
        try:
            analyze()
        except Exception as e:
            log("analyst_error", error=str(e))

if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "produce")
