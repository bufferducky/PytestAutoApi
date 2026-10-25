"""真实工作台表单与API贯通检查；不执行公司业务接口。"""

import importlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path
from threading import Thread

import pytest
from test_support import seed_test_environments

pytestmark = pytest.mark.skipif(
    os.environ.get("PYTA_RUN_BROWSER_TESTS") != "1", reason="显式启用的真实工作台浏览器检查"
)


def test_real_workbench_edit_publish_live_run_and_offline_error(tmp_path):
    import uvicorn
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles
    from playwright.sync_api import expect, sync_playwright

    root = Path(__file__).resolve().parents[2]
    dist = tmp_path / "dist"
    env = {**os.environ, "VITE_API_BASE_URL": "/api/v1"}
    build = subprocess.run(
        ["npm", "run", "build", "--", "--outDir", str(dist), "--emptyOutDir"],
        cwd=root / "platform/frontend",
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert build.returncode == 0, build.stdout + build.stderr
    for name in list(sys.modules):
        if name == "pyta_platform_backend" or name.startswith("pyta_platform_backend."):
            sys.modules.pop(name)
    app = importlib.import_module("pyta_platform_backend.app").create_app(
        settings=importlib.import_module("pyta_platform_backend.config").BackendSettings(
            app_env="test", state_db_path=str(tmp_path / "platform.sqlite3")
        )
    )
    seed_test_environments(app)

    @app.get("/check")
    def local_business_check():
        return {"code": 200}

    app.mount("/assets", StaticFiles(directory=dist / "assets"), name="frontend-assets")

    @app.get("/{frontend_path:path}")
    def frontend(frontend_path: str):
        return FileResponse(dist / "index.html")

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=listener.getsockname()[1], log_level="error")
    )
    base = f"http://127.0.0.1:{listener.getsockname()[1]}"
    app.state.context_service.save(
        "targets",
        {
            "id": "workbench-local",
            "name": "local workbench HTTP",
            "environment_id": "env-demo-mock",
            "base_url": base,
        },
        creating=True,
    )
    thread = Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    try:
        end = time.monotonic() + 5
        while not server.started and time.monotonic() < end:
            time.sleep(0.01)
        assert server.started
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()
            page_errors = []
            page.set_default_timeout(10000)
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(base + "/cases")
            editor = page.get_by_test_id("asset-editor-scenarios")
            expect(editor).to_be_visible()
            editor.get_by_role("button", name="新增", exact=True).click()
            editor.get_by_label("名称", exact=True).fill("真实工作台本地回归")
            editor.get_by_label(re.compile("^目标系统")).select_option("workbench-local")
            editor.get_by_role("button", name="添加 HTTP 步骤", exact=True).click()
            step = editor.get_by_role("group", name="步骤 1", exact=True)
            step.get_by_label("稳定 ID", exact=True).fill("check")
            step.get_by_label("步骤名称", exact=True).fill("业务码验证")
            step.get_by_label("URL", exact=True).fill("{{host}}/check")
            step.get_by_label("请求契约已确认，可进入真实运行预检").check()
            editor.get_by_role("button", name="保存草稿", exact=True).click()
            expect(editor.get_by_text("草稿已持久保存；尚未发布。", exact=True)).to_be_visible()
            editor.get_by_role("button", name="发布预检", exact=True).click()
            expect(editor.locator("pre").first).to_contain_text('"valid": true')
            editor.get_by_label("发布说明", exact=True).fill("真实浏览器本地机制验证")
            editor.get_by_role("button", name="发布不可变版本", exact=True).click()
            expect(
                editor.get_by_text("发布版本已冻结，编辑草稿不会改写它。", exact=True)
            ).to_be_visible()
            with page.expect_response(
                re.compile(r"/api/v1/scenarios/[^/]+/versions/1/runs$")
            ) as response:
                editor.get_by_role("button", name="提交运行", exact=True).click()
            result = response.value
            assert result.status == 202, result.text()
            run_id = result.json()["run_id"]
            page.wait_for_url(re.compile("/runs\\?runId="))
            expect(page.get_by_role("heading", name="失败诊断与证据", exact=True)).to_be_visible()
            expect(page.get_by_text("成功", exact=True).first).to_be_visible()
            detail = app.state.run_service.get_run_detail(run_id)
            assert detail.status.value == "succeeded" and detail.transport_mode == "live"
            assert detail.counts["assertions"] == 1 and detail.eligible_for_release
            assert detail.payload["asset_ref"]["version"] == 1
            # 断开页面API，验证实际DOM出现错误而非自动填入演示数据。
            page.route("**/api/v1/**", lambda route: route.abort())
            page.reload()
            expect(page.locator(".state-banner--error").first).to_be_visible()
            expect(page.get_by_text("run-203", exact=False)).to_have_count(0)
            assert not page_errors, page_errors
            print(
                json.dumps(
                    {
                        "scope": "真实平台前端+本地API，未调用公司业务",
                        "created_published_run": True,
                        "live_http_evidence": True,
                        "offline_error_visible": True,
                        "page_errors": page_errors,
                    },
                    ensure_ascii=False,
                )
            )
            context.close()
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        listener.close()
