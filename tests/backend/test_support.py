"""Explicit local configuration for tests that previously relied on product demo seeds."""


def seed_test_environments(app):
    """Create only test configuration, never sample assets, schedules or run results."""
    repository = app.state.management_service._repository
    for identifier, name in [
        ("env-default-live", "默认联调环境"),
        ("env-demo-mock", "离线演示环境"),
    ]:
        if repository.get_environment_by_id(identifier) is None:
            with repository._lock, repository._connection.transaction():
                repository._connection.execute(
                    "INSERT INTO environments (id,name,base_url,auth_mode,status,variables_json) "
                    "VALUES (?,?,?,?,?,?)",
                    (identifier, name, "http://127.0.0.1:1", "none", "online", "{}"),
                )
        target_id = "default-" + identifier
        if not app.state.context_service.repository.exists("targets", target_id):
            app.state.context_service.save(
                "targets",
                {
                    "id": target_id,
                    "name": "local-test",
                    "environment_id": identifier,
                    "base_url": "http://127.0.0.1:1",
                },
                creating=True,
            )
    return app
