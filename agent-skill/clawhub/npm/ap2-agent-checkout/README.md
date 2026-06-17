# ap2-agent-checkout

One-shot demo installer (Alipay A2A style): ClawHub **ap2-checkout** skill, OpenClaw `openclaw.json`, mcporter config, and **auto-start** of the local AP2 mock backend.

## Prerequisites

- Node.js 18+
- [OpenClaw](https://github.com/openclaw/openclaw) with `~/.openclaw/openclaw.json`
- AP2 repository cloned (for Python mock services via `uv`)
- `clawhub` CLI logged in (optional; falls back to bundled skill copy)

## Demo install (from AP2 clone)

```bash
cd /path/to/AP2
npx -y file:code/samples/python/scenarios/a2a/unified/clawhub/npm/ap2-agent-checkout install
```

Or with explicit home:

```bash
AP2_HOME=/path/to/AP2 npx -y ap2-agent-checkout install
```

After install:

1. Restart the OpenClaw gateway.
2. Talk to the agent in Feishu or another OpenClaw-compatible agent. Generic shopping prompts such as “我要购物” / “I want to shop” and flight prompts such as “我要买机票” should use the `ap2-checkout` skill first and run against the local AP2 mock checkout flow.

## Commands

| Command | Description |
|---------|-------------|
| `install` | Default: skill + config + start backend if needed |
| `status` | Show `AP2_HOME` and port 8091–8094 / 8100–8103 |
| `stop` | Run `openclaw/stop_ap2_backend.sh` |
| `start` | Start backend only |

Config is stored in `~/.ap2-agent-checkout/config.json` and `mcporter.json`.

## What it does

1. Detects `AP2_HOME` (env → saved config → walk up from package for repo root).
2. `clawhub install ap2-checkout` into `~/.openclaw/workspace/skills/`.
3. Writes `~/.ap2-agent-checkout/mcporter.json` and enables `mcporter` + `ap2-checkout` in `openclaw.json`.
4. If mock ports are not up, runs `openclaw/start_ap2_backend.sh` with `AP2_INSTALL_QUICK=1` (skips verify step for faster demo).
5. Leaves `ap2-checkout` enabled so shopping, purchase, and flight-booking intents prefer AP2 mock checkout.

ClawHub skill: https://clawhub.ai/xielianghai/ap2-checkout
