#!/usr/bin/env python3
"""Read-only public release verification; credentials and response bodies stay in memory."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

WIDTHS = (320, 390, 768, 960, 980, 1080, 1081, 1280, 1440)
ROUTES = ("/dashboard", "/cases", "/suites", "/environments", "/runs", "/schedules", "/extensions")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
MEASURE_LAYOUT = """() => {
  const rect = selector => {
    const el = document.querySelector(selector);
    if (!el) return null;
    const box = el.getBoundingClientRect();
    return {width: box.width, height: box.height};
  };
  return {
    viewport: document.documentElement.clientWidth,
    scroll: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
    body: rect('.app-shell__body'), brand: rect('.side-nav__brand'),
    navItem: rect('.side-nav__item'), title: rect('.hero-banner__title'),
    links: document.querySelectorAll('.side-nav__menu a').length
  };
}"""


class VerificationError(Exception):
    """Only fixed, non-secret error codes may enter receipts."""


def require(condition, code):
    if not condition:
        raise VerificationError(code)


def origin(url):
    parsed = urlsplit(url)
    return parsed.scheme, parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)


def cloudflare_beacon(url):
    """Cloudflare注入的可选统计脚本不属于发布产物；验证时不请求该外站。"""
    return bool(re.fullmatch(
        r"https://static\.cloudflareinsights\.com/beacon\.min\.js(?:/[A-Za-z0-9]+)?", url
    ))


def without_cloudflare_beacon(body):
    """只在验证浏览器中移除已知统计标签，避免空脚本触发原标签的SRI校验错误。"""
    def replace(match):
        opening = match.group(0).split(">", 1)[0]
        source = re.search(r"\bsrc\s*=\s*(['\"])(.*?)\1", opening, re.I)
        return "" if source and cloudflare_beacon(source.group(2)) else match.group(0)

    return re.sub(
        r"<script\b[^>]*>[\s\S]*?</script\s*>", replace, body.decode("utf-8"), flags=re.I
    ).encode("utf-8")


def public_url(value):
    parsed = urlsplit(value)
    require(
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and parsed.path in ("", "/")
        and not parsed.query
        and not parsed.fragment,
        "invalid_public_url",
    )
    origin(value)  # Validate malformed ports before any authenticated I/O.
    return value.rstrip("/")


def load_credentials(path):
    raw = path.read_text(encoding="utf-8-sig")
    if raw.lstrip().startswith("{"):
        data = json.loads(raw)
    else:
        data = {}
        for label, key in (("用户名", "username"), ("密码", "password")):
            match = re.search(r"^\s*" + label + r"\s*[:：]\s*(.*?)\s*$", raw, re.MULTILINE)
            if match:
                data[key] = match.group(1)
    require(isinstance(data, dict), "invalid_credentials")
    username, password = data.get("username"), data.get("password")
    require(
        isinstance(username, str)
        and isinstance(password, str)
        and bool(username)
        and bool(password)
        and ":" not in username
        and not any(char in username + password for char in "\r\n"),
        "invalid_credentials",
    )
    return username, password


class SameOriginRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parsed = urlsplit(newurl)
        require(
            parsed.username is None
            and parsed.password is None
            and origin(newurl) == origin(request.full_url),
            "unsafe_redirect",
        )
        return super().redirect_request(request, fp, code, msg, headers, newurl)


class HTTPClient:
    """The only stdlib network boundary; fake/local transports can replace it in tests."""

    def __init__(self, base_url, credentials):
        self.base_url = base_url
        token = base64.b64encode(":".join(credentials).encode("utf-8")).decode("ascii")
        self._authorization = "Basic " + token
        self._opener = build_opener(SameOriginRedirect())

    def get(self, path, authenticated=True):
        url = urljoin(self.base_url + "/", path)
        parsed = urlsplit(url)
        require(
            origin(url) == origin(self.base_url)
            and parsed.username is None
            and parsed.password is None,
            "unsafe_request_url",
        )
        headers = {
            "Accept-Encoding": "identity", "Cache-Control": "no-cache",
            "User-Agent": "PytestAutoApi-ReleaseCheck/1.0",
        }
        if authenticated:
            headers["Authorization"] = self._authorization
        request = Request(url, headers=headers, method="GET")
        try:
            with self._opener.open(request, timeout=30) as response:
                return response.status, response.read()
        except HTTPError as exc:
            # Never emit HTTP exception text: it may contain URLs or response secrets.
            with exc:
                return exc.code, b""


class IndexAssets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.references = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "script" and values.get("src"):
            self.references.append(values["src"])
        if tag == "link" and values.get("href"):
            rel = values.get("rel", "").lower().split()
            if any(value in rel for value in ("stylesheet", "modulepreload", "preload")):
                self.references.append(values["href"])


def index_assets(body, base_url):
    parser = IndexAssets()
    parser.feed(body.decode("utf-8"))
    assets = set()
    for reference in parser.references:
        target = urljoin(base_url + "/", reference)
        if cloudflare_beacon(target):
            continue
        parsed = urlsplit(target)
        require(
            origin(target) == origin(base_url)
            and parsed.username is None
            and parsed.password is None
            and not parsed.query
            and not parsed.fragment
            and parsed.path.startswith("/assets/")
            and unquote(parsed.path) == parsed.path
            and ".." not in parsed.path.split("/"),
            "invalid_index_asset",
        )
        assets.add(parsed.path)
    require(bool(assets), "index_assets_missing")
    return assets


def load_manifest(bundle, report):
    raw = (bundle / "manifest.json").read_bytes()
    report["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    manifest = json.loads(raw)
    require(isinstance(manifest, dict) and manifest.get("schema_version") == 1, "invalid_manifest")
    require(
        isinstance(manifest.get("tag"), str)
        and bool(manifest["tag"])
        and isinstance(manifest.get("commit"), str)
        and bool(manifest["commit"]),
        "invalid_release_identity",
    )
    report.update(tag=manifest["tag"], commit=manifest["commit"])
    archives = manifest.get("archives")
    require(isinstance(archives, dict), "invalid_archives")
    for name in ("source.tar.gz", "frontend.tar.gz"):
        require(
            isinstance(archives.get(name), str) and bool(SHA256.fullmatch(archives[name])),
            "invalid_archive_hash",
        )
        path = bundle / name
        # Public verification requires frontend; source may remain on the release host.
        if name == "frontend.tar.gz" or path.exists():
            with path.open("rb") as stream:
                digest = hashlib.sha256()
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            require(digest.hexdigest() == archives[name], "archive_hash_mismatch")
    assets = manifest.get("assets")
    require(isinstance(assets, dict) and bool(assets), "invalid_manifest_assets")
    for path, digest in assets.items():
        require(
            isinstance(path, str)
            and path.startswith("/assets/")
            and not any(char in path for char in "?#\\")
            and unquote(path) == path
            and ".." not in path.split("/")
            and isinstance(digest, str)
            and bool(SHA256.fullmatch(digest)),
            "invalid_manifest_assets",
        )
    return manifest


def get_json(client, path):
    status, body = client.get(path)
    require(status == 200, "authenticated_http_failed")
    value = json.loads(body)
    require(isinstance(value, dict), "invalid_api_response")
    return value


def verify_http(client, manifest, base_url, checks):
    # Check both the SPA and API boundary; a protected home alone does not protect data.
    for path in ("/", "/api/v1/health/live"):
        status, _ = client.get(path, authenticated=False)
        require(status == 401, "unauthenticated_not_401")
    checks.append({"name": "unauthenticated_401", "passed": True})
    health = get_json(client, "/api/v1/health/live")
    require(health.get("status") == "ok", "health_not_ok")
    checks.append({"name": "authenticated_health", "passed": True})
    worker = get_json(client, "/api/v1/worker/status")
    require(
        worker.get("available") is True
        and "last_error" in worker
        and worker["last_error"] in (None, "")
        and type(worker.get("queued")) is int
        and worker["queued"] == 0,
        "worker_not_ready",
    )
    checks.append({"name": "worker_ready", "passed": True})
    contract = get_json(client, "/api/v1/regression-packs/yanji")
    rows = contract.get("contracts")
    require(
        isinstance(rows, list)
        and len(rows) == 16
        and all(isinstance(row, dict) for row in rows)
        and {row.get("regression_id") for row in rows}
        == {f"S{number:02}" for number in range(1, 17)},
        "contracts_mismatch",
    )
    checks.append({"name": "contracts_16", "passed": True})
    capabilities = get_json(client, "/api/v1/runner-capabilities")
    require(
        isinstance(capabilities.get("web"), dict) and capabilities["web"].get("available") is True,
        "web_runner_unavailable",
    )
    checks.append({"name": "web_runner_available", "passed": True})
    status, body = client.get("/")
    require(status == 200, "index_http_failed")
    discovered = index_assets(body, base_url)
    require(discovered == set(manifest["assets"]), "index_assets_mismatch")
    for path in sorted(discovered):
        status, body = client.get(path)
        require(status == 200, "asset_http_failed")
        require(hashlib.sha256(body).hexdigest() == manifest["assets"][path], "asset_hash_mismatch")
    checks.append({"name": "static_assets", "passed": True, "count": len(discovered)})


def check_layout(metrics, extension=False):
    require(metrics["scroll"] <= metrics["viewport"] + 1, "horizontal_overflow")
    require(
        metrics["links"] == 6 and metrics["body"] and metrics["brand"] and metrics["navItem"],
        "layout_elements_missing",
    )
    tall_brand = metrics["brand"]["height"] >= 100
    require(extension or not tall_brand, "brand_too_tall")
    require(metrics["navItem"]["height"] < 120, "navigation_too_tall")
    title = metrics["title"]
    if title:
        require(
            title["width"] >= min(240, metrics["body"]["width"] - 80) and title["height"] < 250,
            "title_layout_failed",
        )
    return tall_brand


def verify_browser(base_url, credentials, checks, warnings):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as runtime:
        browser = runtime.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                http_credentials={
                    "username": credentials[0],
                    "password": credentials[1],
                    "origin": base_url,
                },
                # route.fetch代发请求时显式携带Basic认证，避免每个API反复触发401挑战。
                # 下方guard先拒绝跨源/重定向，认证只会发往本站。
                extra_http_headers={
                    "Authorization": "Basic " + base64.b64encode(
                        ":".join(credentials).encode("utf-8")
                    ).decode("ascii"),
                },
                service_workers="block",
            )
            failures = set()

            def guard(route):
                request = route.request
                parsed = urlsplit(request.url)
                if request.method == "GET" and cloudflare_beacon(request.url):
                    # 不向统计站点发送认证或流量，也不让被禁用统计误报业务页面故障。
                    route.fulfill(status=200, content_type="application/javascript", body="")
                    return
                # Abort all writes and foreign origins before the browser can send them.
                if (
                    request.method != "GET"
                    or origin(request.url) != origin(base_url)
                    or parsed.username is not None
                    or parsed.password is not None
                ):
                    failures.add("browser_request_blocked")
                    route.abort()
                else:
                    # Playwright only routes the first request in a redirect chain.
                    # Fetch without following redirects, so a later Location cannot
                    # bypass our origin/method guard or carry credentials elsewhere.
                    try:
                        response = route.fetch(max_redirects=0, timeout=30000)
                        if 300 <= response.status < 400:
                            failures.add("browser_redirect_blocked")
                            route.abort()
                        else:
                            if "text/html" in response.headers.get("content-type", ""):
                                route.fulfill(
                                    response=response,
                                    body=without_cloudflare_beacon(response.body()),
                                )
                            else:
                                route.fulfill(response=response)
                        response.dispose()
                    except Exception:
                        failures.add("browser_request_failed")
                        route.abort()

            context.route("**/*", guard)
            page = context.new_page()
            page.on("pageerror", lambda error: failures.add("browser_js_error"))
            page.on(
                "console",
                lambda msg: failures.add("browser_console_error") if msg.type == "error" else None,
            )
            page.on("requestfailed", lambda request: failures.add("browser_request_failed"))

            def response_check(response):
                if response.status >= 400:
                    failures.add("browser_http_failed")

            page.on("response", response_check)
            for width in WIDTHS:
                page.set_viewport_size({"width": width, "height": 900})
                for route in ROUTES:
                    label = {"route": route, "width": width}
                    print(f"Browser check: {route} {width}px", flush=True)
                    try:
                        response = page.goto(base_url + route, wait_until="networkidle")
                        require(
                            response is not None and response.status == 200,
                            "browser_navigation_failed",
                        )
                        require(urlsplit(page.url).path == route, "browser_route_mismatch")
                        page.locator(".side-nav__menu a").first.wait_for(state="visible")
                        for expanded in (False, True):
                            if expanded:
                                for summary in page.locator("details:not([open]) > summary").all():
                                    if summary.is_visible():
                                        summary.click()
                            metrics = page.evaluate(MEASURE_LAYOUT)
                            if check_layout(metrics, extension=route == "/extensions"):
                                warning = {"code": "extensions_brand_too_tall", **label}
                                if warning not in warnings:
                                    warnings.append(warning)
                        require(not failures, sorted(failures)[0] if failures else "browser_failed")
                        checks.append({"name": "browser_layout", "passed": True, **label})
                    except Exception as exc:
                        code = str(exc) if isinstance(exc, VerificationError) else "browser_failed"
                        checks.append(
                            {"name": "browser_layout", "passed": False, "code": code, **label}
                        )
            context.close()
        finally:
            browser.close()
    require(not any(check["passed"] is False for check in checks), "browser_checks_failed")


def verify(
    bundle,
    url,
    credentials_file,
    browser=False,
    *,
    client_factory=HTTPClient,
    browser_verifier=verify_browser,
):
    """Always write a receipt, including configuration, network and browser failures."""
    bundle = Path(bundle)
    report = {
        "schema_version": 1,
        "tag": None,
        "commit": None,
        "manifest_sha256": None,
        "url": "",
        "passed": False,
        "browser_passed": False,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": [],
        "warnings": [],
    }
    try:
        base_url = public_url(url)
        report["url"] = base_url
        manifest = load_manifest(bundle, report)
        report["checks"].append({"name": "bundle", "passed": True})
        credentials = load_credentials(Path(credentials_file))
        client = client_factory(base_url, credentials)
        verify_http(client, manifest, base_url, report["checks"])
        if browser:
            browser_verifier(base_url, credentials, report["checks"], report["warnings"])
            report["browser_passed"] = True
        else:
            report["warnings"].append({"code": "browser_not_run"})
        report["passed"] = True
    except Exception as exc:
        # Whitelist our own codes; never persist a third-party exception or traceback.
        code = str(exc) if isinstance(exc, VerificationError) else "verification_failed"
        report["checks"].append({"name": "verification", "passed": False, "code": code})
    receipt = bundle / "verification" / "public.json"
    receipt.parent.mkdir(parents=True, exist_ok=True)
    temporary = receipt.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(receipt)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--credentials-file", type=Path, required=True)
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = verify(args.bundle, args.url, args.credentials_file, args.browser)
    except Exception:
        print("Public verification failed; receipt could not be saved.")
        return 1
    print("Public verification passed." if report["passed"] else "Public verification failed.")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
