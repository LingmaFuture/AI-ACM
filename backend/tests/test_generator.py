import copy

import pytest

from app import generator, tasks
from app.generator import (
    DraftGenerationError,
    _extract_json,
    _normalize_draft_payload,
    generate_draft,
)
from app.runner import execute
from app.schemas import ProblemDraftV1
from app.seed_data import KNN_DRAFT


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": self.content},
                }
            ]
        }


def test_extract_json_accepts_fences_and_surrounding_text():
    assert _extract_json('```json\n{"ok": true}\n```') == {"ok": True}
    assert _extract_json('结果如下：\n{"ok": true}\n请查收') == {"ok": True}


def test_extract_json_rejects_empty_content_with_clear_error():
    with pytest.raises(ValueError, match="空内容"):
        _extract_json("  ")


def test_normalize_minimax_style_payload():
    payload = copy.deepcopy(KNN_DRAFT)
    function_spec = payload.pop("function_spec")
    payload["slug"] = payload.pop("slug_hint")
    payload["constraints"] = {"k": "1 <= k <= n_train", "n_train": "1..200"}
    payload["function_spec"] = {
        "name": function_spec["method_name"],
        "returns": {"type": "np.ndarray"},
    }
    argument_names = [item["name"] for item in function_spec["args"]]
    for collection in ("public_cases", "hidden_cases"):
        payload[collection] = [
            {
                "inputs": [case["args"][name] for name in argument_names],
                "output": case["expected"],
            }
            for case in payload[collection]
        ]
    payload["checker"] = {"type": "exact_match", "params": {}}
    payload["mutants"] = [
        {"name": f"错误实现 {index}", "code": code}
        for index, code in enumerate(payload["mutants"], start=1)
    ]
    payload["resource_limits"] = {"time_limit_ms": 2000, "memory_limit_mb": 256}

    normalized = _normalize_draft_payload(payload)
    ProblemDraftV1.model_validate(normalized)

    assert normalized["slug_hint"] == KNN_DRAFT["slug_hint"]
    assert normalized["constraints"] == ["k: 1 <= k <= n_train", "n_train: 1..200"]
    assert normalized["function_spec"]["method_name"] == function_spec["method_name"]
    assert [item["name"] for item in normalized["function_spec"]["args"]] == argument_names
    assert normalized["public_cases"][0]["args"] == KNN_DRAFT["public_cases"][0]["args"]
    assert normalized["public_cases"][0]["expected"] == KNN_DRAFT["public_cases"][0]["expected"]
    assert normalized["checker"]["kind"] == "exact"
    assert normalized["mutants"] == KNN_DRAFT["mutants"]
    assert normalized["resource_limits"]["timeout_seconds"] == 2


def test_generate_draft_retries_empty_response(monkeypatch):
    payload = copy.deepcopy(KNN_DRAFT)
    responses = [FakeResponse(""), FakeResponse(f"```json\n{generator.json.dumps(payload)}\n```")]
    requests = []

    def fake_post(*args, **kwargs):
        requests.append(kwargs["json"])
        return responses.pop(0)

    monkeypatch.setattr(generator.settings, "ai_api_key", "test-key")
    monkeypatch.setattr(generator.httpx, "post", fake_post)

    draft = generate_draft("KNN 算法资料，包含欧氏距离与多数投票。", "knn.txt")

    assert draft.title == payload["title"]
    assert len(requests) == 2
    assert "上一次输出无法使用" in requests[1]["messages"][-1]["content"]
    assert requests[0]["max_tokens"] == 8192


def test_generate_draft_retries_cases_missing_required_args(monkeypatch):
    invalid = copy.deepcopy(KNN_DRAFT)
    invalid["public_cases"][0]["args"] = {}
    valid = copy.deepcopy(KNN_DRAFT)
    responses = [
        FakeResponse(generator.json.dumps(invalid)),
        FakeResponse(generator.json.dumps(valid)),
    ]
    requests = []

    def fake_post(*args, **kwargs):
        requests.append(kwargs["json"])
        return responses.pop(0)

    monkeypatch.setattr(generator.settings, "ai_api_key", "test-key")
    monkeypatch.setattr(generator.httpx, "post", fake_post)

    draft = generate_draft("KNN 算法资料。", "knn.txt")

    assert draft.title == valid["title"]
    assert len(requests) == 2
    assert "缺少函数参数" in requests[1]["messages"][-1]["content"]


def test_generate_draft_retries_failed_reference_validation(monkeypatch):
    payload = copy.deepcopy(KNN_DRAFT)
    responses = [
        FakeResponse(generator.json.dumps(payload)),
        FakeResponse(generator.json.dumps(payload)),
    ]
    requests = []
    validation_results = ["参考答案未通过隔离执行（0/3）：样例 1 结果错误", None]

    def fake_post(*args, **kwargs):
        requests.append(kwargs["json"])
        return responses.pop(0)

    monkeypatch.setattr(generator.settings, "ai_api_key", "test-key")
    monkeypatch.setattr(generator.httpx, "post", fake_post)

    draft = generate_draft(
        "KNN 算法资料。",
        "knn.txt",
        reference_validator=lambda _draft: validation_results.pop(0),
    )

    assert draft.title == payload["title"]
    assert len(requests) == 2
    assert "参考答案未通过隔离执行" in requests[1]["messages"][-1]["content"]


def test_generate_draft_repairs_uncaught_mutant_with_previous_draft(monkeypatch):
    invalid = copy.deepcopy(KNN_DRAFT)
    invalid["mutants"][1] = invalid["reference_solution"]
    responses = [
        FakeResponse(generator.json.dumps(invalid)),
        FakeResponse(generator.json.dumps(KNN_DRAFT)),
    ]
    requests = []

    def fake_post(*args, **kwargs):
        requests.append(kwargs["json"])
        return responses.pop(0)

    monkeypatch.setattr(generator.settings, "ai_api_key", "test-key")
    monkeypatch.setattr(generator.httpx, "post", fake_post)
    monkeypatch.setattr(tasks.judge_executor, "run", execute)

    draft = generate_draft(
        "KNN 算法资料。", "knn.txt", reference_validator=tasks._generated_reference_error
    )

    assert draft.mutants == KNN_DRAFT["mutants"]
    assert len(requests) == 2
    assert len(requests[0]["messages"]) == 2
    retry_messages = requests[1]["messages"]
    assert retry_messages[-2]["role"] == "assistant"
    previous = generator.json.loads(retry_messages[-2]["content"])
    assert previous["mutants"][1] == invalid["reference_solution"]
    assert previous["hidden_cases"] == invalid["hidden_cases"]
    assert "错误实现 2 未被任何测试拦截" in retry_messages[-1]["content"]


def test_generate_draft_repairs_forbidden_import_with_execution_feedback(monkeypatch):
    invalid = copy.deepcopy(KNN_DRAFT)
    invalid["reference_solution"] = "import math\n" + invalid["reference_solution"]
    responses = [
        FakeResponse(generator.json.dumps(invalid)),
        FakeResponse(generator.json.dumps(KNN_DRAFT)),
    ]
    requests = []

    def fake_post(*args, **kwargs):
        requests.append(kwargs["json"])
        return responses.pop(0)

    monkeypatch.setattr(generator.settings, "ai_api_key", "test-key")
    monkeypatch.setattr(generator.httpx, "post", fake_post)
    monkeypatch.setattr(tasks.judge_executor, "run", execute)

    draft = generate_draft(
        "KNN 算法资料。", "knn.txt", reference_validator=tasks._generated_reference_error
    )

    assert draft.reference_solution == KNN_DRAFT["reference_solution"]
    assert len(requests) == 2
    previous = generator.json.loads(requests[1]["messages"][-2]["content"])
    assert previous["reference_solution"].startswith("import math\n")
    assert "第 1 行不允许导入：import math" in requests[1]["messages"][-1]["content"]
    assert "np.exp" in requests[1]["messages"][-1]["content"]


def test_generate_draft_retains_validated_candidate_when_later_output_is_invalid(monkeypatch):
    payload = copy.deepcopy(KNN_DRAFT)
    responses = [
        FakeResponse(generator.json.dumps(payload)),
        FakeResponse("{}"),
        FakeResponse("{}"),
    ]
    requests = []
    validation_error = "错误实现 2 未被任何测试拦截"

    def fake_post(*args, **kwargs):
        requests.append(kwargs["json"])
        return responses.pop(0)

    def validate(draft):
        # The precheck may calibrate expected values before requesting a repair.
        draft.hidden_cases[0].expected = [99]
        return validation_error

    monkeypatch.setattr(generator.settings, "ai_api_key", "test-key")
    monkeypatch.setattr(generator.httpx, "post", fake_post)

    with pytest.raises(DraftGenerationError) as caught:
        generate_draft("KNN 算法资料。", "knn.txt", reference_validator=validate)

    assert caught.value.draft is not None
    assert caught.value.draft.hidden_cases[0].expected == [99]
    assert caught.value.validation_error == validation_error
    previous = generator.json.loads(requests[1]["messages"][-2]["content"])
    assert previous["hidden_cases"][0]["expected"] == [99]


def test_schema_rejects_string_expected_for_list_return():
    payload = copy.deepcopy(KNN_DRAFT)
    payload["public_cases"][0]["expected"] = "0 1"

    with pytest.raises(ValueError, match="返回类型 list 不一致"):
        ProblemDraftV1.model_validate(payload)


def test_normalize_replaces_clustering_checker_on_numeric_problem():
    payload = copy.deepcopy(KNN_DRAFT)
    payload["title"] = "二维卷积数值计算"
    payload["description"] = "给定矩阵与卷积核，计算卷积和池化后的数值结果。"
    payload["tags"] = ["卷积", "NumPy"]
    payload["checker"] = {"kind": "labels_equivalent"}

    normalized = _normalize_draft_payload(payload)

    assert normalized["checker"]["kind"] == "allclose"


def test_generate_draft_reports_repeated_invalid_output(monkeypatch):
    monkeypatch.setattr(generator.settings, "ai_api_key", "test-key")
    monkeypatch.setattr(
        generator.httpx,
        "post",
        lambda *args, **kwargs: FakeResponse('{"title": "字段不足"}'),
    )

    with pytest.raises(DraftGenerationError, match="连续 3 次") as caught:
        generate_draft("KNN 算法资料，包含欧氏距离与多数投票。", "knn.txt")
    assert caught.value.draft is None
    assert caught.value.validation_error is None
