from app.runner import check_result, execute

SPEC = {
    "class_name": "Solution",
    "method_name": "double",
    "args": [{"name": "values", "type": "ndarray"}],
    "return_type": "list",
}


def test_runner_accepts_numpy_solution():
    result = execute(
        {
            "code": "class Solution:\n    def double(self, values):\n        return (values * 2).tolist()",
            "function_spec": SPEC,
            "tests": [{"name": "sample", "args": {"values": [1, 3]}, "expected": [2, 6]}],
            "checker": {"kind": "exact"},
            "resource_limits": {"timeout_seconds": 1, "output_kb": 8},
        }
    )
    assert result["status"] == "accepted"


def test_runner_rejects_imports():
    result = execute(
        {
            "code": "import os\nclass Solution:\n    def double(self, values):\n        return values",
            "function_spec": SPEC,
            "tests": [{"name": "sample", "args": {"values": [1]}, "expected": [2]}],
            "checker": {"kind": "exact"},
        }
    )
    assert result["status"] == "policy_error"


def test_cluster_labels_allow_permutations():
    passed, _ = check_result([9, 9, 4, 4], [0, 0, 1, 1], {"kind": "labels_equivalent"})
    assert passed
    failed, _ = check_result([0, 1, 1, 1], [0, 0, 1, 1], {"kind": "labels_equivalent"})
    assert not failed

