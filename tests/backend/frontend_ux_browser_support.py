"""Element Plus 工作区的真实操作回归，使用隔离本地测试资产。"""

import copy
import json
from pathlib import Path

from playwright.sync_api import expect


def check_ux_workspace(page, app, base, saved_asset, evidence_dir=None):
    # 三份资产各有三步，验证目录和隐藏编辑区；业务调用仍只指向本地 /check。
    assets = []
    for number in range(1, 4):
        draft = copy.deepcopy(saved_asset["draft"])
        draft["name"] = f"体验验收场景 {number}"
        draft["steps"] = []
        for step_number in range(1, 4):
            step = copy.deepcopy(saved_asset["draft"]["steps"][0])
            step.update(step_id=f"step_{step_number}", name=f"请求 {step_number}", depends_on=[])
            step["request"]["body_type"] = "none"
            step["request"]["body"] = None
            step["request"]["headers"] = {"X-Public-Example": "kept"}
            step["metadata"]["custom_editor_evidence"] = {"preserve": True}
            draft["steps"].append(step)
        assets.append(app.state.asset_service.create("scenarios", draft))

    page.goto(base + "/cases?assetId=" + assets[0]["id"])
    editor = page.get_by_test_id("asset-editor-scenarios")
    expect(editor.locator(".asset-list__item--selected")).to_contain_text("体验验收场景 1")
    for asset in assets:
        editor.locator(".asset-list__item").filter(has_text=asset["draft"]["name"]).click()
        expect(editor.locator(".asset-list__item--selected")).to_contain_text(asset["draft"]["name"])
        expect(editor.locator(".step-choice")).to_have_count(3)
        for index in range(3):
            editor.locator(".step-choice").nth(index).click()
            expect(editor.locator(".step-card:visible")).to_have_count(1)
            expect(editor.locator(".step-card:visible").get_by_label("步骤名称", exact=True)).to_have_value(f"请求 {index+1}")

    # 名称搜索不改变选中的编辑缓冲。
    editor.get_by_label("搜索资产", exact=True).fill("体验验收场景 2")
    expect(editor.locator(".asset-list__item")).to_have_count(1)
    expect(editor.locator(".step-card:visible").get_by_label("步骤名称", exact=True)).to_have_value("请求 3")
    editor.get_by_label("搜索资产", exact=True).fill("")
    editor.locator(".step-choice").first.click()
    first = editor.locator(".step-card:visible")
    first.get_by_label("步骤名称", exact=True).fill("未保存步骤名称")
    first.get_by_role("tab", name="请求体", exact=True).click()
    first.get_by_role("combobox", name="请求体类型", exact=True).select_option("json")
    body = first.get_by_role("textbox", name="请求体（JSON/表单填写 JSON，原始文本直接填写）", exact=True)
    body.fill("invalid-json")
    editor.locator(".step-choice").nth(2).click()
    editor.get_by_role("button", name="保存草稿", exact=True).click()
    # 保存必须检查隐藏步骤，不能只校验当前显示的表单。
    expect(editor.locator(".step-card:visible").get_by_label("步骤名称", exact=True)).to_have_value("未保存步骤名称")
    expect(body).to_be_visible()
    expect(body).to_have_value("invalid-json")
    expect(editor.locator(".state-banner--error").first).to_contain_text("请求体")
    assert app.state.asset_service.get("scenarios", assets[-1]["id"])["revision"] == 1
    body.fill('{"public":true,"count":3}')
    first.get_by_role("button", name="复制步骤", exact=True).click()
    expect(editor.locator(".step-choice")).to_have_count(4)
    copied = editor.locator(".step-card:visible")
    expect(copied.get_by_label("步骤名称", exact=True)).to_have_value("未保存步骤名称 副本")
    copied.get_by_role("button", name="下移", exact=True).click()
    expect(copied.get_by_label("步骤名称", exact=True)).to_have_value("未保存步骤名称 副本")
    copied.get_by_role("button", name="删除步骤", exact=True).click()
    expect(editor.locator(".step-choice")).to_have_count(3)
    editor.locator(".step-choice").first.click()
    expect(editor.locator(".step-card:visible").get_by_label("步骤名称", exact=True)).to_have_value("未保存步骤名称")
    editor.get_by_role("button", name="保存草稿", exact=True).click()
    expect(editor.get_by_text("草稿已持久保存；尚未发布。", exact=True)).to_be_visible()
    persisted = app.state.asset_service.get("scenarios", assets[-1]["id"])
    assert persisted["draft"]["steps"][0]["request"]["body"] == {"public": True, "count": 3}
    assert persisted["draft"]["steps"][0]["request"]["headers"] == {"X-Public-Example": "kept"}
    assert persisted["draft"]["steps"][0]["metadata"]["custom_editor_evidence"] == {"preserve": True}

    # 数据和请求不变时切换库标签不应产生保存请求；主要工具栏与地址位于首屏。
    page.evaluate("window.scrollTo(0,0)")
    for name in ["保存草稿", "调试当前整场景"]:
        box = editor.get_by_role("button", name=name, exact=True).bounding_box()
        assert box and 0 <= box["y"] < 900
    box = editor.locator(".step-card:visible").get_by_label("URL", exact=True).bounding_box()
    assert box and 0 <= box["y"] < 900
    if evidence_dir:
        directory = Path(evidence_dir)
        directory.mkdir(parents=True, exist_ok=True)
        page.screenshot(animations="disabled", path=str(directory / "1440-workspace-multistep.png"))

    # 单步依赖缺失应在发请求之前阻止，避免隐式执行前置步骤。
    current = editor.locator(".step-card:visible")
    current.get_by_role("tab", name="高级设置", exact=True).click()
    current.get_by_label("依赖（逗号分隔的前置步骤 ID）", exact=True).fill("missing")
    # 完整草稿依赖校验先于单步输入校验，仍必须阻止网络提交。
    writes = []
    page.on("request", lambda request: writes.append(request.url) if request.method == "POST" and request.url.endswith("/scenarios/debug") else None)
    current.get_by_role("button", name="仅调试此步骤", exact=True).click()
    debug = page.get_by_role("region", name="当前草稿调试", exact=True)
    debug.get_by_role("button", name="确认范围并真实调试", exact=True).click()
    expect(debug.get_by_role("alert")).to_contain_text("依赖")
    assert writes == []
    editor.locator(".step-card:visible").get_by_label("依赖（逗号分隔的前置步骤 ID）", exact=True).fill("")

    return {"three_assets_three_steps": True, "search_and_single_visible_step": True,
            "hidden_invalid_json_located": True, "switch_copy_move_delete_preserve_inputs": True,
            "typed_body_headers_and_extensions_roundtrip": True, "primary_actions_first_viewport": True,
            "invalid_dependency_prevents_debug_request": True}


def check_configuration_and_tools(page, app, base, evidence_dir=None):
    page.goto(base + "/environments")
    page.get_by_role("tab", name="目标系统", exact=True).click()
    context = page.locator(".context-panel")
    expect(context.get_by_role("button", name="新增配置", exact=True)).to_be_enabled()
    context.get_by_label("名称", exact=True).fill("体验验收目标")
    context.get_by_role("combobox", name="环境", exact=True).select_option("env-demo-mock")
    context.get_by_label("基础地址", exact=True).fill(base)
    with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/api/v1/targets")) as response:
        context.get_by_role("button", name="保存公开配置", exact=True).click()
    assert response.value.status == 201, response.value.text()
    target = response.value.json()
    expect(context.get_by_text("已保存公开配置；秘密值不会回显。", exact=True)).to_be_visible()
    context.get_by_label("搜索配置", exact=True).fill("体验验收目标")
    expect(context.locator(".profile-library li")).to_have_count(1)
    page.get_by_role("tab", name="身份", exact=True).click()
    expect(context.get_by_role("button", name="新增配置", exact=True)).to_be_enabled()
    context.get_by_label("名称", exact=True).fill("体验验收身份")
    select = context.get_by_role("combobox", name="支持的目标系统", exact=True)
    select.locator('xpath=ancestor::div[contains(@class,"el-select__wrapper")]').click()
    page.get_by_role("option", name="体验验收目标", exact=True).click()
    select.press("Escape")
    with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/api/v1/identity-profiles")) as response:
        context.get_by_role("button", name="保存公开配置", exact=True).click()
    assert response.value.status == 201, response.value.text()
    identity = response.value.json()
    assert identity["target_ids"] == [target["id"]]
    assert identity["username_secret_ref"].startswith("env:PYTA_SECRET_")
    page.get_by_role("tab", name="租户 / 项目绑定", exact=True).click()
    expect(context.get_by_role("button", name="新增配置", exact=True)).to_be_enabled()
    context.get_by_label("名称", exact=True).fill("体验验收项目")
    context.get_by_role("combobox", name="目标系统", exact=True).select_option(target["id"])
    context.get_by_role("combobox", name="身份", exact=True).select_option(identity["id"])
    context.get_by_label("租户 ID", exact=True).fill("test-tenant")
    context.get_by_label("项目 ID", exact=True).fill("test-project")
    with page.expect_response(lambda response: response.request.method == "POST" and response.url.endswith("/api/v1/context-bindings")) as response:
        context.get_by_role("button", name="保存公开配置", exact=True).click()
    assert response.value.status == 201, response.value.text()
    # 切换分类取消后应保留当前输入，并把焦点留在对话框可操作区域。
    expect(context.get_by_text("已保存公开配置；秘密值不会回显。", exact=True)).to_be_visible()
    context.get_by_label("名称", exact=True).fill("未保存项目绑定")
    page.get_by_role("tab", name="目标系统", exact=True).click()
    dialog=page.get_by_role("dialog",name="请确认操作",exact=True)
    expect(dialog).to_be_visible()
    dialog.get_by_role("button",name="取消",exact=True).click()
    expect(dialog).not_to_be_visible()
    expect(context.get_by_label("名称", exact=True)).to_have_value("未保存项目绑定")
    context.get_by_label("名称", exact=True).fill("体验验收项目")
    if evidence_dir:
        page.screenshot(animations="disabled",path=str(Path(evidence_dir)/"1440-context-binding.png"))

    page.goto(base + "/extensions")
    page.get_by_role("tab", name="测试资源与清理配置", exact=True).click()
    resource=page.locator(".resource-panel")
    resource.get_by_label("名称",exact=True).fill("体验验收只读资源")
    resource.get_by_role("combobox",name="策略",exact=True).select_option("read_only")
    resource.get_by_label("资源池 ID（lease/read_only）",exact=True).fill("local-public-pool")
    resource.get_by_label("只读精确对象 ID",exact=True).fill("local-public-object")
    resource.get_by_label("已确认创建/查询/恢复契约",exact=True).check()
    resource.get_by_label("借用后必须恢复原关联",exact=True).uncheck()
    with page.expect_response(lambda response: response.request.method=="POST" and response.url.endswith("/api/v1/fixture-definitions")) as response:
        resource.get_by_role("button",name="保存新版本",exact=True).click()
    assert response.value.status==201,response.value.text()
    expect(resource.get_by_text("已保存不可变定义：",exact=False)).to_be_visible()
    page.get_by_role("tab", name="Web / App 旅程与能力", exact=True).click()
    journey=page.locator(".journeys")
    expect(journey.get_by_role("button",name="刷新能力与风险",exact=True)).to_be_visible()
    journey.get_by_role("button",name="刷新能力与风险",exact=True).click()
    journey.get_by_role("tab",name="旅程编写",exact=True).click()
    expect(journey.get_by_label("旅程名称",exact=True)).to_be_visible()
    page.get_by_role("tab", name="历史评估报告", exact=True).click()
    evaluation=page.locator(".evaluation")
    expect(evaluation.get_by_role("button",name="新建评估（已禁用）",exact=True)).to_be_disabled()
    evaluation.get_by_role("button",name="刷新历史版本",exact=True).click()
    page.get_by_role("tab", name="覆盖与研究账本", exact=True).click()
    page.get_by_role("button",name="刷新覆盖",exact=True).click()
    expect(page.get_by_role("combobox",name="目标端",exact=True)).to_be_visible()
    # 套件按发布版本预览并真实提交到本地 HTTP；这与草稿调试的证据范围不同。
    suite=app.state.asset_service.list("suites")[0]
    page.goto(base+"/suites?assetId="+suite["id"])
    editor=page.get_by_test_id("asset-editor-suites")
    editor.get_by_role("tab",name="正式运行",exact=True).click()
    editor.get_by_label("被测构建",exact=True).fill("local-suite-build")
    editor.get_by_role("button",name="计划预览",exact=True).click()
    editor.get_by_label("已核对计划与测试数据/写入范围",exact=True).check()
    with page.expect_response(lambda response: response.request.method=="POST" and "/api/v1/suites/" in response.url and response.url.endswith("/runs")) as response:
        editor.get_by_role("button",name="提交运行",exact=True).click()
    assert response.value.status==202,response.value.text()
    run_id=response.value.json()["run_id"]
    expect(page).to_have_url(base+"/runs?runId="+run_id)
    expect(page.locator(".run-row--selected")).to_contain_text("成功",timeout=15000)
    run=app.state.run_service.get_run_detail(run_id)
    assert run.status.value=="succeeded" and run.transport_mode=="live"
    assert run.payload["build"]=="local-suite-build"

    page.goto(base+"/schedules")
    page.locator(".plan-library button").first.click()
    page.get_by_role("tab",name="触发与记录",exact=True).click()
    scheduled_writes=[]
    def watch_schedule(request):
        if request.method=="POST" and "/api/v1/schedules/" in request.url:
            scheduled_writes.append(request.url)
    page.on("request",watch_schedule)
    page.get_by_role("button",name="启用",exact=True).click()
    dialog=page.get_by_role("dialog",name="请确认操作",exact=True)
    expect(dialog).to_be_visible()
    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()
    assert scheduled_writes==[]
    page.get_by_role("button",name="删除计划",exact=True).click()
    dialog.get_by_role("button",name="取消",exact=True).click()
    assert len(page.request.get(base+"/api/v1/schedule-plans").json())==1
    page.remove_listener("request",watch_schedule)
    return {"target_identity_binding_created":True,"multiple_select_secret_refs_preserved":True,
            "cancel_category_change_preserves_input":True,"readonly_resource_definition_saved":True,
            "all_four_tools_operable":True,"new_evaluation_remains_disabled":True,"published_suite_plan_and_live_run":True,"schedule_confirm_cancel_escape_no_mutation":True}


def check_ux_tab_layouts(page, base, widths, measure, evidence_dir=None):
    """检查真正打开的新标签页，不能用隐藏配置的几何边界冒充验收。"""
    checks=[]
    groups={"cases":["编辑与调试","场景设置","发布与版本","正式运行","接入与高级"],
            "suites":["场景编排","套件设置","发布与版本","正式运行"],
            "environments":["环境","目标系统","身份","租户 / 项目绑定"],
            "runs":["概览","步骤证据","资源"],
            "schedules":["计划配置","触发与记录","调度运维与摘要"],
            "extensions":["覆盖与研究账本","测试资源与清理配置","Web / App 旅程与能力","历史评估报告"]}
    for width in widths:
        page.set_viewport_size({"width":width,"height":900})
        for route,tabs in groups.items():
            page.goto(base+'/'+route)
            for index,label in enumerate(tabs):
                tab=page.get_by_role('tab',name=label,exact=True)
                expect(tab).to_be_visible()
                tab.click()
                expect(tab).to_have_attribute('aria-selected','true')
                for summary in page.locator('details > summary').all():
                    if summary.is_visible() and not summary.evaluate('element => element.parentElement.open'):
                        summary.click()
                page.evaluate('window.scrollTo(0,0)')
                checks.append({'label':f'{width} {route} {label}','metrics':page.evaluate(measure)})
                if evidence_dir and width==1280 and index==len(tabs)-1:
                    page.screenshot(animations='disabled',path=str(Path(evidence_dir)/f'1280-{route}-last-tab.png'))
            if route=='cases':
                page.get_by_role('tab',name='编辑与调试',exact=True).click()
                for label in ['参数','请求头','请求体','断言','变量提取','高级设置']:
                    page.locator('.step-card:visible').get_by_role('tab',name=label,exact=True).click()
                    checks.append({'label':f'{width} request {label}','metrics':page.evaluate(measure)})
            if route=='extensions':
                for tool,labels in [('测试资源与清理配置',['定义版本','资源池','媒体数据']),('Web / App 旅程与能力',['能力与风险','旅程编写','旅程版本','设备配置'])]:
                    page.get_by_role('tab',name=tool,exact=True).click()
                    for label in labels:
                        page.get_by_role('tab',name=label,exact=True).click()
                        checks.append({'label':f'{width} tool {label}','metrics':page.evaluate(measure)})
    return checks
