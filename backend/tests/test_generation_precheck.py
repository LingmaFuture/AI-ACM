import copy

from app import tasks
from app.schemas import ProblemDraftV1
from app.seed_data import KNN_DRAFT


def test_precheck_calibrates_expected_values_from_safe_execution(monkeypatch):
    draft = ProblemDraftV1.model_validate(copy.deepcopy(KNN_DRAFT))
    cases = draft.public_cases + draft.hidden_cases
    actual_values = [[index] for index in range(len(cases))]
    responses = [
        {
            "status": "wrong_answer",
            "passed": 0,
            "total": len(cases),
            "cases": [
                {
                    "name": case.name,
                    "passed": False,
                    "message": "结果与期望不一致",
                    "actual": actual,
                }
                for case, actual in zip(cases, actual_values, strict=True)
            ],
        },
        {"status": "accepted", "passed": len(cases), "total": len(cases), "cases": []},
        *[
            {"status": "wrong_answer", "passed": 0, "total": len(cases), "cases": []}
            for _ in draft.mutants
        ],
    ]
    calls = []

    def fake_run(payload):
        calls.append(payload)
        return responses.pop(0)

    monkeypatch.setattr(tasks.judge_executor, "run", fake_run)

    assert tasks._generated_reference_error(draft) is None
    assert [case.expected for case in cases] == actual_values
    assert len(calls) == 2 + len(draft.mutants)
    assert calls[1]["tests"][0]["expected"] == actual_values[0]


def test_precheck_does_not_calibrate_runtime_errors(monkeypatch):
    draft = ProblemDraftV1.model_validate(copy.deepcopy(KNN_DRAFT))
    original = draft.public_cases[0].expected
    monkeypatch.setattr(
        tasks.judge_executor,
        "run",
        lambda _payload: {
            "status": "wrong_answer",
            "passed": 0,
            "total": len(draft.public_cases + draft.hidden_cases),
            "cases": [
                {
                    "name": draft.public_cases[0].name,
                    "passed": False,
                    "message": "NameError: name 'bad_name' is not defined",
                    "actual": None,
                }
            ],
        },
    )

    error = tasks._generated_reference_error(draft)

    assert "NameError" in error
    assert draft.public_cases[0].expected == original


def test_precheck_rejects_uncaught_mutants(monkeypatch):
    draft = ProblemDraftV1.model_validate(copy.deepcopy(KNN_DRAFT))
    cases = draft.public_cases + draft.hidden_cases
    responses = [
        {"status": "accepted", "passed": len(cases), "total": len(cases), "cases": []},
        {"status": "accepted", "passed": len(cases), "total": len(cases), "cases": []},
        *[
            {"status": "wrong_answer", "passed": 0, "total": len(cases), "cases": []}
            for _ in draft.mutants[1:]
        ],
    ]
    monkeypatch.setattr(tasks.judge_executor, "run", lambda _payload: responses.pop(0))

    error = tasks._generated_reference_error(draft)

    assert "错误实现 1" in error
    assert "未被任何测试拦截" in error
