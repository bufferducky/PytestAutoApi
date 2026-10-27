"""Exercise the public verifier against a local HTTP boundary, never the deployed site."""

import base64
import hashlib
import importlib.util
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "deploy" / "scripts" / "verify_public.py"
SPEC = importlib.util.spec_from_file_location("public_verify", SCRIPT)
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)
PUBLIC_URL = "https://test.ysspace2099.com"
USERNAME = "verify-user-sentinel"
PASSWORD = "verify-password-sentinel-$secret"


@pytest.fixture
def bundle(tmp_path):
    assets = {"/assets/app.js": b"console.log('release');", "/assets/app.css": b"body{margin:0}"}
    frontend = b"local frontend archive bytes"
    (tmp_path / "frontend.tar.gz").write_bytes(frontend)
    manifest = {
        "schema_version": 1,
        "tag": "release-test",
        "commit": "f" * 40,
        "archives": {
            "source.tar.gz": "0" * 64,
            "frontend.tar.gz": hashlib.sha256(frontend).hexdigest(),
        },
        "assets": {path: hashlib.sha256(body).hexdigest() for path, body in assets.items()},
    }
    # Extra whitespace proves the receipt binds original file bytes, not reserialized JSON.
    (tmp_path / "manifest.json").write_text(json.dumps(manifest, indent=3) + "\n\n")
    credentials = tmp_path / "credentials.json"
    credentials.write_text(json.dumps({"username": USERNAME, "password": PASSWORD}))
    return tmp_path, assets, credentials


@pytest.fixture
def local_site(bundle):
    _, assets, _ = bundle
    state = {
        "auth_status": 200,
        "anonymous_status": 401,
        "requests": [],
        "index": b'<script type="module" src="/assets/app.js"></script>'
        b'<link rel="stylesheet" href="/assets/app.css">',
        "assets": dict(assets),
        "worker": {"available": True, "last_error": None, "queued": 0},
        "contracts": {"contracts": [{"regression_id": f"S{n:02}"} for n in range(1, 17)]},
    }
    expected = "Basic " + base64.b64encode(f"{USERNAME}:{PASSWORD}".encode()).decode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            authorization = self.headers.get("Authorization")
            state["requests"].append((self.command, self.path, authorization))
            status = 200
            body = b""
            if authorization != expected:
                status = state["anonymous_status"]
            elif state["auth_status"] != 200:
                status = state["auth_status"]
                body = PASSWORD.encode()  # Even a credential-echoing server must not leak.
            elif self.path == "/" or self.path in verifier.ROUTES:
                body = state["index"]
            elif self.path in state["assets"]:
                body = state["assets"][self.path]
            elif self.path == "/redirect":
                status = 302
            else:
                payloads = {
                    "/api/v1/health/live": {"status": "ok"},
                    "/api/v1/worker/status": state["worker"],
                    "/api/v1/regression-packs/yanji": state["contracts"],
                    "/api/v1/runner-capabilities": {"web": {"available": True}},
                }
                if self.path in payloads:
                    body = json.dumps(payloads[self.path]).encode()
                else:
                    status = 404
            self.send_response(status)
            if self.path == "/" or self.path in verifier.ROUTES:
                self.send_header("Content-Type", "text/html; charset=utf-8")
            if status == 401:
                self.send_header("WWW-Authenticate", 'Basic realm="release-test"')
            if self.path == "/redirect":
                self.send_header("Location", "http://127.0.0.1:1/stolen")
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            state["requests"].append((self.command, self.path, None))
            self.send_response(405)
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state["url"] = f"http://127.0.0.1:{server.server_port}"
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def run(bundle, site, **kwargs):
    path, _, credentials = bundle
    report = verifier.verify(
        path,
        PUBLIC_URL,
        credentials,
        client_factory=lambda url, auth: verifier.HTTPClient(site["url"], auth),
        **kwargs,
    )
    receipt = json.loads((path / "verification" / "public.json").read_text())
    assert receipt == report
    return report


def test_success_is_read_only_and_browser_not_run(bundle, local_site, capsys):
    report = run(bundle, local_site)
    assert report["passed"] is True
    assert report["browser_passed"] is False
    assert {"code": "browser_not_run"} in report["warnings"]
    assert report["schema_version"] == 1 and report["tag"] == "release-test"
    assert (
        report["manifest_sha256"]
        == hashlib.sha256((bundle[0] / "manifest.json").read_bytes()).hexdigest()
    )
    assert all(method == "GET" for method, _, _ in local_site["requests"])
    assert all(auth is None for _, _, auth in local_site["requests"][:2])
    assert len(local_site["requests"]) == 9
    output = json.dumps(report) + str(capsys.readouterr())
    assert USERNAME not in output and PASSWORD not in output and "Authorization" not in output


def test_cloudflare_beacon_is_optional_without_ignoring_other_external_assets(bundle, local_site):
    local_site["index"] += (
        b'<script src="https://static.cloudflareinsights.com/beacon.min.js/vce123"></script>'
    )
    assert run(bundle, local_site)["passed"] is True
    cleaned = verifier.without_cloudflare_beacon(local_site["index"])
    assert b"cloudflareinsights" not in cleaned
    assert b"/assets/app.js" in cleaned
    assert not verifier.cloudflare_beacon(
        "https://static.cloudflareinsights.com.evil.invalid/beacon.min.js/vce123"
    )
    local_site["index"] += b'<script src="https://foreign.invalid/assets/app.js"></script>'
    assert run(bundle, local_site)["passed"] is False
    assert b"foreign.invalid" in verifier.without_cloudflare_beacon(local_site["index"])


@pytest.mark.parametrize(
    "auth_status, anonymous_status, code",
    [
        (401, 401, "authenticated_http_failed"),
        (200, 200, "unauthenticated_not_401"),
    ],
)
def test_auth_failure_saves_negative_receipt(
    bundle,
    local_site,
    capsys,
    auth_status,
    anonymous_status,
    code,
):
    local_site.update(auth_status=auth_status, anonymous_status=anonymous_status)
    report = run(bundle, local_site)
    assert report["passed"] is False and report["browser_passed"] is False
    assert report["checks"][-1]["code"] == code
    assert PASSWORD not in json.dumps(report) + str(capsys.readouterr())


@pytest.mark.parametrize(
    "change, code",
    [
        ("extra", "index_assets_mismatch"),
        ("missing", "index_assets_mismatch"),
        ("hash", "asset_hash_mismatch"),
        ("foreign", "invalid_index_asset"),
    ],
)
def test_online_index_and_asset_bytes_must_match(bundle, local_site, change, code):
    if change == "extra":
        local_site["index"] += b'<script src="/assets/old.js"></script>'
    elif change == "missing":
        local_site["index"] = b'<script src="/assets/app.js"></script>'
    elif change == "foreign":
        local_site["index"] += b'<script src="https://foreign.invalid/assets/a.js"></script>'
    else:
        local_site["assets"]["/assets/app.js"] = b"stale release"
    report = run(bundle, local_site)
    assert report["passed"] is False and report["checks"][-1]["code"] == code


@pytest.mark.parametrize(
    "worker",
    [
        {"available": False, "last_error": None, "queued": 0},
        {"available": True, "last_error": PASSWORD, "queued": 0},
        {"available": True, "last_error": None, "queued": 1},
        {"available": True, "queued": 0},
    ],
)
def test_worker_requires_ready_idle_state(bundle, local_site, worker):
    local_site["worker"] = worker
    report = run(bundle, local_site)
    assert report["checks"][-1]["code"] == "worker_not_ready"
    assert PASSWORD not in json.dumps(report)


def test_contract_count_does_not_hide_duplicate_ids(bundle, local_site):
    local_site["contracts"]["contracts"][-1] = {"regression_id": "S01"}
    assert run(bundle, local_site)["checks"][-1]["code"] == "contracts_mismatch"


def test_legacy_credentials_and_opt_in_browser_receipt(bundle, local_site):
    bundle[2].write_text(f"用户名：{USERNAME}\n密码：{PASSWORD}\n", encoding="utf-8")
    called = []

    def browser(url, credentials, checks, warnings):
        called.append((url, credentials))
        checks.append({"name": "browser_layout", "passed": True})
        warnings.append({"code": "extensions_brand_too_tall"})

    report = run(bundle, local_site, browser=True, browser_verifier=browser)
    assert called == [(PUBLIC_URL, (USERNAME, PASSWORD))]
    assert report["browser_passed"] is True and report["passed"] is True
    assert {"code": "browser_not_run"} not in report["warnings"]


def test_browser_exception_is_redacted_and_does_not_pass(bundle, local_site):
    def browser(*args):
        raise RuntimeError(PASSWORD + " Authorization: secret")

    report = run(bundle, local_site, browser=True, browser_verifier=browser)
    assert report["passed"] is False and report["browser_passed"] is False
    assert PASSWORD not in json.dumps(report)


def test_redirect_rejected_before_authenticated_followup(local_site):
    client = verifier.HTTPClient(local_site["url"], (USERNAME, PASSWORD))
    with pytest.raises(verifier.VerificationError, match="unsafe_redirect"):
        client.get("/redirect")
    assert len(local_site["requests"]) == 1
    handler = verifier.SameOriginRedirect()
    with pytest.raises(verifier.VerificationError, match="unsafe_redirect"):
        handler.redirect_request(
            Request(PUBLIC_URL), None, 302, "", {}, "https://user:pass@test.ysspace2099.com/"
        )


@pytest.mark.parametrize(
    "url",
    [
        "http://test.ysspace2099.com",
        "https://user:pass@test.ysspace2099.com",
        "https://test.ysspace2099.com/?password=secret",
    ],
)
def test_unsafe_public_url_never_reaches_network(bundle, url):
    def forbidden(*args):
        pytest.fail("invalid URL reached HTTP client")

    report = verifier.verify(bundle[0], url, bundle[2], client_factory=forbidden)
    assert report["passed"] is False and report["url"] == ""


def test_archive_hash_failure_and_cli_exit_do_not_print_credentials(bundle, capsys):
    (bundle[0] / "frontend.tar.gz").write_bytes(b"changed after pack")
    result = verifier.main(
        ["--bundle", str(bundle[0]), "--url", PUBLIC_URL, "--credentials-file", str(bundle[2])]
    )
    assert result == 1
    report = json.loads((bundle[0] / "verification" / "public.json").read_text())
    assert report["checks"][-1]["code"] == "archive_hash_mismatch"
    assert PASSWORD not in str(capsys.readouterr())


def test_layout_warns_only_for_extension_brand_height():
    metrics = {
        "scroll": 390,
        "viewport": 390,
        "links": 6,
        "body": {"width": 390},
        "brand": {"height": 110},
        "navItem": {"height": 45},
        "title": {"width": 300, "height": 50},
    }
    assert verifier.check_layout(metrics, extension=True) is True
    with pytest.raises(verifier.VerificationError, match="brand_too_tall"):
        verifier.check_layout(metrics)
    metrics["scroll"] = 400
    with pytest.raises(verifier.VerificationError, match="horizontal_overflow"):
        verifier.check_layout(metrics, extension=True)


@pytest.mark.skipif(
    os.environ.get("PYTA_PUBLIC_BROWSER_TESTS") != "1", reason="explicit opt-in for local Chromium"
)
def test_real_browser_checks_all_routes_and_widths_locally(local_site):
    local_site["index"] = b"""<!doctype html><html><head><style>
      .side-nav__brand {height:50px} .side-nav__item {height:30px;display:block}
      .hero-banner__title {font-size:20px;margin:0}
      </style></head><body><main class="app-shell__body">
      <div class="side-nav__brand">Release</div><nav class="side-nav__menu">
      <a class="side-nav__item" href="/dashboard">One</a><a href="/cases">Two</a>
      <a href="/suites">Three</a><a href="/environments">Four</a>
      <a href="/runs">Five</a><a href="/schedules">Six</a></nav>
      <h1 class="hero-banner__title">Release verification</h1></main>
      <script>if(location.pathname==='/extensions')
      document.querySelector('.side-nav__brand').style.height='110px';</script></body></html>"""
    local_site["index"] += (
        b'<script src="https://static.cloudflareinsights.com/beacon.min.js/vce123" '
        b'integrity="sha512-AAAA"></script>'
    )
    checks, warnings = [], []
    verifier.verify_browser(local_site["url"], (USERNAME, PASSWORD), checks, warnings)
    assert len(checks) == 63 and all(check["passed"] for check in checks)
    assert len(warnings) == 9
    assert {row["route"] for row in warnings} == {"/extensions"}
    assert all(method == "GET" for method, _, _ in local_site["requests"])


@pytest.mark.skipif(
    os.environ.get("PYTA_PUBLIC_BROWSER_TESTS") != "1", reason="explicit opt-in for local Chromium"
)
@pytest.mark.parametrize(
    "script",
    [
        "fetch('/business-write', {method:'POST'})",
        "fetch('/redirect')",
    ],
)
def test_real_browser_blocks_writes_and_redirects(local_site, monkeypatch, script):
    local_site["index"] = f"<html><body><script>{script}</script></body></html>".encode()
    monkeypatch.setattr(verifier, "WIDTHS", (390,))
    monkeypatch.setattr(verifier, "ROUTES", ("/dashboard",))
    checks = []
    with pytest.raises(verifier.VerificationError, match="browser_checks_failed"):
        verifier.verify_browser(local_site["url"], (USERNAME, PASSWORD), checks, [])
    assert checks[0]["passed"] is False
    assert all(method == "GET" for method, _, _ in local_site["requests"])
    assert not any(path == "/business-write" for _, path, _ in local_site["requests"])
