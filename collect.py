#!/usr/bin/env python3
"""
Collect LLM token usage from local session files.

Run on each machine to export data. Works on macOS, Linux, and Windows.

Usage:
  python3 collect.py                  # auto-detect hostname
  python3 collect.py --name mybox     # custom machine name
  python3 collect.py --data-dir /path/to/.claude  # custom data dir
"""

import argparse
import json
import glob
import platform
import socket
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Pricing per 1M tokens (USD)
MODEL_PRICING = {
    "opus-4-6":            {"input": 15.0, "output": 75.0, "cache_read": 1.5,  "cache_create": 18.75},
    "opus-4-20250514":     {"input": 15.0, "output": 75.0, "cache_read": 1.5,  "cache_create": 18.75},
    "opus-4-5-20251101":   {"input": 15.0, "output": 75.0, "cache_read": 1.5,  "cache_create": 18.75},
    "sonnet-4-20250514":   {"input": 3.0,  "output": 15.0, "cache_read": 0.3,  "cache_create": 3.75},
    "sonnet-4-6":          {"input": 3.0,  "output": 15.0, "cache_read": 0.3,  "cache_create": 3.75},
    "haiku-4-5-20251001":  {"input": 0.8,  "output": 4.0,  "cache_read": 0.08, "cache_create": 1.0},
}
DEFAULT_PRICING = {"input": 15.0, "output": 75.0, "cache_read": 1.5, "cache_create": 18.75}


def get_pricing(model):
    for key, pricing in MODEL_PRICING.items():
        if key in model:
            return pricing
    return DEFAULT_PRICING


def friendly_model(model):
    if "opus-4-6" in model:   return "Opus 4.6"
    if "opus-4-5" in model:   return "Opus 4.5"
    if "opus-4-" in model:    return "Opus 4"
    if "sonnet-4-6" in model: return "Sonnet 4.6"
    if "sonnet-4-" in model:  return "Sonnet 4"
    if "haiku" in model:      return "Haiku 4.5"
    return model


def guess_data_dir():
    """Find data directory across platforms."""
    home = Path.home()
    candidates = [
        home / ".claude",                           # macOS / Linux
        Path.home() / "AppData" / "Roaming" / "claude",  # Windows alt
    ]
    for c in candidates:
        if (c / "projects").is_dir():
            return c
    return home / ".claude"


def project_name_from_path(path):
    """Extract human-readable project name from session file path."""
    parts = Path(path).parts
    for i, p in enumerate(parts):
        if p == "projects" and i + 1 < len(parts):
            raw = parts[i + 1]
            segments = raw.split("-")
            meaningful = []
            skip = True
            for s in segments:
                if skip and s.lower() in ("", "users", "home", "c:", "d:") or (skip and len(s) <= 1):
                    continue
                # Skip username-looking segments (lowercase, common patterns)
                if skip and not any(c.isupper() for c in s) and len(s) < 15:
                    continue
                skip = False
                meaningful.append(s)
            return "-".join(meaningful) if meaningful else raw
    return "unknown"


def parse_sessions(data_dir):
    """Parse all session JSONL files and return structured data."""
    projects_dir = data_dir / "projects"
    all_files = glob.glob(str(projects_dir / "**" / "*.jsonl"), recursive=True)

    daily = defaultdict(lambda: {
        "input_tokens": 0, "output_tokens": 0,
        "cache_read": 0, "cache_create": 0,
        "messages": 0, "sessions": set(), "cost": 0.0,
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
        "cache_read": 0, "cache_create": 0, "cost": 0.0, "messages": 0, "sessions": set()
    })
    hour_counts = defaultdict(int)

    total_files = len(all_files)
    processed = 0

    for fpath in all_files:
        proj = project_name_from_path(fpath)
        try:
            with open(fpath, "r", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if msg.get("type") != "assistant":
                        continue

                    message = msg.get("message", {})
                    usage = message.get("usage", {})
                    model = message.get("model", "unknown")
                    timestamp = msg.get("timestamp", "")
                    session_id = msg.get("sessionId", "")

                    input_t = usage.get("input_tokens", 0)
                    output_t = usage.get("output_tokens", 0)
                    cache_read_t = usage.get("cache_read_input_tokens", 0)
                    cache_create_t = usage.get("cache_creation_input_tokens", 0)

                    if input_t == 0 and output_t == 0 and cache_read_t == 0 and cache_create_t == 0:
                        continue

                    pricing = get_pricing(model)
                    cost = (
                        input_t * pricing["input"] / 1_000_000
                        + output_t * pricing["output"] / 1_000_000
                        + cache_read_t * pricing["cache_read"] / 1_000_000
                        + cache_create_t * pricing["cache_create"] / 1_000_000
                    )

                    date_str = ""
                    hour = -1
                    if timestamp:
                        try:
                            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                            date_str = dt.strftime("%Y-%m-%d")
                            hour = dt.hour
                        except (ValueError, AttributeError):
                            pass

                    friendly = friendly_model(model)

                    if date_str:
                        d = daily[date_str]
                        d["input_tokens"] += input_t
                        d["output_tokens"] += output_t
                        d["cache_read"] += cache_read_t
                        d["cache_create"] += cache_create_t
                        d["messages"] += 1
                        d["cost"] += cost
                        if session_id:
                            d["sessions"].add(session_id)

                        dm = d["by_model"][friendly]
                        dm["input_tokens"] += input_t
                        dm["output_tokens"] += output_t
                        dm["cache_read"] += cache_read_t
                        dm["cache_create"] += cache_create_t
                        dm["cost"] += cost

                    if hour >= 0:
                        hour_counts[hour] += 1

                    mt = model_totals[friendly]
                    mt["input_tokens"] += input_t
                    mt["output_tokens"] += output_t
                    mt["cache_read"] += cache_read_t
                    mt["cache_create"] += cache_create_t
                    mt["cost"] += cost
                    mt["messages"] += 1

                    pt = project_totals[proj]
                    pt["input_tokens"] += input_t
                    pt["output_tokens"] += output_t
                    pt["cache_read"] += cache_read_t
                    pt["cache_create"] += cache_create_t
                    pt["cost"] += cost
                    pt["messages"] += 1
                    if session_id:
                        pt["sessions"].add(session_id)

        except Exception:
            pass

        processed += 1
        if processed % 100 == 0:
            print(f"  [{processed}/{total_files}] files...")

    print(f"  [{processed}/{total_files}] files total.")

    # Serialize
    daily_list = []
    for date_str in sorted(daily.keys()):
        d = daily[date_str]
        by_model = {m: dict(v) for m, v in d["by_model"].items()}
        daily_list.append({
            "date": date_str,
            "input_tokens": d["input_tokens"], "output_tokens": d["output_tokens"],
            "cache_read": d["cache_read"], "cache_create": d["cache_create"],
            "messages": d["messages"], "sessions": len(d["sessions"]),
            "cost": round(d["cost"], 4), "by_model": by_model,
        })

    model_list = [{"model": m, **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in t.items()}}
                  for m, t in sorted(model_totals.items())]

    project_list = [{
        "project": p,
        "input_tokens": t["input_tokens"], "output_tokens": t["output_tokens"],
        "cache_read": t["cache_read"], "cache_create": t["cache_create"],
        "cost": round(t["cost"], 4), "messages": t["messages"], "sessions": len(t["sessions"]),
    } for p, t in sorted(project_totals.items(), key=lambda x: -x[1]["cost"])]

    hour_list = [{"hour": h, "count": hour_counts.get(h, 0)} for h in range(24)]

    grand = {
        "input_tokens": sum(d["input_tokens"] for d in daily_list),
        "output_tokens": sum(d["output_tokens"] for d in daily_list),
        "cache_read": sum(d["cache_read"] for d in daily_list),
        "cache_create": sum(d["cache_create"] for d in daily_list),
        "total_cost": round(sum(d["cost"] for d in daily_list), 2),
        "total_messages": sum(d["messages"] for d in daily_list),
        "total_sessions": len(set().union(*(daily[d]["sessions"] for d in daily))) if daily else 0,
        "total_files_parsed": total_files,
        "date_range": {
            "start": daily_list[0]["date"] if daily_list else "",
            "end": daily_list[-1]["date"] if daily_list else "",
        },
    }

    return {
        "grand": grand, "daily": daily_list, "models": model_list,
        "projects": project_list, "hours": hour_list,
    }


def main():
    parser = argparse.ArgumentParser(description="Collect LLM token usage")
    parser.add_argument("--name", default=None, help="Machine identifier (default: hostname)")
    parser.add_argument("--data-dir", default=None, help="Path to data directory")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: ./machines/)")
    args = parser.parse_args()

    machine_name = args.name or socket.gethostname().split(".")[0].lower()
    data_dir = Path(args.data_dir) if args.data_dir else guess_data_dir()
    output_dir = Path(args.output_dir) if args.output_dir else Path(__file__).parent / "machines"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Collecting from: {data_dir}/projects/")
    print(f"Machine name:    {machine_name}")

    data = parse_sessions(data_dir)

    # Add machine metadata
    data["machine"] = {
        "name": machine_name,
        "hostname": socket.gethostname(),
        "platform": platform.system(),
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

    out_path = output_dir / f"data-{machine_name}.json"
    with open(out_path, "w") as f:
        json.dump(data, f)

    print(f"Written to:      {out_path}")
    print(f"  Cost estimate: ${data['grand']['total_cost']:.2f}")
    print(f"  Messages:      {data['grand']['total_messages']:,}")
    print(f"  Sessions:      {data['grand']['total_sessions']}")


if __name__ == "__main__":
    main()
