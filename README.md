# TokenBurn

Self-hosted dashboard for tracking LLM token usage and cost across multiple machines. Compares API-equivalent costs against your subscription.

<img width="1440" height="543" alt="image" src="https://github.com/user-attachments/assets/fe4b6089-73f0-4eaf-b834-a40708675374" />

Ever been curious about what your actual spend rate would be in API usage vs what a Claude subscription is costing you? Well now you can, it has a breakdown per machine where you can run `./sync.sh||./sync.ps1` and it'll pick up your local machine if you use the ame account across multple hosts and projects.

You can also do breakdown per project:
<img width="1424" height="610" alt="image" src="https://github.com/user-attachments/assets/fe848538-25c3-44e9-ba39-671a5d6b9ec4" />

Everyone loves a graph so there's pleny in here.

## Setup

### 1. Create your repo from this template

Click **"Use this template"** on GitHub, then clone it:

```bash
git clone git@github.com:ZephrFish/TokenBurn.git
cd TokenBurn
```

### 2. Collect data on each machine

Clone the repo and run the sync script. Works on macOS, Linux, and Windows.

```bash
# macOS / Linux
./sync.sh

# Windows (PowerShell)
.\sync.ps1
```

This parses all LLM session files from `the session data directory`, writes `machines/data-<hostname>.json`, and pushes.

```bash
# Optional flags
./sync.sh --name my-server              # custom machine name
./sync.sh --data-dir /path/to/data  # custom data directory
```

### 3. Build and serve the dashboard

On whichever machine will host the dashboard:

```bash
git pull
python3 build.py
python3 -m http.server 8080 --bind 0.0.0.0
```

Open `http://<machine-ip>:8080` from your network.

## Automate collection

Add a cron job on each machine:

```
0 2 * * * cd /path/to/TokenBurn && ./sync.sh >> /tmp/tokenburn.log 2>&1
```

## Dashboard features

- **Filters** - date range presets, machine, project
- **Currency selector** - USD, GBP, EUR, CAD, AUD, JPY, CHF, INR, BRL
- **Subscription comparison** - configurable cost/month and start date, savings multiplier, monthly and cumulative cost vs sub
- **Charts** - daily token usage, cost by model/project, hourly activity, cost trends
- **Tables** - per-project and per-day breakdowns

All settings (currency, sub cost, sub start date) are persisted in the browser via localStorage.

## Requirements

- Python 3.6+
- Git
- LLM session data (`the session data directory`)

## Files

```
collect.py      Run on each machine - exports local session data
build.py        Merges all machine data - generates index.html
template.html   Dashboard HTML template
sync.sh         macOS/Linux: collect + git push
sync.ps1        Windows: collect + git push
machines/       Per-machine JSON data files (gitignored in template)
```
