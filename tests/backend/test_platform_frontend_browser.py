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
            expect(editor.get_by_text("还没有资产", exact=True)).to_be_visible()
            # 问号悬停、焦点及点击只展示说明，不提交表单或切换折叠/勾选。
            help_mutations = []
            page.on(
                "request",
                lambda request: (
                    help_mutations.append(request.url)
                    if request.method in {"POST", "PATCH", "DELETE"}
                    else None
                ),
            )
            target_help = editor.get_by_role("button", name="查看帮助：目标系统", exact=True)
            target_help.hover()
            tooltip = page.get_by_role("tooltip")
            expect(tooltip).to_contain_text("包含其基础地址")
            tooltip.hover()
            expect(tooltip).to_be_visible()
            page.keyboard.press("Escape")
            expect(tooltip).not_to_be_visible()
            target_help.focus()
            expect(tooltip).to_be_visible()
            described_by = target_help.get_attribute("aria-describedby")
            assert (
                described_by
                and page.locator(f"[id='{described_by}']").get_attribute("role") == "tooltip"
            )
            page.keyboard.press("Escape")
            expect(tooltip).not_to_be_visible()
            schema_help = editor.get_by_role(
                "button", name="查看帮助：参数 schema", exact=True
            ).first
            schema_help.click()
            expect(tooltip).to_contain_text("user_id")
            assert not editor.get_by_role(
                "textbox", name="参数 schema（名称 → type/required）", exact=True
            ).is_visible()
            page.locator(".app-header").click()
            expect(tooltip).not_to_be_visible()
            assert not help_mutations

            editor.get_by_role("button", name="新增", exact=True).click()
            editor.get_by_label("名称", exact=True).fill("真实工作台本地回归")
            editor.get_by_label(re.compile("^目标系统")).select_option("workbench-local")
            editor.get_by_role("button", name="添加 HTTP 步骤", exact=True).click()
            step = editor.get_by_role("group", name="步骤 1", exact=True)
            step.get_by_label("稳定 ID", exact=True).fill("check")
            step.get_by_label("步骤名称", exact=True).fill("业务码验证")
            step.get_by_label("URL", exact=True).fill("{{host}}/check")
            confirmation = step.get_by_label("请求契约已确认，可进入真实运行预检", exact=True)
            step.get_by_role("button", name="查看帮助：请求契约确认", exact=True).click()
            expect(page.get_by_role("tooltip")).to_be_visible()
            expect(confirmation).not_to_be_checked()
            page.keyboard.press("Escape")
            step.get_by_label("请求契约已确认，可进入真实运行预检").check()
            editor.get_by_role("button", name="保存草稿", exact=True).click()
            expect(editor.get_by_text("草稿已持久保存；尚未发布。", exact=True)).to_be_visible()
            # 搜索不改变已选资产；放弃切换确认时，未保存输入必须保留。
            expect(editor.locator(".asset-list__item--selected")).to_contain_text(
                "真实工作台本地回归"
            )
            editor.get_by_label("搜索资产", exact=True).fill("no-matching-asset")
            expect(editor.get_by_text("没有匹配的资产", exact=True)).to_be_visible()
            editor.get_by_role("button", name="清空搜索", exact=True).click()
            expect(editor.locator(".asset-list__item")).to_have_count(1)
            if not editor.get_by_label("名称", exact=True).is_visible():
                editor.locator(".scenario-settings > summary").click()
            editor.get_by_label("名称", exact=True).fill("未保存的编辑")
            page.once("dialog", lambda dialog: dialog.dismiss())
            editor.get_by_role("button", name="新增", exact=True).click()
            expect(editor.get_by_label("名称", exact=True)).to_have_value("未保存的编辑")
            # 调试当前未保存内容，且路由离开取消不会丢编辑。
            saved_asset = app.state.asset_service.list("scenarios")[0]
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.locator('.side-nav__menu a[href="/runs"]').click()
            expect(page).to_have_url(base + "/cases")
            expect(editor.get_by_label("名称", exact=True)).to_have_value("未保存的编辑")
            editor.get_by_role("button", name="调试当前整场景", exact=True).click()
            debug = page.get_by_role("region", name="当前草稿调试", exact=True)
            page.once("dialog", lambda dialog: dialog.accept())
            with page.expect_response(re.compile(r"/api/v1/scenarios/debug$")) as debug_response:
                debug.get_by_role("button", name="确认范围并真实调试", exact=True).click()
            assert debug_response.value.status == 202, debug_response.value.text()
            debug_id = debug_response.value.json()["run_id"]
            end = time.monotonic() + 10
            while time.monotonic() < end:
                debug_detail = app.state.run_service.get_run_detail(debug_id)
                if debug_detail.status.value not in {"queued", "running"}:
                    break
                time.sleep(0.05)
            assert debug_detail.status.value == "succeeded", debug_detail.results
            assert not debug_detail.eligible_for_release
            assert debug_detail.payload["debug_snapshot"]["draft"]["name"] == "未保存的编辑"
            assert app.state.asset_service.get("scenarios", saved_asset["id"]) == saved_asset
            assert app.state.asset_service.repository.versions("scenarios", saved_asset["id"]) == []
            debug.get_by_role("button", name="刷新调试结果", exact=True).click()
            expect(debug.get_by_role("status")).to_contain_text(debug_id)
            expect(editor.get_by_label("名称", exact=True)).to_have_value("未保存的编辑")
            editor.get_by_label("名称", exact=True).fill("真实工作台本地回归")
            step.get_by_text("请求选项", exact=False).click()
            expect(step.get_by_role("combobox", name="请求体类型", exact=True)).to_be_visible()
            step.get_by_text("请求选项", exact=False).click()
            expect(step.get_by_role("combobox", name="请求体类型", exact=True)).not_to_be_visible()

            editor.get_by_role("button", name="发布预检", exact=True).click()
            expect(editor.locator("pre").filter(has_text='"valid": true').first).to_be_visible()
            editor.get_by_label("发布说明", exact=True).fill("真实浏览器本地机制验证")
            editor.get_by_role("button", name="发布不可变版本", exact=True).click()
            expect(
                editor.get_by_text("发布版本已冻结，编辑草稿不会改写它。", exact=True)
            ).to_be_visible()
            evidence_dir = os.environ.get("PYTA_BROWSER_EVIDENCE_DIR")
            if evidence_dir:
                Path(evidence_dir).mkdir(parents=True, exist_ok=True)
                page.set_viewport_size({"width": 1440, "height": 1000})
                page.evaluate("window.scrollTo(0, 0)")
                page.screenshot(path=str(Path(evidence_dir) / "1440-cases-selected.png"))
            if evidence_dir:
                page.evaluate("window.scrollTo(0, 0)")
                if not editor.get_by_label("名称", exact=True).is_visible():
                    editor.locator(".scenario-settings > summary").click()
                editor.get_by_role("button", name="查看帮助：优先级", exact=True).hover()
                expect(page.get_by_role("tooltip")).to_contain_text("P0")
                page.screenshot(path=str(Path(evidence_dir) / "1440-help-hover.png"))
                page.keyboard.press("Escape")
            editor.locator(".version-section").get_by_label("被测构建", exact=True).fill(
                "workbench-local-v1"
            )
            editor.get_by_label("已核对计划与测试数据/写入范围").check()
            if not editor.get_by_label("名称", exact=True).is_visible():
                editor.locator(".scenario-settings > summary").click()
            editor.get_by_label("名称", exact=True).fill("正式执行前未保存")
            count_before_cancel = app.state.run_service.repository.list_runs(100, 0).total
            page.once("dialog", lambda dialog: dialog.dismiss())
            editor.get_by_role("button", name="提交运行", exact=True).click()
            expect(editor.get_by_label("名称", exact=True)).to_have_value("正式执行前未保存")
            assert app.state.run_service.repository.list_runs(100, 0).total == count_before_cancel
            editor.get_by_label("名称", exact=True).fill("真实工作台本地回归")
            with page.expect_response(
                re.compile(r"/api/v1/scenarios/[^/]+/versions/1/runs$")
            ) as response:
                editor.get_by_role("button", name="提交运行", exact=True).click()
            result = response.value
            assert result.status == 202, result.text()
            run_id = result.json()["run_id"]
            page.wait_for_url(re.compile("/runs\\?runId="))
            expect(page.get_by_role("heading", name="失败诊断与证据", exact=True)).to_be_visible()
            expect(page.locator(".run-row--selected")).to_contain_text("成功", timeout=15000)
            detail = app.state.run_service.get_run_detail(run_id)
            assert detail.status.value == "succeeded" and detail.transport_mode == "live"
            assert detail.counts["assertions"] == 1 and detail.eligible_for_release
            assert detail.payload["asset_ref"]["version"] == 1
            assert detail.environment_id == "env-demo-mock"
            assert detail.environment_name == "离线演示环境"
            assert detail.payload["build"] == "workbench-local-v1"
            listed = app.state.run_service.list_runs(
                environment_id="env-demo-mock", build="workbench-local-v1"
            )
            assert run_id in [row.run_id for row in listed.items]
            page.goto(base + "/suites")
            suite = page.get_by_test_id("asset-editor-suites")
            suite.get_by_label("名称", exact=True).fill("本地回归套件")
            suite.get_by_role("button", name="添加固定场景版本", exact=True).click()
            suite.get_by_role("combobox", name="场景", exact=True).select_option(
                label="真实工作台本地回归"
            )
            suite.get_by_role("button", name="保存草稿", exact=True).click()
            expect(suite.locator(".asset-list__item--selected")).to_contain_text("本地回归套件")
            suite.get_by_label("发布说明", exact=True).fill("浏览器调度回归")
            suite.get_by_role("button", name="发布不可变版本", exact=True).click()
            expect(
                suite.get_by_text("发布版本已冻结，编辑草稿不会改写它。", exact=True)
            ).to_be_visible()
            suite_id = app.state.asset_service.list("suites")[0]["id"]
            page.goto(base + "/environments")
            environment_row = page.locator(".environment-row").filter(has_text="离线演示环境")
            environment_row.get_by_role("button", name="编辑", exact=True).click()
            variables = page.get_by_role("group", name="环境变量", exact=True)
            variables.get_by_role("combobox", name="编辑方式", exact=True).select_option("json")
            variables.get_by_label("变量 JSON", exact=True).fill(
                '{"count":3,"enabled":true,"nested":{"names":["a","b"]},"empty":null}'
            )
            page.get_by_role("button", name="保存修改", exact=True).click()
            expect(page.get_by_text("环境已保存。", exact=True)).to_be_visible()
            saved_environment = app.state.management_service.get_environment_detail("env-demo-mock")
            assert saved_environment.variables == {
                "count": 3,
                "enabled": True,
                "nested": {"names": ["a", "b"]},
                "empty": None,
            }
            page.get_by_label("环境名称", exact=True).fill("尚未保存环境")
            page.once("dialog", lambda dialog: dialog.dismiss())
            page.get_by_role("button", name="新增环境", exact=True).click()
            expect(page.get_by_label("环境名称", exact=True)).to_have_value("尚未保存环境")
            page.once("dialog", lambda dialog: dialog.accept())
            page.locator('.side-nav__menu a[href="/schedules"]').click()
            page.get_by_label("名称", exact=True).fill("浏览器工作日回归")
            page.get_by_role("combobox", name="发布套件", exact=True).select_option(suite_id)
            page.get_by_role("combobox", name="固定发布版本", exact=True).select_option("1")
            page.get_by_role("combobox", name="运行环境", exact=True).select_option("env-demo-mock")
            page.get_by_role("combobox", name="时间规则", exact=True).select_option("weekdays")
            page.get_by_label("执行时间", exact=True).fill("09:30")
            page.get_by_role("button", name="保存为暂停计划", exact=True).click()
            expect(page.get_by_text("计划已保存并暂停。", exact=True)).to_be_visible()
            plan_row = page.locator(".plans tbody tr").filter(has_text="浏览器工作日回归")
            expect(plan_row).to_contain_text("30 9 * * 1-5")
            plan_row.get_by_role("button", name="预览5次", exact=True).click()
            expect(page.get_by_role("region", name="触发时间预览").locator("time")).to_have_count(5)
            page.get_by_role("button", name="新计划", exact=True).click()
            expect(page.get_by_label("名称", exact=True)).to_have_value("")
            expect(page.get_by_role("combobox", name="发布套件", exact=True)).to_have_value("")
            expect(page.get_by_role("combobox", name="运行环境", exact=True)).to_have_value("")
            # 后来的成功记录不能挤掉失败入口；失败详情展示真实断言差异。
            debug_model = importlib.import_module(
                "pyta_platform_backend.schemas.assets"
            ).DraftDebugRequest
            failed_draft = json.loads(json.dumps(saved_asset["draft"]))
            failed_draft["steps"][0]["assertions"][0]["expected"] = 201
            failed_run = app.state.asset_service.debug(
                debug_model(draft=failed_draft, live_confirmed=True)
            )
            for _ in range(4):
                app.state.asset_service.debug(
                    debug_model(draft=saved_asset["draft"], live_confirmed=True)
                )
            end = time.monotonic() + 10
            while time.monotonic() < end:
                failed_detail = app.state.run_service.get_run_detail(failed_run.run_id)
                if failed_detail.status.value == "failed":
                    break
                time.sleep(0.05)
            assert failed_detail.status.value == "failed"
            page.goto(base + "/dashboard")
            failed_link = page.locator(f'.workbench-grid a[href="/runs?runId={failed_run.run_id}"]')
            expect(failed_link).to_contain_text("草稿调试")
            failed_link.click()
            expect(page.locator(".diagnostics .state-banner--error").first).to_contain_text(
                "首次失败"
            )
            expect(page.locator(".step-evidence").first).to_contain_text("201")
            expect(page.locator(".step-evidence").first).to_contain_text("200")
            # 从现有 JS 布局契约读取视口、路由和测量函数，避免两套门槛漂移。
            layout_module = "./tests/frontend/responsive-layout.mjs"
            layout_config_result = subprocess.run(
                [
                    "node",
                    "--input-type=module",
                    "-e",
                    f"import {{widths,routes,measureLayout}} from '{layout_module}'; "
                    "console.log(JSON.stringify({widths,routes,measure:measureLayout.toString()}))",
                ],
                cwd=root,
                capture_output=True,
                text=True,
                check=True,
            )
            layout_config = json.loads(layout_config_result.stdout)
            layout_checks = []
            for width in layout_config["widths"]:
                page.set_viewport_size({"width": width, "height": 900})
                for route in layout_config["routes"]:
                    page.goto(base + route)
                    expect(page.locator(".side-nav__menu a")).to_have_count(6)
                    if route == "/cases":
                        expect(page.locator(".asset-list__item--selected")).to_contain_text(
                            "真实工作台本地回归"
                        )
                        expect(page.get_by_role("group", name="步骤 1", exact=True)).to_be_visible()
                    if route == "/suites":
                        expect(page.locator(".asset-list__item--selected")).to_contain_text(
                            "本地回归套件"
                        )
                    if route == "/runs":
                        expect(page.locator(".run-row--selected")).to_contain_text(
                            re.compile("成功|调试断言通过")
                        )
                    first_help = page.locator(".help-hint__trigger:visible").first
                    expect(first_help).to_be_visible()
                    first_help.scroll_into_view_if_needed()
                    page.mouse.move(0, 0)
                    first_help.hover()
                    expect(page.get_by_role("tooltip")).to_be_visible()
                    tooltip_box = page.get_by_role("tooltip").bounding_box()
                    assert tooltip_box and tooltip_box["x"] >= 0 and tooltip_box["y"] >= 0
                    assert tooltip_box["x"] + tooltip_box["width"] <= width
                    assert tooltip_box["y"] + tooltip_box["height"] <= 900
                    page.keyboard.press("Escape")
                    evidence_dir = os.environ.get("PYTA_BROWSER_EVIDENCE_DIR")
                    if evidence_dir and width in {390, 980, 1440}:
                        image_path = Path(evidence_dir) / f"{width}-{route[1:]}-default.png"
                        image_path.parent.mkdir(parents=True, exist_ok=True)
                        page.evaluate("window.scrollTo(0, 0)")
                        page.screenshot(path=str(image_path))
                    layout_checks.append(
                        {
                            "label": f"{width} {route} default",
                            "metrics": page.evaluate(layout_config["measure"]),
                        }
                    )
                    for summary in page.locator("details:not([open]) > summary").all():
                        if summary.is_visible():
                            summary.click()
                    layout_checks.append(
                        {
                            "label": f"{width} {route} expanded",
                            "metrics": page.evaluate(layout_config["measure"]),
                        }
                    )
                    evidence_dir = os.environ.get("PYTA_BROWSER_EVIDENCE_DIR")
                    if evidence_dir and width in {390, 980, 1440}:
                        image_path = Path(evidence_dir) / f"{width}-{route[1:]}.png"
                        image_path.parent.mkdir(parents=True, exist_ok=True)
                        page.evaluate("window.scrollTo(0, 0)")
                        page.screenshot(path=str(image_path))
            layout_validation = subprocess.run(
                [
                    "node",
                    "--input-type=module",
                    "-e",
                    f"import {{assertLayout}} from '{layout_module}'; "
                    "let data=''; for await (const part of process.stdin) data+=part; "
                    "for (const entry of JSON.parse(data)) "
                    "assertLayout(entry.metrics,entry.label);",
                ],
                cwd=root,
                input=json.dumps(layout_checks),
                capture_output=True,
                text=True,
            )
            assert layout_validation.returncode == 0, layout_validation.stderr
            touch_context = browser.new_context(
                viewport={"width": 390, "height": 844},
                is_mobile=True,
                has_touch=True,
            )
            touch_page = touch_context.new_page()
            touch_page.goto(base + "/cases")
            touch_page.locator(".scenario-settings > summary").click()
            touch_help = touch_page.get_by_role("button", name="查看帮助：优先级", exact=True)
            touch_help.tap()
            expect(touch_page.get_by_role("tooltip")).to_contain_text("P0")
            if evidence_dir:
                touch_page.screenshot(path=str(Path(evidence_dir) / "390-help-tap.png"))
            touch_help.tap()
            expect(touch_page.get_by_role("tooltip")).not_to_be_visible()
            touch_help.tap()
            touch_page.locator(".editor-heading h3").tap()
            expect(touch_page.get_by_role("tooltip")).not_to_be_visible()
            touch_context.close()
            page.set_viewport_size({"width": 1280, "height": 900})
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
                        "layout_checks": len(layout_checks),
                        "help_hover_keyboard_touch": True,
                        "help_does_not_mutate_forms": True,
                        "unsaved_draft_debug": True,
                        "formal_run_preserves_unsaved_on_cancel": True,
                        "typed_environment_variables": True,
                        "schedule_select_preview_reset": True,
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
