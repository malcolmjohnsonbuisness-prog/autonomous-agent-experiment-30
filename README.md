# AUTONOMOUS-30 — Attention Asset Experiment

**Hypothesis:** An unattended AI agent, given $0 and 30 days, can build a monetizable
attention asset (audience + content library + distribution) that a human can convert
to revenue on Day 30 in a single step.

**The one human step:** ~90 minutes of Day-0 setup (account creation + API keys).
After that: zero human interaction for 30 days. A 5-minute optional daily digest
is sent to you — reading it is not required for the system to run.

---

## Experiment Charter

| Parameter | Value |
|---|---|
| Capital | $0 (free tiers only) |
| Human interaction | Day 0 only (~90 min) |
| Duration | 30 days |
| Distribution | Telegram channel (free, no KYC) + X account |
| Production | GitHub Actions cron (free) |
| Brain | Groq or Google AI Studio free API (OpenAI-compatible) |

## Success Metrics (measured Day 30)

1. **Attention:** cumulative impressions/views on distributed content
2. **Audience:** followers/subscribers across channels
3. **Asset value:** content library size + engagement rate → what the asset could
   sell for or earn in month two (the human job to convert)

## The Daily Loop (runs unattended)

```
13:30 UTC  SCOUT    Pull hot topics from configured subreddits + RSS feeds
13:35 UTC  SCORE    LLM ranks topics by virality/monetization fit
13:40 UTC  DRAFT    Write 3 posts + 1 long-form piece on the top topic
13:50 UTC  CRITIC   Self-review pass; rewrites anything scoring < 8/10
14:00 UTC  PUBLISH  Fire scheduled content to Telegram + X
22:00 UTC  ANALYST  Pull engagement metrics, log them, adapt tomorrow strategy
```

State persists in `state/` as JSON — the agent reads yesterday results before
deciding what to do today. Strategy drifts automatically toward what works.

## Day-0 Setup Checklist (the ONLY human work)

1. Create accounts (all free, ~60 min):
   - Telegram: create a channel + a bot via @BotFather → get `BOT_TOKEN`, `CHAT_ID`
   - X: create account, apply for free developer tier → get API keys
     (optional; system runs on Telegram alone if X approval lags)
   - GitHub: fork/upload this repo
2. Get a free LLM API key (pick one):
   - Groq: https://console.groq.com (free tier, fast, OpenAI-compatible)
   - Google AI Studio: https://aistudio.google.com (free tier)
3. Set repo Secrets (GitHub → Settings → Secrets → Actions):
   - `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - `X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_SECRET` (optional)
4. Enable Actions. The system starts itself on the next cron tick.

## Kill-Switch

Disable the GitHub Action, or delete the Telegram bot. The agent halts itself on
account-level errors (rate limits, bans) — see `kill_conditions` in `config.yaml`.

## Honest Expectations

- Days 1-10: near-zero traction. Normal; the agent is learning what the niche rewards.
- Days 11-20: first compounding signals if the loop is healthy.
- Day 30 output: an asset, not a paycheck. Conversion is the human 1-hour job after.
