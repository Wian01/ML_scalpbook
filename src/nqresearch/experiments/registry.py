"""DuckDB experiment registry (canonical §38) with immutable lifecycle (§37).

Design (post independent-audit remediation):
- DuckDB is the AUTHORITATIVE store: experiments table, hash-chained
  append-only lifecycle_audit table (prev_hash/record_hash tamper evidence).
  The registry is SINGLE-WRITER — DuckDB's write lock refuses a second
  writable connection, and that enforcement is tested; within the single
  writer, sequence IDs come from DuckDB SEQUENCEs and are never reused
  (refused/rolled-back operations leave gaps, not collisions). The chain is
  verified fail-closed: on open (before recovery) and before every
  registration, inspection, and transition.
- The per-experiment directory (prereg.yaml + audit_projection.json) is a
  committed lightweight record: prereg.yaml is the immutable registered
  specification (content-hash-verified against the DB on EVERY inspection
  and transition — missing, altered, retyped, or substituted records all
  fail closed); audit_projection.json is honestly a MATERIALIZED PROJECTION
  of the DuckDB audit table, rebuilt from it (the DB chain is the
  append-only source of truth).
- Registration is crash-safe: the DB transaction commits only after the
  files are staged with a .pending marker; on any failure the transaction
  rolls back and staged files are removed (no orphan directory, no DB-only
  or file-only registration; the consumed sequence value is never reused).
  On open, recovery re-materializes projections for committed rows whose
  directory is missing or still marked .pending — but a missing/altered
  prereg.yaml WITHOUT a pending marker is tampering and is never silently
  restored.
- Every write destination (DB file, experiment directories, every record
  file) passes the raw-write guard, including when NQR_REGISTRY_DB /
  NQR_EXPERIMENTS_DIR overrides are set.
- §38: source dataset hashes are required pre-registration fields; an
  outputs manifest can be recorded at terminal transitions; prereg/outputs
  are JSON documents so metrics/predictions can be added later without a
  schema redesign. Parent experiment references are validated. No delete
  API exists; failed/null experiments are permanently retained.

No real market experiment may be registered in Milestone 1; tests use
synthetic metadata only.
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import yaml

from nqresearch import paths
from nqresearch.experiments.models import (
    ALL_STATES,
    STATE_PLANNED,
    STATE_RUNNING,
    TERMINAL_STATES,
    VALID_TRANSITIONS,
    PreRegistration,
)
from nqresearch.rawguard import assert_write_outside_raw

SCHEMA_VERSION = 4
RECORD_PENDING = "PENDING_PROJECTION"
RECORD_FINALIZED = "FINALIZED"


def _clear_pending_marker(exp_dir: Path) -> None:
    (exp_dir / PENDING_MARKER).unlink(missing_ok=True)
PENDING_MARKER = ".pending"
PROJECTION_FILENAME = "audit_projection.json"
GENESIS_HASH = "0" * 64


class RegistryError(RuntimeError):
    pass


class ImmutableSpecError(RegistryError):
    """The registered specification is missing or was modified."""


class ProjectionRecoveryRequiredError(RegistryError):
    """The lifecycle change WAS COMMITTED to the authoritative DuckDB store,
    but the materialized projection could not be written. Lifecycle state HAS
    changed; the projection is a recoverable materialized view and will be
    rebuilt on the next open or verified inspection."""


class InvalidTransitionError(RegistryError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical_prereg_bytes(prereg: PreRegistration) -> bytes:
    return json.dumps(prereg.model_dump(), sort_keys=True).encode()


def _record_hash(prev_hash: str, record: dict) -> str:
    body = json.dumps(
        {k: v for k, v in record.items() if k not in ("prev_hash", "record_hash")},
        sort_keys=True,
    )
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


def reproducibility_snapshot(seeds: list[int], experiment_id: str) -> dict:
    """Canonical §47 capture."""
    from nqresearch.config import effective_config_hash
    from nqresearch.qa.cache import package_source_hash
    from nqresearch.qa.report import _git_sha

    lock = paths.ROOT / "uv.lock"
    # Separate research-configuration identity (active partitions, when they
    # exist) so a partition change changes the experiment identity WITHOUT
    # conflating it with acquisition semantics (which have their own binding).
    active_parts = paths.ROOT / "config" / "data" / "partitions_active.yaml"
    active_parts_sha = (
        hashlib.sha256(active_parts.read_bytes()).hexdigest()
        if active_parts.is_file() else None
    )
    return {
        "active_partitions_sha256": active_parts_sha,
        "git_sha": _git_sha(paths.ROOT),
        "python_version": sys.version.split()[0],
        "os_platform": platform.platform(),
        "dependency_lock_sha256": (
            hashlib.sha256(lock.read_bytes()).hexdigest() if lock.is_file() else None
        ),
        "config_hash": effective_config_hash(),
        "code_hash": package_source_hash(),
        "random_seeds": seeds,
        "experiment_id": experiment_id,
    }


class ExperimentRegistry:
    def __init__(self, db_path: Path | None = None,
                 experiments_dir: Path | None = None):
        self.db_path = Path(db_path or paths.registry_db())
        self.experiments_dir = Path(experiments_dir or paths.experiments_dir())
        assert_write_outside_raw(self.db_path)
        assert_write_outside_raw(self.experiments_dir)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        # Explicit SINGLE-WRITER enforcement: an exclusive lock file (DuckDB
        # shares its instance within one process, so its own file lock is not
        # sufficient). A stale lock after a hard crash must be investigated
        # and removed manually — the registry never steals a lock.
        import os as _os

        self._lock_path = self.db_path.with_suffix(".lock")
        try:
            fd = _os.open(str(self._lock_path),
                          _os.O_CREAT | _os.O_EXCL | _os.O_WRONLY)
            _os.write(fd, str(_os.getpid()).encode())
            _os.close(fd)
        except FileExistsError as e:
            raise RegistryError(
                "registry is single-writer and the lock is already held "
                f"({self._lock_path}); close the other registry handle (or "
                "investigate a stale lock after a crash)"
            ) from e
        try:
            self._con = duckdb.connect(str(self.db_path))
            self._init_schema()
            # Chain integrity is verified BEFORE recovery and before any use:
            # a corrupted chain blocks show/registration/recovery/transitions.
            self.verify_audit_chain()
            self._recover()
        except Exception:
            self._release_lock()
            raise

    def _release_lock(self) -> None:
        try:
            self._lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    def close(self) -> None:
        try:
            self._con.close()
        finally:
            self._release_lock()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- schema ------------------------------------------------------------
    def _init_schema(self) -> None:
        con = self._con
        con.execute("BEGIN")
        try:
            con.execute(
                "CREATE TABLE IF NOT EXISTS registry_meta("
                "key VARCHAR PRIMARY KEY, value VARCHAR)"
            )
            row = con.execute(
                "SELECT value FROM registry_meta WHERE key='schema_version'"
            ).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO registry_meta VALUES ('schema_version', ?)",
                    [str(SCHEMA_VERSION)],
                )
            elif int(row[0]) != SCHEMA_VERSION:
                raise RegistryError(
                    f"registry schema version {row[0]} unsupported by code "
                    f"version {SCHEMA_VERSION}; explicit migration required"
                )
            con.execute("CREATE SEQUENCE IF NOT EXISTS exp_seq START 1")
            con.execute("CREATE SEQUENCE IF NOT EXISTS audit_seq START 1")
            con.execute(
                "CREATE TABLE IF NOT EXISTS experiments("
                "experiment_id VARCHAR PRIMARY KEY,"
                "trial_number INTEGER NOT NULL,"
                "registered_at_utc VARCHAR NOT NULL,"
                "status VARCHAR NOT NULL,"
                "prereg_json VARCHAR NOT NULL,"
                "prereg_sha256 VARCHAR NOT NULL,"
                "reproducibility_json VARCHAR NOT NULL,"
                "outputs_json VARCHAR NOT NULL DEFAULT 'null',"
                "record_state VARCHAR NOT NULL DEFAULT 'FINALIZED',"
                "parent_experiment VARCHAR,"
                "parent_hypothesis VARCHAR,"
                "notes VARCHAR)"
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS lifecycle_audit("
                "seq BIGINT PRIMARY KEY,"
                "experiment_id VARCHAR NOT NULL,"
                "at_utc VARCHAR NOT NULL,"
                "event VARCHAR NOT NULL,"
                "from_status VARCHAR,"
                "to_status VARCHAR,"
                "note VARCHAR,"
                "prev_hash VARCHAR NOT NULL,"
                "record_hash VARCHAR NOT NULL)"
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise

    # -- audit (hash-chained, sequence-allocated, append-only) -------------
    def _append_audit(self, experiment_id: str, event: str,
                      from_status: str | None, to_status: str | None,
                      note: str) -> dict:
        con = self._con
        seq = con.execute("SELECT nextval('audit_seq')").fetchone()[0]
        prev = con.execute(
            "SELECT record_hash FROM lifecycle_audit ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        prev_hash = prev[0] if prev else GENESIS_HASH
        record = {
            "seq": seq, "experiment_id": experiment_id, "at_utc": _now(),
            "event": event, "from_status": from_status, "to_status": to_status,
            "note": note, "prev_hash": prev_hash,
        }
        record["record_hash"] = _record_hash(prev_hash, record)
        con.execute(
            "INSERT INTO lifecycle_audit VALUES (?,?,?,?,?,?,?,?,?)",
            [record[k] for k in ("seq", "experiment_id", "at_utc", "event",
                                 "from_status", "to_status", "note",
                                 "prev_hash", "record_hash")],
        )
        return record

    def _audit_rows(self, experiment_id: str | None = None) -> list[dict]:
        where = "WHERE experiment_id=?" if experiment_id else ""
        args = [experiment_id] if experiment_id else []
        return [
            {"seq": r[0], "experiment_id": r[1], "at_utc": r[2], "event": r[3],
             "from_status": r[4], "to_status": r[5], "note": r[6],
             "prev_hash": r[7], "record_hash": r[8]}
            for r in self._con.execute(
                f"SELECT * FROM lifecycle_audit {where} ORDER BY seq", args
            ).fetchall()
        ]

    def verify_audit_chain(self) -> int:
        """Verify the tamper-evident hash chain; returns record count."""
        prev = GENESIS_HASH
        rows = self._audit_rows()
        for r in rows:
            if r["prev_hash"] != prev or _record_hash(prev, r) != r["record_hash"]:
                raise RegistryError(
                    f"lifecycle audit chain broken at seq {r['seq']}"
                )
            prev = r["record_hash"]
        return len(rows)

    # -- projection (materialized from DuckDB; DB is authoritative) --------
    def _projection_payload(self, experiment_id: str) -> dict:
        events = self._audit_rows(experiment_id)
        return {
            "note": ("MATERIALIZED PROJECTION of the authoritative "
                     "hash-chained DuckDB lifecycle_audit table; "
                     "rebuilt, not independently append-only"),
            "event_count": len(events),
            "head_hash": events[-1]["record_hash"] if events else GENESIS_HASH,
            "events": events,
        }

    def _write_projection(self, experiment_id: str) -> None:
        """Atomic temp-write-and-replace of the materialized projection."""
        import os as _os

        exp_dir = self.experiments_dir / experiment_id
        if not exp_dir.is_dir():
            return
        final = assert_write_outside_raw(exp_dir / PROJECTION_FILENAME)
        tmp = final.with_name(final.name + ".tmp")
        tmp.write_text(
            json.dumps(self._projection_payload(experiment_id), indent=1),
            encoding="utf-8",
        )
        _os.replace(tmp, final)

    def _projection_current(self, experiment_id: str) -> bool:
        """True iff the on-disk projection exactly matches the verified chain
        (head hash AND event count)."""
        path = self.experiments_dir / experiment_id / PROJECTION_FILENAME
        if not path.is_file():
            return False
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        expected = self._projection_payload(experiment_id)
        return (
            doc.get("head_hash") == expected["head_hash"]
            and doc.get("event_count") == expected["event_count"]
            and doc.get("events") == expected["events"]
        )

    def _reconcile_projection(self, experiment_id: str) -> None:
        """Missing/stale/partial projections are a RECOVERABLE materialized-
        view condition: rebuild atomically from the verified DuckDB chain.
        A missing EXPERIMENT DIRECTORY is tampering (handled elsewhere) and
        is never recreated here."""
        exp_dir = self.experiments_dir / experiment_id
        if not exp_dir.is_dir():
            return
        if not self._projection_current(experiment_id):
            self._write_projection(experiment_id)

    # -- crash recovery ----------------------------------------------------
    def _recover(self) -> None:
        """Deterministic recovery keyed on DURABLE record_state:

        - row record_state=PENDING_PROJECTION (crash between DB commit and
          finalize): safely re-materialize the files from the DB, audit, and
          finalize;
        - row record_state=FINALIZED with a later-deleted directory/record:
          TAMPERING — never reconstructed; operations on it fail closed via
          the immutability check;
        - directory with a pending marker but NO committed row (pre-commit
          orphan): quarantined deterministically, never treated as a valid
          experiment.
        """
        known_ids = set()
        for r in self._con.execute(
            "SELECT experiment_id, prereg_json, record_state FROM experiments"
        ).fetchall():
            exp_id, prereg_json, record_state = r
            known_ids.add(exp_id)
            exp_dir = self.experiments_dir / exp_id
            if record_state == RECORD_FINALIZED:
                # A FINALIZED row with a pending marker is a registration
                # INCONSISTENCY: fail closed, never accept.
                if exp_dir.exists() and (exp_dir / PENDING_MARKER).exists():
                    raise RegistryError(
                        f"{exp_id}: FINALIZED row with pending marker — "
                        "inconsistent registry state; failing closed "
                        "(investigate before reopening)"
                    )
                # Missing/stale projections are a recoverable materialized-
                # view condition: rebuilt below. Missing DIRECTORIES are
                # tampering and stay fail-closed via the immutability check.
                self._reconcile_projection(exp_id)
                continue  # intact FINALIZED rows are never reconstructed
            # PENDING: complete the registration idempotently.
            exp_dir.mkdir(parents=True, exist_ok=True)
            prereg = PreRegistration(**json.loads(prereg_json))
            final = assert_write_outside_raw(exp_dir / "prereg.yaml")
            final.write_text(
                yaml.safe_dump(prereg.model_dump(), sort_keys=True),
                encoding="utf-8",
            )
            self._con.execute("BEGIN")
            try:
                self._append_audit(exp_id, "RECOVERED_PROJECTION", None, None,
                                   "completed pending registration on reopen")
                self._con.execute("COMMIT")
            except Exception:
                self._con.execute("ROLLBACK")
                raise
            self._finalize_registration(exp_id)
        # Pre-commit orphans: pending-marked directories with no DB row.
        if self.experiments_dir.is_dir():
            for d in self.experiments_dir.iterdir():
                if (d.is_dir() and (d / PENDING_MARKER).is_file()
                        and d.name not in known_ids
                        and not d.name.endswith(".orphaned")):
                    quarantine = d.with_name(d.name + ".orphaned")
                    d.rename(quarantine)
                    self._con.execute("BEGIN")
                    try:
                        self._append_audit(
                            d.name, "ORPHAN_QUARANTINED", None, None,
                            f"pre-commit orphan directory moved to {quarantine.name}",
                        )
                        self._con.execute("COMMIT")
                    except Exception:
                        self._con.execute("ROLLBACK")
                        raise

    # -- registration ------------------------------------------------------
    def register(self, prereg: PreRegistration) -> str:
        self.verify_audit_chain()  # corrupted chain blocks registration
        con = self._con
        if prereg.parent_experiment is not None:
            parent = con.execute(
                "SELECT 1 FROM experiments WHERE experiment_id=?",
                [prereg.parent_experiment],
            ).fetchone()
            if parent is None:
                raise RegistryError(
                    f"parent experiment {prereg.parent_experiment!r} is not "
                    "registered"
                )
        trial_number = con.execute("SELECT nextval('exp_seq')").fetchone()[0]
        experiment_id = f"EXP-{trial_number:04d}"
        exp_dir = self.experiments_dir / experiment_id
        if exp_dir.exists():
            raise RegistryError(
                f"{experiment_id}: experiment directory already exists; "
                "IDs are never reused or overwritten"
            )
        prereg_bytes = _canonical_prereg_bytes(prereg)
        prereg_sha = hashlib.sha256(prereg_bytes).hexdigest()
        repro = reproducibility_snapshot(prereg.seeds, experiment_id)

        con.execute("BEGIN")
        staged = False
        try:
            exists = con.execute(
                "SELECT 1 FROM experiments WHERE experiment_id=?", [experiment_id]
            ).fetchone()
            if exists:
                raise RegistryError(f"{experiment_id} already registered")
            con.execute(
                "INSERT INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                [experiment_id, trial_number, _now(), STATE_PLANNED,
                 prereg_bytes.decode(), prereg_sha, json.dumps(repro), "null",
                 RECORD_PENDING, prereg.parent_experiment,
                 prereg.parent_hypothesis, prereg.notes],
            )
            self._append_audit(experiment_id, "REGISTERED", None, STATE_PLANNED,
                               f"trial_number={trial_number}")
            # Stage files BEFORE commit; failures roll everything back.
            exp_dir.mkdir(parents=True)
            staged = True
            (exp_dir / PENDING_MARKER).write_text("registration in progress")
            final = assert_write_outside_raw(exp_dir / "prereg.yaml")
            final.write_text(
                yaml.safe_dump(prereg.model_dump(), sort_keys=True),
                encoding="utf-8",
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            if staged:
                shutil.rmtree(exp_dir, ignore_errors=True)
            raise  # consumed sequence value is never reused: gap, not reuse
        # Finalization: FINALIZED is the LAST durable step, only after every
        # filesystem record (prereg + projection) is present and the pending
        # marker is cleared. A failure here leaves the row PENDING; reopening
        # recovers it idempotently.
        self._finalize_registration(experiment_id)
        return experiment_id

    def _finalize_registration(self, experiment_id: str) -> None:
        exp_dir = self.experiments_dir / experiment_id
        self._write_projection(experiment_id)
        if not (exp_dir / PROJECTION_FILENAME).is_file():
            raise RegistryError(
                f"{experiment_id}: projection write did not materialize; "
                "registration remains PENDING for recovery"
            )
        _clear_pending_marker(exp_dir)
        if (exp_dir / PENDING_MARKER).exists():
            raise RegistryError(
                f"{experiment_id}: pending marker could not be cleared; "
                "registration remains PENDING for recovery"
            )
        con = self._con
        con.execute("BEGIN")
        try:
            con.execute(
                "UPDATE experiments SET record_state=? WHERE experiment_id=?",
                [RECORD_FINALIZED, experiment_id],
            )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise

    # -- spec immutability (fail closed) -----------------------------------
    def _verify_spec_immutable(self, experiment_id: str, stored_sha: str,
                               stored_json: str) -> None:
        prereg = PreRegistration(**json.loads(stored_json))
        if hashlib.sha256(_canonical_prereg_bytes(prereg)).hexdigest() != stored_sha:
            raise ImmutableSpecError(f"{experiment_id}: stored spec hash mismatch")
        yaml_file = self.experiments_dir / experiment_id / "prereg.yaml"
        if not yaml_file.is_file():
            raise ImmutableSpecError(
                f"{experiment_id}: committed pre-registration record "
                "prereg.yaml is MISSING; failing closed exactly like an "
                "altered record"
            )
        try:
            on_disk = PreRegistration(
                **yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
            )
            disk_sha = hashlib.sha256(_canonical_prereg_bytes(on_disk)).hexdigest()
        except ImmutableSpecError:
            raise
        except Exception as e:
            raise ImmutableSpecError(
                f"{experiment_id}: prereg.yaml is unreadable/invalid "
                f"({e}); failing closed"
            ) from e
        if disk_sha != stored_sha:
            raise ImmutableSpecError(
                f"{experiment_id}: prereg.yaml was modified after "
                "registration; the registered specification is immutable — "
                "a new hypothesis/configuration requires a NEW experiment"
            )

    # -- inspection --------------------------------------------------------
    def _show_unverified(self, experiment_id: str) -> dict:
        """PRIVATE diagnostic accessor (tests/diagnostics of refused states
        only). Public inspection always verifies."""
        row = self._con.execute(
            "SELECT experiment_id, trial_number, registered_at_utc, status,"
            " prereg_json, prereg_sha256, reproducibility_json, outputs_json,"
            " record_state, parent_experiment, parent_hypothesis, notes"
            " FROM experiments WHERE experiment_id=?", [experiment_id]
        ).fetchone()
        if row is None:
            raise RegistryError(f"unknown experiment: {experiment_id}")
        return {
            "experiment_id": row[0], "trial_number": row[1],
            "registered_at_utc": row[2], "status": row[3],
            "prereg": json.loads(row[4]), "prereg_sha256": row[5],
            "reproducibility": json.loads(row[6]),
            "outputs": json.loads(row[7]),
            "record_state": row[8],
            "parent_experiment": row[9], "parent_hypothesis": row[10],
            "notes": row[11],
            "audit": self._audit_rows(experiment_id),
        }

    def show(self, experiment_id: str) -> dict:
        """Verified inspection: fails closed on a broken audit chain or a
        missing/altered committed specification; reconciles a stale
        materialized projection against the verified chain. No bypass flag."""
        self.verify_audit_chain()
        info = self._show_unverified(experiment_id)
        self._verify_spec_immutable(
            experiment_id, info["prereg_sha256"],
            json.dumps(info["prereg"]),
        )
        self._reconcile_projection(experiment_id)
        return info

    def list(self) -> list[dict]:
        """Every experiment, INCLUDING failed/incomplete — always visible.
        Fails closed on a corrupted audit chain."""
        self.verify_audit_chain()
        return [
            {"experiment_id": r[0], "trial_number": r[1], "status": r[2]}
            for r in self._con.execute(
                "SELECT experiment_id, trial_number, status FROM experiments "
                "ORDER BY trial_number"
            ).fetchall()
        ]

    def trial_count(self) -> int:
        self.verify_audit_chain()
        return self._con.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]

    # -- lifecycle ---------------------------------------------------------
    def transition(self, experiment_id: str, new_status: str, note: str = "",
                   outputs: dict | None = None) -> dict:
        self.verify_audit_chain()  # corrupted chain blocks every mutation
        if new_status not in ALL_STATES:
            raise InvalidTransitionError(f"unknown state {new_status!r}")
        if outputs is not None and new_status not in TERMINAL_STATES:
            raise RegistryError("an outputs manifest may only be recorded "
                                "at a terminal transition")
        con = self._con
        row = con.execute(
            "SELECT status, prereg_sha256, prereg_json FROM experiments "
            "WHERE experiment_id=?", [experiment_id]
        ).fetchone()
        if row is None:
            raise RegistryError(f"unknown experiment: {experiment_id}")
        current, stored_sha, stored_json = row
        try:
            if current in TERMINAL_STATES:
                raise InvalidTransitionError(
                    f"{experiment_id}: terminal result {current} can never "
                    "be rewritten"
                )
            if new_status not in VALID_TRANSITIONS[current]:
                raise InvalidTransitionError(
                    f"{experiment_id}: invalid transition "
                    f"{current} -> {new_status}"
                )
            validated_outputs: str | None = None
            if new_status in TERMINAL_STATES:
                if outputs is None:
                    raise RegistryError(
                        f"{experiment_id}: every terminal transition requires "
                        "an EXPLICIT OutputsManifest (§38); synthetic/null "
                        "experiments must pass an explicitly empty manifest "
                        "{'outputs': [], 'note': ...} — omission is never "
                        "treated as empty"
                    )
                from nqresearch.experiments.models import OutputsManifest

                try:
                    validated_outputs = json.dumps(
                        OutputsManifest(**outputs).model_dump()
                    )
                except RegistryError:
                    raise
                except Exception as e:
                    raise RegistryError(
                        f"outputs manifest rejected (§38 structure required): {e}"
                    ) from e
            self._verify_spec_immutable(experiment_id, stored_sha, stored_json)
        except RegistryError as e:
            # The refusal is durably audit-recorded in its OWN transaction so
            # it cannot corrupt or be lost with any caller transaction. The
            # projection is best-effort here (the original refusal takes
            # precedence); any staleness is reconciled on open/inspection.
            con.execute("BEGIN")
            try:
                self._append_audit(experiment_id, "TRANSITION_REFUSED",
                                   current, new_status, str(e))
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
            try:
                self._write_projection(experiment_id)
            except Exception:
                pass  # recoverable materialized view; DB remains authoritative
            raise
        con.execute("BEGIN")
        try:
            con.execute(
                "UPDATE experiments SET status=? WHERE experiment_id=?",
                [new_status, experiment_id],
            )
            if validated_outputs is not None:
                con.execute(
                    "UPDATE experiments SET outputs_json=? WHERE experiment_id=?",
                    [validated_outputs, experiment_id],
                )
            record = self._append_audit(experiment_id, "TRANSITION", current,
                                        new_status, note)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        try:
            self._write_projection(experiment_id)
        except Exception as e:
            # NEVER ambiguous: the transition IS committed; only the
            # materialized projection needs recovery (rebuilt on next
            # open/verified inspection).
            raise ProjectionRecoveryRequiredError(
                f"{experiment_id}: transition {current} -> {new_status} was "
                f"COMMITTED to the authoritative store; the materialized "
                f"projection failed to write ({e}) and will be rebuilt on "
                "the next open or verified inspection"
            ) from e
        return record

    def begin_run(self, experiment_id: str, note: str = "") -> dict:
        return self.transition(experiment_id, STATE_RUNNING, note)
