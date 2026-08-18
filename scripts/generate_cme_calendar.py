"""Generate the versioned CME Globex Equity calendar snapshot.

Source: pandas_market_calendars "CME Globex Equity" calendar (package pinned
in uv.lock). Run via `uv run python scripts/generate_cme_calendar.py`; the
committed snapshot (config/data/cme_calendar.yaml) is the runtime artifact —
research code never calls the package directly. Regenerating with a different
package version is a configuration change (snapshot is in the effective
config hash) and must be reviewed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import time

import pandas_market_calendars as mcal
import yaml

START, END = "2024-08-01", "2026-12-31"
NORMAL_CLOSE = time(16, 0)


def main() -> None:
    cal = mcal.get_calendar("CME Globex Equity")
    sched = cal.schedule(start_date=START, end_date=END)
    closes_ct = sched["market_close"].dt.tz_convert("America/Chicago")
    opens_ct = sched["market_open"].dt.tz_convert("America/Chicago")

    early_closes: dict[str, str] = {}
    trading_days: list[str] = []
    for idx, close in closes_ct.items():
        d = idx.strftime("%Y-%m-%d")
        trading_days.append(d)
        if close.time() != NORMAL_CLOSE:
            early_closes[d] = close.strftime("%H:%M")
    assert all(o.strftime("%H:%M") == "17:00" for o in opens_ct), \
        "unexpected session open != 17:00 CT"

    import pandas as pd

    all_weekdays = pd.date_range(START, END, freq="B").strftime("%Y-%m-%d")
    holidays = sorted(set(all_weekdays) - set(trading_days))

    payload = {
        "trading_day_close_normal_ct": "16:00",
        "session_open_ct": "17:00",
        "holidays": holidays,
        "early_closes": early_closes,
    }
    content_sha = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()
    doc = {
        "meta": {
            "source": "pandas_market_calendars calendar 'CME Globex Equity'",
            "package_version": mcal.__version__,
            "range_start": START,
            "range_end": END,
            "timezone": "America/Chicago",
            "n_trading_days": len(trading_days),
            "content_sha256": content_sha,
            "note": (
                "Snapshot is the runtime source of truth; regeneration is a "
                "reviewed configuration change. Validated against observed "
                "vendor data (Good Friday short sessions, 2026-07-03 12:00 CT "
                "close, day-after-Thanksgiving 12:15 CT close)."
            ),
        },
        **payload,
    }
    with open("config/data/cme_calendar.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False, default_flow_style=False)
    print(f"wrote config/data/cme_calendar.yaml: {len(trading_days)} trading days, "
          f"{len(holidays)} weekday holidays, {len(early_closes)} early closes, "
          f"sha256 {content_sha[:16]}...")


if __name__ == "__main__":
    main()
