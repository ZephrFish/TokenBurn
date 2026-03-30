#!/usr/bin/env python3
"""
Merge per-machine data files and generate the dashboard HTML.

Usage:
  python3 build.py                    # merge all machines/*.json → index.html
  python3 build.py --machines-dir ./machines --output ./index.html
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def merge_machine_data(machines_dir):
    """Merge all data-*.json files into a single dataset."""
    files = sorted(machines_dir.glob("data-*.json"))
    if not files:
        raise FileNotFoundError(f"No data-*.json files found in {machines_dir}")

    # Merged structures
    daily = defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read": 0, "cache_create": 0,
        "messages": 0, "sessions": 0, "cost": 0.0,
        "by_model": defaultdict(lambda: {
            "input_tokens": 0, "output_tokens": 0,
            "cache_read": 0, "cache_create": 0, "cost": 0.0
        })
    })
    model_totals = defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read": 0, "cache_create": 0, "cost": 0.0, "messages": 0
    })
    project_totals = defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read": 0, "cache_create": 0, "cost": 0.0, "messages": 0, "sessions": 0
    })
    hour_counts = defaultdict(int)
    machines = []

    total_sessions = 0
    total_messages = 0
    total_cost = 0.0

    for fpath in files:
        print(f"  Merging: {fpath.name}")
        with open(fpath) as f:
            data = json.load(f)

        machine_info = data.get("machine", {"name": fpath.stem.replace("data-", "")})
        machine_name = machine_info.get("name", "?")
        machine_info["cost"] = data["grand"]["total_cost"]
        machine_info["messages"] = data["grand"]["total_messages"]
        machine_info["sessions"] = data["grand"]["total_sessions"]
        machines.append(machine_info)

        total_sessions += data["grand"]["total_sessions"]
        total_messages += data["grand"]["total_messages"]
        total_cost += data["grand"]["total_cost"]

        # Merge daily (both combined and per-machine)
        for d in data.get("daily", []):
            dd = daily[d["date"]]
            for k in ("input_tokens", "output_tokens", "cache_read", "cache_create", "messages", "sessions"):
                dd[k] += d.get(k, 0)
            dd["cost"] += d.get("cost", 0)
            for model, mv in d.get("by_model", {}).items():
                dm = dd["by_model"][model]
                for k in ("input_tokens", "output_tokens", "cache_read", "cache_create", "cost"):
                    dm[k] += mv.get(k, 0)
            # Per-machine daily breakdown
            if "by_machine" not in dd:
                dd["by_machine"] = {}
            dd["by_machine"][machine_name] = {
                "input_tokens": d.get("input_tokens", 0),
                "output_tokens": d.get("output_tokens", 0),
                "cache_read": d.get("cache_read", 0),
                "cache_create": d.get("cache_create", 0),
                "messages": d.get("messages", 0),
                "sessions": d.get("sessions", 0),
                "cost": d.get("cost", 0),
            }

        # Merge models
        for m in data.get("models", []):
            mt = model_totals[m["model"]]
            for k in ("input_tokens", "output_tokens", "cache_read", "cache_create", "cost", "messages"):
                mt[k] += m.get(k, 0)

        # Merge projects (prefix with machine name for uniqueness)
        for p in data.get("projects", []):
            key = f"{p['project']} ({machine_name})"
            pt = project_totals[key]
            for k in ("input_tokens", "output_tokens", "cache_read", "cache_create", "cost", "messages", "sessions"):
                pt[k] += p.get(k, 0)

        # Merge hours
        for h in data.get("hours", []):
            hour_counts[h["hour"]] += h.get("count", 0)

    # Build output
    daily_list = []
    for date_str in sorted(daily.keys()):
        d = daily[date_str]
        by_model = {m: dict(v) for m, v in d["by_model"].items()}
        by_machine = d.get("by_machine", {})
        daily_list.append({
            "date": date_str,
            "input_tokens": d["input_tokens"], "output_tokens": d["output_tokens"],
            "cache_read": d["cache_read"], "cache_create": d["cache_create"],
            "messages": d["messages"], "sessions": d["sessions"],
            "cost": round(d["cost"], 4), "by_model": by_model, "by_machine": by_machine,
        })

    model_list = [{"model": m, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in t.items()}}
                  for m, t in sorted(model_totals.items())]

    project_list = [{
        "project": p, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in t.items()}
    } for p, t in sorted(project_totals.items(), key=lambda x: -x[1]["cost"])]

    hour_list = [{"hour": h, "count": hour_counts.get(h, 0)} for h in range(24)]

    grand = {
        "input_tokens": sum(d["input_tokens"] for d in daily_list),
        "output_tokens": sum(d["output_tokens"] for d in daily_list),
        "cache_read": sum(d["cache_read"] for d in daily_list),
        "cache_create": sum(d["cache_create"] for d in daily_list),
        "total_cost": round(total_cost, 2),
        "total_messages": total_messages,
        "total_sessions": total_sessions,
        "date_range": {
            "start": daily_list[0]["date"] if daily_list else "",
            "end": daily_list[-1]["date"] if daily_list else "",
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    return {
        "grand": grand, "daily": daily_list, "models": model_list,
        "projects": project_list, "hours": hour_list, "machines": machines,
    }


def build_html(data, template_path):
    """Inject data into HTML template."""
    with open(template_path) as f:
        html = f.read()
    return html.replace("/*__DATA_PLACEHOLDER__*/", f"const DATA = {json.dumps(data)};", 1)


def main():
    parser = argparse.ArgumentParser(description="Build TokenBurn dashboard")
    parser.add_argument("--machines-dir", default=None, help="Directory with data-*.json files")
    parser.add_argument("--output", default=None, help="Output HTML path")
    parser.add_argument("--template", default=None, help="Template HTML path")
    args = parser.parse_args()

    base = Path(__file__).parent
    machines_dir = Path(args.machines_dir) if args.machines_dir else base / "machines"
    output_path = Path(args.output) if args.output else base / "index.html"
    template_path = Path(args.template) if args.template else base / "template.html"

    print("Merging machine data...")
    data = merge_machine_data(machines_dir)

    print("Building dashboard...")
    html = build_html(data, template_path)
    with open(output_path, "w") as f:
        f.write(html)

    print(f"\nDashboard: {output_path}")
    print(f"  Machines:  {len(data['machines'])}")
    print(f"  Cost:      ${data['grand']['total_cost']:.2f}")
    print(f"  Messages:  {data['grand']['total_messages']:,}")
    print(f"  Sessions:  {data['grand']['total_sessions']}")
    for m in data["machines"]:
        print(f"    - {m['name']} ({m.get('platform','?')}): ${m['cost']:.2f}, {m['messages']:,} msgs")


if __name__ == "__main__":
    main()
