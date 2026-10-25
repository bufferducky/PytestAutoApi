"""Offline, read-only SQLite import. Never starts repositories, workers or schedulers."""

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import JSON, and_, inspect, select, text

from pyta_platform_backend.config import BackendSettings
from pyta_platform_backend.db.schema import metadata
from pyta_platform_backend.db.store import engine_for


class MigrationError(ValueError):
    def __init__(self, report):
        super().__init__("Migration refused; inspect the reconciliation report")
        self.report = report


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def snapshot(source):
    """Backup API includes committed WAL content without writing the source database."""
    path = Path(source).resolve(strict=True)
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    copy = sqlite3.connect(":memory:")
    try:
        connection.backup(copy)
    finally:
        connection.close()
    copy.row_factory = sqlite3.Row
    if copy.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        copy.close()
        raise ValueError("Source SQLite integrity check failed")
    return copy


def transform(name, row, root, report):
    row = dict(row)
    if name == "runs":
        execution = row["execution_json"]
        execution["migration"] = {
            "source": "historical_demo",
            "do_not_resume": True,
            "original_status": row["status"],
        }
        execution["eligible_for_release"] = False
    if name in {"schedules", "schedule_triggers", "resource_pool", "resource_records"}:
        doc = row["data_json"]
        doc["migration"] = {
            "source": "historical_demo",
            "do_not_resume": True,
            "original_state": row.get("state", doc.get("status")),
        }
        if name == "schedules":
            doc["status"] = "paused"
        elif name == "schedule_triggers":
            row["state"] = doc["state"] = "migration_suppressed"
        elif row["state"] in {"leased", "acquiring", "acquired", "in_use", "releasing"}:
            row["state"] = doc["state"] = "needs_reconciliation"
    if name == "run_outbox":
        row["state"] = "migration_suppressed"
    if name == "artifact_refs":
        doc = row["data_json"]
        doc["migration"] = {"source": "historical_demo"}
        identifier = row["id"]
        # Never follow symlinks or a legacy document's arbitrary path/identifier.
        if not isinstance(identifier, str) or not re.fullmatch(r"[0-9a-f]{32}", identifier):
            report["errors"].append({"table": name, "issue": "unsafe_artifact_id"})
            return row
        path = root / identifier
        if doc.get("artifact_id", identifier) != identifier or path.is_symlink():
            state = "corrupt"
        elif not path.is_file():
            state = "missing"
        else:
            data = path.read_bytes()
            state = (
                "available"
                if len(data) == doc.get("byte_size")
                and hashlib.sha256(data).hexdigest() == doc.get("sha256")
                else "corrupt"
            )
        report["attachments"][state].append(identifier)
        if state != "available":
            doc["availability"] = state
    return row


def migrate(source, artifact_root, engine, *, apply=False):
    report = {
        "mode": "apply" if apply else "dry-run",
        "tables": {},
        "errors": [],
        "conflicts": [],
        "dangling_references": [],
        "attachments": {"available": [], "missing": [], "corrupt": []},
    }
    rows = {}
    source_manifest = {}
    db = snapshot(source)
    try:
        names = {
            r[0]
            for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not r[0].startswith("sqlite_")
        }
        unknown = names - set(metadata.tables) - {"alembic_version"}
        report["absent_source_tables"] = sorted(set(metadata.tables) - names)
        if unknown:
            report["errors"].append({"unknown_tables": sorted(unknown)})
        for name in sorted(names & set(metadata.tables)):
            table = metadata.tables[name]
            columns = {r[1] for r in db.execute(f'PRAGMA table_info("{name}")')}
            if columns != set(table.c.keys()):
                report["errors"].append(
                    {
                        "table": name,
                        "unknown_columns": sorted(columns - set(table.c.keys())),
                        "missing_columns": sorted(set(table.c.keys()) - columns),
                    }
                )
                continue
            data = []
            for raw in db.execute(f'SELECT * FROM "{name}"'):
                row = dict(raw)
                for column in table.c:
                    if isinstance(column.type, JSON):
                        try:
                            row[column.name] = json.loads(row[column.name])
                            if not isinstance(row[column.name], dict):
                                raise ValueError("Expected JSON object")
                        except (TypeError, ValueError):
                            report["errors"].append({"table": name, "issue": "invalid_json"})
                data.append(row)
            keys = [c.name for c in table.primary_key]
            data.sort(key=lambda r: json.dumps([r[k] for k in keys]))
            source_manifest[name] = digest(data)
            if name in {"migration_ledger", "write_guard"}:
                if name == "migration_ledger" and data:
                    report["errors"].append({"table": name, "issue": "source_already_migrated"})
                continue
            rows[name] = data
            report["tables"][name] = {
                "source_count": len(data),
                "inserted": 0,
                "matched": 0,
                "pk_hash": digest([[r[k] for k in keys] for r in data]),
                "source_rows_hash": source_manifest[name],
            }
    finally:
        db.close()
    report["source_hash"] = digest(source_manifest)
    if report["errors"]:
        raise MigrationError(report)
    for name, data in rows.items():
        rows[name] = [transform(name, row, Path(artifact_root).resolve(), report) for row in data]
    with engine.begin() as conn:
        if not inspect(conn).has_table("alembic_version") or conn.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalars().all() != ["0001_mysql"]:
            report["errors"].append({"issue": "target_requires_alembic_upgrade"})
            raise MigrationError(report)
        if engine.dialect.name == "mysql":
            conn.execute(select(metadata.tables["write_guard"]).with_for_update()).all()
        target = {}
        for name in ("runs", "schedules", "environments"):
            target[name] = [dict(r) for r in conn.execute(select(metadata.tables[name])).mappings()]
        for name, data in rows.items():
            table = metadata.tables[name]
            target[name] = [dict(r) for r in conn.execute(select(table)).mappings()]
            for row in data:
                predicate = and_(*(table.c[c.name] == row[c.name] for c in table.primary_key))
                existing = conn.execute(select(table).where(predicate)).mappings().first()
                if existing is not None:
                    if digest(dict(existing)) != digest(row):
                        report["conflicts"].append(
                            {
                                "table": name,
                                "pk_hash": digest([row[c.name] for c in table.primary_key]),
                            }
                        )
                    else:
                        report["tables"][name]["matched"] += 1
                else:
                    report["tables"][name]["inserted"] += 1
        # Reconcile explicit relational columns against source plus existing target.
        run_ids = {r["run_id"] for r in rows.get("runs", []) + target.get("runs", [])}
        schedule_ids = {r["id"] for r in rows.get("schedules", []) + target.get("schedules", [])}
        environment_ids = {
            r["id"] for r in rows.get("environments", []) + target.get("environments", [])
        }
        for name, data in rows.items():
            for row in data:
                for field, valid in (
                    ("run_id", run_ids),
                    ("schedule_id", schedule_ids),
                    ("environment_id", environment_ids),
                ):
                    if name == "runs" and field == "run_id":
                        continue
                    if row.get(field) and row[field] not in valid:
                        report["dangling_references"].append(
                            {"table": name, "field": field, "reference": row[field]}
                        )
        if report["errors"] or report["conflicts"]:
            raise MigrationError(report)
        ledger = metadata.tables["migration_ledger"]
        ledger_id = report["source_hash"]
        prior = conn.execute(select(ledger).where(ledger.c.id == ledger_id)).mappings().first()
        if prior is not None and prior["source_hash"] != ledger_id:
            report["errors"].append({"issue": "ledger_source_hash_conflict"})
            raise MigrationError(report)
        if apply:
            for name, data in rows.items():
                table = metadata.tables[name]
                for row in data:
                    predicate = and_(*(table.c[c.name] == row[c.name] for c in table.primary_key))
                    if conn.execute(select(table).where(predicate)).first() is None:
                        conn.execute(table.insert().values(**row))
            if prior is None:
                conn.execute(
                    ledger.insert().values(id=ledger_id, source_hash=ledger_id, data_json=report)
                )
    report["applied"] = apply
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--artifact-root", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = migrate(
            args.source,
            args.artifact_root,
            engine_for(BackendSettings.from_env().resolve_database_url()),
            apply=args.apply,
        )
    except MigrationError as exc:
        print(json.dumps(exc.report, ensure_ascii=False, sort_keys=True))
        return 1
    except Exception:
        # Database/driver exceptions may contain credentials or raw historical payloads.
        print(json.dumps({"errors": ["Migration failed; inspect configuration/source securely"]}))
        return 1
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
