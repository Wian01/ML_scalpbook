"""CME trading-session assignment and RTH segmentation.

Canonical rules (spec section 9/10):
- session_id is the CME trading day; a trading day begins at the configured
  session boundary (17:00 America/Chicago) on the prior calendar day.
- V1 RTH is 08:30-15:00 America/Chicago.
- Storage/timestamps remain UTC nanoseconds; DST changes the UTC offset of the
  session boundary and RTH window, so these must never be fixed UTC windows.

Boundary and RTH values come from config/data/sessions.yaml
(nqresearch.config.SessionWindowConfig), not from code.

Two implementations are provided and cross-checked by unit tests:
- scalar (zoneinfo-based), used as the reference definition;
- vectorized polars expressions, used for bulk audit work.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import polars as pl

from nqresearch.config import SessionWindowConfig, load_session_config

NS = 1_000_000_000


def _cfg(cfg: SessionWindowConfig | None) -> SessionWindowConfig:
    return cfg if cfg is not None else load_session_config()


def _to_exchange_local(ts_event_ns: int, cfg: SessionWindowConfig) -> datetime:
    # Second precision is sufficient for session/RTH boundaries; avoids float ns loss.
    seconds, rem_ns = divmod(int(ts_event_ns), NS)
    dt = datetime.fromtimestamp(seconds, tz=timezone.utc).astimezone(ZoneInfo(cfg.timezone))
    return dt.replace(microsecond=rem_ns // 1000)


def trading_session(ts_event_ns: int, cfg: SessionWindowConfig | None = None) -> date:
    """CME trading day for a UTC-nanosecond event timestamp."""
    c = _cfg(cfg)
    dt_local = _to_exchange_local(ts_event_ns, c)
    d = dt_local.date()
    if dt_local.time() >= c.session_boundary_time:
        d = d + timedelta(days=1)
    return d


def is_rth(ts_event_ns: int, cfg: SessionWindowConfig | None = None) -> bool:
    """True if the timestamp falls inside configured RTH (exchange-local)."""
    c = _cfg(cfg)
    t = _to_exchange_local(ts_event_ns, c).time()
    return c.rth_start_time <= t < c.rth_end_time


def session_utc_dates(session: date, cfg: SessionWindowConfig | None = None) -> list[date]:
    """UTC calendar dates a full session's window can span.

    A session runs from the boundary (17:00 exchange-local, i.e. 22:00/23:00
    UTC) on the prior calendar day through the following boundary, so its
    events fall on UTC dates {session-1, session}.
    """
    return [session - timedelta(days=1), session]


def session_exprs(
    ts_col: str = "ts_event", cfg: SessionWindowConfig | None = None
) -> list[pl.Expr]:
    """Polars expressions adding session_id (date) and rth_flag columns."""
    c = _cfg(cfg)
    boundary = c.session_boundary_time
    rth_s, rth_e = c.rth_start_time, c.rth_end_time
    local = (
        pl.from_epoch(pl.col(ts_col).cast(pl.Int64), time_unit="ns")
        .dt.replace_time_zone("UTC")
        .dt.convert_time_zone(c.timezone)
    )
    local_time = local.dt.time()
    session = (
        pl.when(local_time >= pl.time(boundary.hour, boundary.minute))
        .then(local.dt.date() + pl.duration(days=1))
        .otherwise(local.dt.date())
        .cast(pl.Date)
        .alias("session_id")
    )
    rth = (
        (local_time >= pl.time(rth_s.hour, rth_s.minute))
        & (local_time < pl.time(rth_e.hour, rth_e.minute))
    ).alias("rth_flag")
    return [session, rth]
