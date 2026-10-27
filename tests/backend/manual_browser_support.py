"""复用真实工作台浏览器，验收手册正文、图形及新标签页编辑保护。"""

import json
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlsplit

from playwright.sync_api import expect


def check_manual_desktop(context, page, editor, base, root, evidence_dir=None):
    manifest_result = subprocess.run(
        ["node", "tests/frontend/manual-content.mjs", "--json"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert manifest_result.returncode == 0, manifest_result.stdout + manifest_result.stderr
    manifest = json.loads(manifest_result.stdout)
    article_by_id = {article["id"]: article for article in manifest["articles"]}
    original_url = page.url
    name = editor.get_by_label("名称", exact=True)
    original_name = name.input_value()
    writes = []

    def record_write(request):
        if request.method in {"POST", "PATCH", "PUT", "DELETE"}:
            writes.append(request.url)

    context.on("request", record_write)
    manual = None
    errors = []
    try:
        # 悬停链接是鼠标入口；Tab/Enter 才能证明键盘真的可到达。
        trigger = editor.get_by_role("button", name="查看帮助：目标系统", exact=True)
        trigger.hover()
        link = page.locator(".help-tooltip__manual")
        expected = manifest["topicLinks"]["target"]
        target_path = f"/manual/{expected['articleId']}#{expected['sectionId']}"
        expect(link).to_have_attribute("href", target_path)
        expect(link).to_have_attribute("target", "_blank")
        expect(link).to_have_attribute("rel", "noopener")
        trigger.focus()
        page.keyboard.press("Tab")
        expect(link).to_be_focused()
        with context.expect_page() as popup:
            page.keyboard.press("Enter")
        manual = popup.value
        manual.set_viewport_size({"width": 1440, "height": 1000})
        manual.on("pageerror", lambda error: errors.append(str(error)))
        expect(manual).to_have_url(base + target_path)
        heading = manual.locator(f'[id="{expected["sectionId"]}"]')
        expect(heading).to_be_visible()
        expect(page).to_have_url(original_url)
        expect(name).to_have_value(original_name)
        expect(editor.locator(".draft-state")).to_have_text("未保存")
        page.keyboard.press("Escape")
        expect(page.locator(".help-tooltip")).not_to_be_visible()

        def check_fragment():
            expect(manual.locator(".manual-diagram [role='status']")).to_have_count(
                0, timeout=30000
            )
            section_id = unquote(urlsplit(manual.url).fragment)
            if not section_id:
                return
            target = manual.locator(f'[id="{section_id}"]')
            expect(target).to_be_visible()
            # 等待图形引起的高度变化结束后，章节仍位于视口。
            manual.wait_for_function(
                """id => {
                    const target = document.getElementById(id);
                    if (!target) return false;
                    const box = target.getBoundingClientRect();
                    return box.top >= -1 && box.top < innerHeight;
                }""",
                arg=section_id,
            )

        check_fragment()
        manual.reload()
        expect(manual.locator(".manual-article h1")).to_have_text(
            article_by_id[expected["articleId"]]["title"]
        )
        check_fragment()
        next_article = next(
            article for article in manifest["articles"] if article["id"] != expected["articleId"]
        )
        manual.get_by_role("navigation", name="使用手册目录", exact=True).get_by_role(
            "link", name=next_article["title"], exact=True
        ).click()
        expect(manual.locator(".manual-article h1")).to_have_text(next_article["title"])
        manual.go_back()
        expect(manual).to_have_url(base + target_path)
        check_fragment()
        manual.go_forward()
        expect(manual.locator(".manual-article h1")).to_have_text(next_article["title"])

        search = manual.get_by_role("searchbox", name="搜索使用手册", exact=True)
        search.fill("Token")
        result = manual.locator(".manual-search__results a").first
        expect(result).to_be_visible()
        expected_search_url = result.get_attribute("href")
        result.click()
        expect(manual).to_have_url(base + expected_search_url)
        expect(search).to_have_value("")
        check_fragment()
        search.fill("impossible-manual-query-579342")
        expect(manual.locator(".manual-search__results")).to_contain_text("没有找到相关说明")
        search.fill("")

        # 所有已编写文章都实际打开；每张图都必须成为 SVG，不能只核对源码数量。
        rendered_diagrams = 0
        for article in manifest["articles"]:
            manual.goto(base + f"/manual/{article['id']}")
            expect(manual.locator(".manual-article h1")).to_have_text(article["title"])
            expect(manual.locator(".manual-diagram__canvas svg")).to_have_count(
                article["diagrams"], timeout=30000
            )
            expect(manual.locator(".manual-article [role='alert']")).to_have_count(0)
            actual_ids = manual.locator(".manual-body [id]").evaluate_all(
                "elements => elements.map(item => item.id)"
            )
            for item in article["headings"]:
                assert item["id"] in actual_ids, f"{article['id']}#{item['id']}"
            rendered_diagrams += article["diagrams"]
        assert rendered_diagrams == manifest["diagramCount"]

        manual.goto(base + "/manual/no-such-manual-article")
        expect(manual.get_by_role("alert")).to_contain_text("文章地址可能已变更")
        manual.goto(base + f"/manual/{expected['articleId']}#no-such-manual-section")
        expect(manual.get_by_role("alert")).to_contain_text("未找到")

        if evidence_dir:
            directory = Path(evidence_dir)
            directory.mkdir(parents=True, exist_ok=True)
            with_diagram = next(article for article in manifest["articles"] if article["diagrams"])
            manual.goto(base + f"/manual/{with_diagram['id']}")
            expect(manual.locator(".manual-diagram__canvas svg")).to_have_count(
                with_diagram["diagrams"], timeout=30000
            )
            manual.screenshot(animations="disabled", path=str(directory / "1440-manual-overview.png"))
            diagram = manual.locator(".manual-diagram").first
            diagram.scroll_into_view_if_needed()
            diagram.get_by_role("button", name="展开大图", exact=True).click()
            expect(diagram).to_have_class("manual-diagram manual-diagram--expanded")
            diagram.screenshot(animations="disabled", path=str(directory / "1440-manual-diagram.png"))
            diagram.get_by_role("button", name="收起大图", exact=True).click()

        expect(page).to_have_url(original_url)
        expect(name).to_have_value(original_name)
        expect(editor.locator(".draft-state")).to_have_text("未保存")
        assert not writes, writes
        assert not errors, errors
        return {
            "articles": len(manifest["articles"]),
            "topics": manifest["topicCount"],
            "rendered_diagrams": rendered_diagrams,
            "new_tab_keyboard_and_unsaved_preserved": True,
            "search_hash_reload_and_history": True,
            "invalid_article_and_section_explained": True,
            "business_writes": len(writes),
        }
    finally:
        context.remove_listener("request", record_write)
        if manual:
            manual.close()
