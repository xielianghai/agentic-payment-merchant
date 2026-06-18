# Publish heg-flight to ClawHub

Maintainer notes for publishing the **heg-flight** skill bundle.

This bundle intentionally contains only HEG Flight checkout instructions and
supporting scripts. It does not include the legacy generic checkout skill.

## Prerequisites

- `clawhub` CLI installed and logged in
- Local Agentic Payment Merchant repository available as `MERCHANT_HOME`
- Local payment stack and HEG backend available for smoke testing

## Publish

From this repository:

```bash
cd agent-skill/clawhub
./publish.sh
```

After install, users should set or regenerate `MCPORTER_CONFIG` for their local
machine because the Adapter MCP entrypoint depends on the checkout repository
path.
