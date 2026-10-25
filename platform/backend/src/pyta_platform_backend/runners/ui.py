"""成熟工具的薄适配：每run独立session，缺能力明确阻塞。"""

import importlib.util
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from urllib.parse import urlsplit

from pyta_platform_backend.workers.context_transport import ContextError, endpoint, secret_value
from testflow_engine import (
    AssertionResult,
    CaseExecutionResult,
    ExecutionStatus,
    StepExecutionResult,
)


class CapabilityMissing(ContextError):
    category = "device"

    def __init__(self, code):
        super().__init__(code, "device")


class WebSession:
    def __init__(self, version, *, capture_trace=False, capture_video=False):
        from playwright.sync_api import sync_playwright

        self._closed = False
        self._recordings = []
        self._trace = capture_trace
        self._video = capture_video
        self._capture_dir = (
            TemporaryDirectory(prefix="pyta-ui-capture-")
            if capture_trace or capture_video
            else None
        )
        self.runtime = sync_playwright().start()
        self.browser = None
        self.context = None
        try:
            self.browser = self.runtime.chromium.launch(headless=True)
            if self.browser.version != version:
                raise CapabilityMissing("chromium_version_mismatch")
            options = {}
            if capture_video:
                options["record_video_dir"] = self._capture_dir.name
            self.context = self.browser.new_context(**options)
            if capture_trace:
                self.context.tracing.start(screenshots=True, snapshots=True, sources=False)
            self.page = self.context.new_page()
        except BaseException:
            self.close()
            raise

    def locate(self, selector):
        strategy, value = selector["strategy"], selector["value"]
        if strategy == "role":
            return self.page.get_by_role(value, name=selector.get("name"), exact=True)
        if strategy == "label":
            return self.page.get_by_label(value, exact=True)
        if strategy == "testid":
            return self.page.get_by_test_id(value)
        raise ValueError("Web只接受role/label/testid定位")

    def act(self, action, value, base_url):
        timeout = action["timeout_seconds"] * 1000
        if action["action"] == "navigate":
            response = self.page.goto(
                endpoint(base_url, action["path"]), timeout=timeout, wait_until="domcontentloaded"
            )
            current = urlsplit(self.page.url)
            target = urlsplit(base_url)
            if (current.scheme, current.netloc) != (target.scheme, target.netloc):
                raise ValueError("UI跳转超出目标源")
            if response and response.status >= 400:
                raise RuntimeError("page_http_load_failed")
            return
        locator = self.locate(action["selector"])
        if action["action"] == "click":
            locator.click(timeout=timeout)
        elif action["action"] == "fill":
            locator.fill(value or "", timeout=timeout)
        elif action["action"] == "assert_visible":
            locator.wait_for(state="visible", timeout=timeout)
        elif action["action"] == "assert_text":
            from playwright.sync_api import expect

            expect(locator).to_have_text(value, timeout=timeout)
        else:
            raise ValueError("该动作不适用于Web")

    def screenshot(self):
        return self.page.screenshot()

    def close(self):
        if self._closed:
            return
        self._closed = True
        failures = []
        try:
            if self.context:
                if self._trace:
                    try:
                        self.context.tracing.stop(
                            path=str(Path(self._capture_dir.name) / "trace.zip")
                        )
                    except Exception as exc:
                        failures.append(type(exc).__name__)
                try:
                    self.context.close()
                except Exception as exc:
                    failures.append(type(exc).__name__)
            if self._capture_dir:
                for file in Path(self._capture_dir.name).iterdir():
                    if file.suffix in {".zip", ".webm"}:
                        self._recordings.append(
                            (
                                "application/vnd.playwright.trace+zip"
                                if file.suffix == ".zip"
                                else "video/webm",
                                file.read_bytes(),
                            )
                        )
            if self.browser:
                try:
                    self.browser.close()
                except Exception as exc:
                    failures.append(type(exc).__name__)
        finally:
            self.runtime.stop()
            if self._capture_dir:
                self._capture_dir.cleanup()
        if failures:
            raise RuntimeError("browser_capture_or_close_failed")

    def take_artifacts(self):
        recordings, self._recordings = self._recordings, []
        return recordings


class AndroidSession:
    def __init__(self, profile, device):
        from appium import webdriver
        from appium.options.android import UiAutomator2Options

        self.profile, self.device, self.driver = profile, device, None
        options = UiAutomator2Options().load_capabilities(
            {
                "platformName": "Android",
                "appium:automationName": "UiAutomator2",
                "appium:udid": device,
                "appium:platformVersion": profile["platform_version"],
                "appium:appPackage": profile["app_package"],
                "appium:appActivity": profile["app_activity"],
                "appium:noReset": False,
                "appium:newCommandTimeout": 60,
            }
        )
        self.driver = webdriver.Remote(profile["appium_url"], options=options)

    def locate(self, selector):
        from appium.webdriver.common.appiumby import AppiumBy

        strategy = selector["strategy"]
        if strategy == "accessibility_id":
            return self.driver.find_element(AppiumBy.ACCESSIBILITY_ID, selector["value"])
        if strategy == "resource_id":
            return self.driver.find_element(AppiumBy.ID, selector["value"])
        raise ValueError("Android只接受accessibility_id/resource_id")

    def act(self, action, value, base_url):
        if action["action"] == "background":
            self.driver.background_app(float(value or 1))
            return
        if action["action"] == "permission":
            permission = action["permission"]
            if permission != "android.permission.RECORD_AUDIO":
                raise ValueError("仅允许明确录音权限测试")
            subprocess.run(
                [
                    "adb",
                    "-s",
                    self.device,
                    "shell",
                    "pm",
                    "grant" if action["permission_granted"] else "revoke",
                    self.profile["app_package"],
                    permission,
                ],
                check=True,
                capture_output=True,
                timeout=10,
            )
            return
        self.driver.implicitly_wait(action["timeout_seconds"])
        element = self.locate(action["selector"])
        if action["action"] == "click":
            element.click()
        elif action["action"] == "fill":
            element.clear()
            element.send_keys(value or "")
        elif action["action"] == "assert_visible":
            if not element.is_displayed():
                raise AssertionError("element_not_visible")
        elif action["action"] == "assert_text":
            if element.text != value:
                raise AssertionError("element_text_mismatch")
        else:
            raise ValueError("该动作不适用于Android")

    def screenshot(self):
        return self.driver.get_screenshot_as_png()

    def close(self):
        if self.driver:
            self.driver.quit()


def capability(journey, profile=None):
    reasons = []
    runner = journey["runner_type"]
    if not journey.get("contract_confirmed"):
        reasons.append("journey_contract_missing")
    if runner == "web":
        if importlib.util.find_spec("playwright") is None:
            reasons.append("playwright_not_installed")
        if not journey.get("chromium_version"):
            reasons.append("chromium_baseline_missing")
    else:
        if importlib.util.find_spec("appium") is None:
            reasons.append("appium_client_not_installed")
        if shutil.which("adb") is None:
            reasons.append("adb_not_available")
        if profile is None:
            reasons.append("device_profile_missing")
        elif set(journey.get("required_media_capabilities", [])) - set(
            profile["media_capabilities"]
        ):
            reasons.append("device_media_capability_missing")
    return {
        "runner_type": runner,
        "runner_version": "ui-runner@1",
        "available": not reasons,
        "blocked_reasons": reasons,
        "baseline": {
            "chromium_version": journey.get("chromium_version"),
            "device_alias": profile.get("name") if profile else None,
            "app_build_sha256": profile.get("app_build_sha256") if profile else None,
        },
        "network_executed": False,
    }


def device_preflight(profile):
    if shutil.which("adb") is None:
        return {"available": False, "blocked_reasons": ["adb_not_available"]}
    device = secret_value(profile["device_secret_ref"])

    def adb(*args):
        return subprocess.run(
            ["adb", "-s", device, *args], check=True, capture_output=True, text=True, timeout=10
        ).stdout.strip()

    try:
        if adb("get-state") != "device":
            raise ValueError("device_offline")
        if adb("shell", "getprop", "ro.build.version.release") != profile["platform_version"]:
            raise ValueError("android_version_mismatch")
        package = adb("shell", "dumpsys", "package", profile["app_package"])
        if "versionName=" + profile["installed_build_version"] not in package:
            raise ValueError("installed_app_version_mismatch")
        path = (
            adb("shell", "pm", "path", profile["app_package"])
            .splitlines()[0]
            .removeprefix("package:")
        )
        actual_hash = adb("shell", "sha256sum", path).split()[0]
        if actual_hash != profile["app_build_sha256"]:
            raise ValueError("installed_app_hash_mismatch")
        free = int(adb("shell", "df", "-k", "/data").splitlines()[-1].split()[3]) * 1024
        if free < profile["free_space_min_bytes"]:
            raise ValueError("device_storage_low")
        return {
            "available": True,
            "device_alias": profile["name"],
            "app_build_sha256": actual_hash,
            "platform_version": profile["platform_version"],
            "media_capabilities": profile["media_capabilities"],
        }
    except Exception as exc:
        return {
            "available": False,
            "blocked_reasons": [str(exc) if isinstance(exc, ValueError) else type(exc).__name__],
        }


def execute_journey(
    journey,
    session,
    context,
    *,
    stop=None,
    artifact=None,
    deadline=None,
    remember_secret=None,
    on_result=None,
    api_action=None,
):
    results = []
    status = "succeeded"
    cleanup_status = "succeeded"
    deadline = deadline or monotonic() + journey["timeout_seconds"]
    restores = []
    remember_secret = remember_secret or (lambda value: None)
    try:
        for action in journey["actions"]:
            now = datetime.now(timezone.utc)
            case_status = ExecutionStatus.PASSED
            error = None
            kind = None
            if stop and stop():
                status = "cancelled"
                break
            remaining = deadline - monotonic()
            if remaining <= 0:
                status = "timed_out"
                break
            action = {**action, "timeout_seconds": min(action["timeout_seconds"], remaining)}
            api_step = None
            value = None
            try:
                if action["action"] == "permission":
                    restores.append(action)
                if action.get("value_ref"):
                    from pyta_platform_backend.workers.context_transport import resolve_references
                    from testflow_engine._field_path import has_field_path, resolve_field_path

                    if not has_field_path(context, action["value_ref"]):
                        raise ValueError("UI value_ref missing")
                    value = resolve_references(
                        resolve_field_path(context, action["value_ref"]), remember_secret
                    )
                else:
                    value = action.get("value")
                if action["action"] == "api_assert":
                    if api_action is None:
                        raise ValueError("API校验执行器不可用")
                    api_step = api_action(action)
                    case_status = api_step.status
                    if case_status != ExecutionStatus.PASSED:
                        status = "failed" if case_status == ExecutionStatus.FAILED else "error"
                        error = api_step.error or next(
                            (
                                a.message
                                for a in api_step.assertions
                                if a.status != ExecutionStatus.PASSED
                            ),
                            "API业务校验未通过",
                        )
                        kind = "assertion" if status == "failed" else "executor"
                else:
                    session.act(action, value, journey["_base_url"])
                if monotonic() >= deadline:
                    status = "timed_out"
                    raise TimeoutError("journey_total_budget_exhausted")
            except AssertionError as exc:
                case_status = ExecutionStatus.FAILED
                error = str(exc)
                kind = "assertion"
                status = "failed"
            except Exception as exc:
                if monotonic() >= deadline:
                    case_status = ExecutionStatus.TIMED_OUT
                    error = "journey_total_budget_exhausted"
                    kind = "executor"
                    status = "timed_out"
                elif "Timeout" in type(exc).__name__ and action["action"].startswith("assert_"):
                    case_status = ExecutionStatus.FAILED
                    error = "selector_or_business_state_timeout"
                    kind = "assertion"
                    status = "failed"
                else:
                    case_status = ExecutionStatus.ERROR
                    error = type(exc).__name__
                    kind = "device" if journey["runner_type"] == "android" else "executor"
                    status = "timed_out" if monotonic() >= deadline else "error"
            checks = []
            if action["action"].startswith("assert_"):
                checks.append(
                    AssertionResult(
                        name=action["name"],
                        status=case_status,
                        actual=None,
                        expected=value,
                        message=error or "界面断言通过",
                    )
                )
            step = StepExecutionResult(
                name=action["action"],
                status=case_status,
                assertions=checks,
                error=error,
                error_type=kind,
                started_at=now,
                finished_at=datetime.now(timezone.utc),
            )
            if api_step is not None:
                step = api_step
            case = CaseExecutionResult(
                case_id=action["step_id"],
                title=action["name"],
                status=case_status,
                steps=[step],
                error=error,
                metadata={
                    "runner_type": journey["runner_type"],
                    "runner_version": "ui-runner@1",
                    "phase": "verify",
                },
                started_at=now,
                finished_at=step.finished_at,
            )
            results.append(case)
            if on_result:
                on_result(case)
            if error:
                if artifact and journey["synthetic_test_data"]:
                    try:
                        artifact(action["step_id"], session.screenshot())
                    except Exception:
                        pass  # 截图失败不覆盖原错误；结果仍保留主失败。
                break
    finally:
        # 未执行动作同样入结果，不能在取消/超时后从计划中消失。
        try:
            for action in journey["actions"][len(results) :]:
                now = datetime.now(timezone.utc)
                blocked = CaseExecutionResult(
                    case_id=action["step_id"],
                    title=action["name"],
                    status=ExecutionStatus.BLOCKED,
                    error="旅程已停止，动作未执行",
                    steps=[],
                    metadata={
                        "runner_type": journey["runner_type"],
                        "runner_version": "ui-runner@1",
                        "phase": "verify",
                    },
                    started_at=now,
                    finished_at=now,
                )
                results.append(blocked)
                if on_result:
                    on_result(blocked)
        finally:
            # 证据写入失败也必须关闭会话/尝试恢复权限。
            cleanup_status_holder = []
            _close_journey(session, journey, restores, cleanup_status_holder)
            cleanup_status = "cleanup_failed" if cleanup_status_holder else "succeeded"
    if (
        not any(
            action["action"].startswith("assert_") or action["action"] == "api_assert"
            for action in journey["actions"]
        )
        and status == "succeeded"
    ):
        status = "blocked"
    return status, cleanup_status, results


def _close_journey(session, journey, restores, failures):
    for action in reversed(restores):
        if action.get("restore_permission_granted") is None:
            failures.append("cleanup_failed")
            continue
        try:
            session.act(
                {**action, "permission_granted": action["restore_permission_granted"]},
                None,
                journey["_base_url"],
            )
        except Exception:
            failures.append("cleanup_failed")
    try:
        session.close()
    except Exception:
        failures.append("cleanup_failed")
