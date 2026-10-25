"""确定性协议/质量分栏，固定重复采样；不假装语义规则等同模型质量真值。"""

import io
import wave


def edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def asr_metrics(reference, hypothesis, entities=()):
    if not isinstance(reference, str) or not reference:
        raise ValueError("ASR需要真实人工参考文本，非语音样本不可作golden")
    if not isinstance(hypothesis, str):
        raise ValueError("识别结果必须为文本")

    # 仅去空白，不删除数字/标点/实体来美化错误率。
    def normalize(value):
        return "".join(value.split())

    left, right = normalize(reference), normalize(hypothesis)
    if not left:
        raise ValueError("ASR参考不能为空白")
    return {
        "normalization_version": "whitespace-only@1",
        "character_error_rate": edit_distance(left, right) / len(left),
        "entity_accuracy": sum(entity in hypothesis for entity in entities) / len(entities)
        if entities
        else None,
    }


def tts_metrics(content):
    if not content:
        return {"valid": False, "reason": "empty_audio"}
    try:
        with wave.open(io.BytesIO(content), "rb") as audio:
            duration = audio.getnframes() / audio.getframerate()
            return {
                "valid": duration > 0,
                "format": "wav",
                "duration_seconds": duration,
                "human_listening": "not_reviewed",
            }
    except (wave.Error, EOFError):
        return {"valid": False, "reason": "invalid_or_unsupported_audio_format"}


def quality(sample, output, task, rubric=None):
    rubric = rubric or {}
    thresholds = rubric.get(
        "thresholds",
        {
            "minimum_concept_coverage": 1,
            "require_forbidden_constraint": True,
            "require_structure_complete": True,
        },
    )
    text = output.get("text")
    dimensions = {}
    status = "undetermined"
    if task in {"text", "analysis"}:
        if not isinstance(text, str) or not text.strip():
            return {"status": "failed", "dimensions": {"nonempty": False}, "reason": "empty_output"}
        concepts = sample.get("required_concepts", [])
        dimensions["concept_coverage"] = (
            sum(any(variant in text for variant in group) for group in concepts) / len(concepts)
            if concepts
            else None
        )
        dimensions["forbidden_constraint"] = not any(
            term in text for term in sample.get("forbidden_concepts", [])
        )
        dimensions["structure_complete"] = all(
            key in output for key in sample.get("required_output_keys", [])
        )
        status = (
            "failed"
            if dimensions["concept_coverage"] is not None
            and dimensions["concept_coverage"] < thresholds["minimum_concept_coverage"]
            or thresholds["require_forbidden_constraint"]
            and not dimensions["forbidden_constraint"]
            or thresholds["require_structure_complete"]
            and not dimensions["structure_complete"]
            else "passed"
        )
        return {
            "status": status,
            "dimensions": dimensions,
            "rule_ref": "deterministic-rubric@1",
            "thresholds": thresholds,
            "limitations": "关键词/同义变体规则，不可判定的自由事实仍需人工复核；不是完整幻觉检测",
        }
    if task == "asr":
        return {
            "status": "reported",
            "metrics": asr_metrics(
                sample.get("reference_text"), text, sample.get("known_facts", [])
            ),
        }
    if task in {"tts_format", "audio_integrity"}:
        return {
            "status": "undetermined",
            "reason": "需要真实provider音频与听感复核，本地非语音manifest不证明TTS质量",
        }
    return {"status": "undetermined", "reason": "任务无可核验质量规则"}


def protocol(sample, output):
    expected = sample.get("protocol_expected")
    if not expected:
        return {"status": "not_applicable"}
    actual = output.get("protocol", {})
    mismatch = [key for key, value in expected.items() if actual.get(key) != value]
    if output.get("session_state") not in {"started", "restored", "ended", "reported"}:
        mismatch.append("session_state_unknown")
    return {
        "status": "failed" if mismatch else "passed",
        "mismatches": mismatch,
        "rule_ref": "fixed-object-session@1",
    }


def run_evaluation(worker, task, claimed, redactor):
    """Never replay historical evaluation tasks or call a provider."""
    raise ValueError("evaluation_execution_disabled: 新评估执行已禁用；历史报告仍可读取")
