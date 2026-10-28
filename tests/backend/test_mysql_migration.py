"""Offline importer safety; SQLite targets here do not prove MySQL compatibility."""

import hashlib
import json
import sqlite3

import pytest
from pyta_platform_backend.db.schema import metadata
from pyta_platform_backend.db.store import engine_for
from pyta_platform_backend.migrate_sqlite import MigrationError, main, migrate
from sqlalchemy import select, text


def setup(tmp_path):
    source = tmp_path / "server-snapshot.sqlite3"
    db = sqlite3.connect(source)
    db.executescript("""
    CREATE TABLE runs(run_id TEXT PRIMARY KEY,suite_id TEXT NOT NULL,environment_id TEXT,
    environment_name TEXT,trigger_source TEXT NOT NULL,requested_by TEXT NOT NULL,
    payload_json TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,started_at TEXT,finished_at TEXT,status_message TEXT,
    execution_json TEXT NOT NULL);
    CREATE TABLE schedules(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,data_json TEXT NOT NULL);
    CREATE TABLE artifact_refs(id TEXT PRIMARY KEY,run_id TEXT,data_json TEXT NOT NULL);
    """)
    db.execute(
        "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "Run-A",
            "suite",
            None,
            None,
            "manual",
            "operator",
            json.dumps({"transport_mode": "mock"}),
            "queued",
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
            None,
            None,
            None,
            json.dumps({"eligible_for_release": True, "counts": {"passed": 1}}),
        ),
    )
    db.execute(
        "INSERT INTO schedules VALUES (?,?,?)",
        ("schedule", 3, json.dumps({"status": "active", "next_fire_at": "2026-01-01"})),
    )
    root = tmp_path / "artifacts"
    root.mkdir()
    for identifier, contents in (("a" * 32, b"evidence"), ("b" * 32, None), ("c" * 32, b"bad")):
        if contents is not None:
            (root / identifier).write_bytes(contents)
        db.execute(
            "INSERT INTO artifact_refs VALUES (?,?,?)",
            (
                identifier,
                "Run-A",
                json.dumps(
                    {
                        "artifact_id": identifier,
                        "sha256": hashlib.sha256(b"evidence").hexdigest(),
                        "byte_size": 8,
                        "availability": "available",
                    }
                ),
            ),
        )
    db.commit()
    db.close()
    engine = engine_for(tmp_path / "target.sqlite3")
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version(version_num TEXT PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version VALUES ('0002_run_numbers')"))
    return source, root, engine


def test_preview_apply_repeat_preserves_history_and_source(tmp_path):
    source, root, engine = setup(tmp_path)
    before = source.read_bytes()
    preview = migrate(source, root, engine)
    with engine.connect() as conn:
        assert conn.execute(select(metadata.tables["runs"])).first() is None
        assert conn.execute(select(metadata.tables["migration_ledger"])).first() is None
    assert preview["attachments"]["missing"] == ["b" * 32]
    assert preview["attachments"]["corrupt"] == ["c" * 32]
    applied = migrate(source, root, engine, apply=True)
    repeat = migrate(source, root, engine, apply=True)
    assert applied["source_hash"] == repeat["source_hash"]
    assert repeat["tables"]["runs"]["matched"] == 1
    assert repeat["tables"]["runs"]["inserted"] == 0
    with engine.connect() as conn:
        run = conn.execute(select(metadata.tables["runs"])).mappings().one()
        assert run["run_id"] == "Run-A" and run["status"] == "queued"
        assert run["payload_json"] == {"transport_mode": "mock"}
        assert run["execution_json"]["migration"]["do_not_resume"] is True
        assert run["execution_json"]["eligible_for_release"] is False
        assert conn.execute(select(metadata.tables["run_outbox"])).first() is None
        assert (
            conn.execute(select(metadata.tables["schedules"]))
            .mappings()
            .one()["data_json"]["status"]
            == "paused"
        )
        assert len(conn.execute(select(metadata.tables["migration_ledger"])).all()) == 1
    assert source.read_bytes() == before


def test_conflict_prevents_all_imports(tmp_path):
    source, root, engine = setup(tmp_path)
    table = metadata.tables["schedules"]
    with engine.begin() as conn:
        conn.execute(
            table.insert().values(id="schedule", revision=99, data_json={"status": "active"})
        )
    with pytest.raises(MigrationError) as error:
        migrate(source, root, engine, apply=True)
    assert error.value.report["conflicts"]
    with engine.connect() as conn:
        assert conn.execute(select(metadata.tables["runs"])).first() is None
        assert conn.execute(select(metadata.tables["artifact_refs"])).first() is None
        assert conn.execute(select(metadata.tables["migration_ledger"])).first() is None


@pytest.mark.parametrize(
    "sql", ["CREATE TABLE forgotten(id TEXT)", "ALTER TABLE runs ADD COLUMN unknown TEXT"]
)
def test_unknown_schema_refused(tmp_path, sql):
    source, root, engine = setup(tmp_path)
    with sqlite3.connect(source) as conn:
        conn.execute(sql)
    with pytest.raises(MigrationError):
        migrate(source, root, engine, apply=True)


def test_unsafe_id_and_symlink(tmp_path):
    source, root, engine = setup(tmp_path)
    outside = tmp_path / "private"
    outside.write_bytes(b"private")
    (root / ("a" * 32)).unlink()
    (root / ("a" * 32)).symlink_to(outside)
    assert migrate(source, root, engine)["attachments"]["corrupt"] == ["a" * 32, "c" * 32]
    with sqlite3.connect(source) as conn:
        conn.execute("UPDATE artifact_refs SET id='../private' WHERE id=?", ("a" * 32,))
    with pytest.raises(MigrationError) as error:
        migrate(source, root, engine, apply=True)
    assert error.value.report["errors"][0]["issue"] == "unsafe_artifact_id"


def test_missing_schema_upgrade_and_dangling_reference(tmp_path):
    source, root, engine = setup(tmp_path)
    with sqlite3.connect(source) as conn:
        conn.execute("UPDATE artifact_refs SET run_id='absent'")
    assert len(migrate(source, root, engine)["dangling_references"]) == 3
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM alembic_version"))
    with pytest.raises(MigrationError):
        migrate(source, root, engine)


def test_cli_existing_documented_flags(monkeypatch, capsys, tmp_path):
    source, root, engine = setup(tmp_path)
    monkeypatch.setitem(main.__globals__, "engine_for", lambda _: engine)
    monkeypatch.setattr(
        main.__globals__["BackendSettings"],
        "resolve_database_url",
        lambda self: "explicit-offline-test-target",
    )
    monkeypatch.setenv("PLATFORM_BACKEND_APP_ENV", "test")
    assert main(["--source", str(source), "--artifact-root", str(root), "--dry-run"]) == 0
    assert json.loads(capsys.readouterr().out)["applied"] is False


def test_trigger_outbox_and_lease_never_resume(tmp_path):
    source, root, engine = setup(tmp_path)
    with sqlite3.connect(source) as conn:
        conn.executescript("""
        CREATE TABLE schedule_triggers(id TEXT PRIMARY KEY,schedule_id TEXT,revision INTEGER,
        planned_at TEXT,state TEXT,data_json TEXT);
        CREATE TABLE run_outbox(run_id TEXT PRIMARY KEY,state TEXT,owner TEXT,attempt INTEGER,
        lease_until TEXT,priority INTEGER,created_at TEXT);
        CREATE TABLE resource_pool(id TEXT PRIMARY KEY,pool_id TEXT,state TEXT,owner TEXT,
        generation INTEGER,expires_at TEXT,data_json TEXT);
        """)
        conn.execute(
            "INSERT INTO schedule_triggers VALUES (?,?,?,?,?,?)",
            ("trigger", "schedule", 3, "2026-01-01", "pending", '{"state":"pending"}'),
        )
        conn.execute(
            "INSERT INTO run_outbox VALUES (?,?,?,?,?,?,?)",
            ("Run-A", "pending", None, 0, None, 0, "2026-01-01"),
        )
        conn.execute(
            "INSERT INTO resource_pool VALUES (?,?,?,?,?,?,?)",
            ("object", "pool", "leased", "Run-A", 2, "2026-01-01", "{}"),
        )
    migrate(source, root, engine, apply=True)
    with engine.connect() as conn:
        for name in ("schedule_triggers", "run_outbox"):
            row = conn.execute(select(metadata.tables[name])).mappings().one()
            assert row["state"] == "migration_suppressed"
        resource = conn.execute(select(metadata.tables["resource_pool"])).mappings().one()
        assert resource["state"] == "needs_reconciliation"
        assert resource["owner"] == "Run-A" and resource["generation"] == 2


def test_mid_insert_error_rolls_back_every_table(tmp_path):
    source, root, engine = setup(tmp_path)
    with engine.begin() as conn:
        conn.execute(
            text("""CREATE TRIGGER refuse_schedule BEFORE INSERT ON schedules
                          BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
        )
    with pytest.raises(Exception, match="injected failure"):
        migrate(source, root, engine, apply=True)
    with engine.connect() as conn:
        assert conn.execute(select(metadata.tables["artifact_refs"])).first() is None
        assert conn.execute(select(metadata.tables["runs"])).first() is None
        assert conn.execute(select(metadata.tables["migration_ledger"])).first() is None
