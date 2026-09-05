import ast
import contextlib
import io
import json
import math
import signal
import time
from dataclasses import dataclass
from typing import Any

import numpy as np


class PolicyError(ValueError):
    pass


class ExecutionTimeout(TimeoutError):
    pass


class OutputLimitError(RuntimeError):
    pass


class SafeImportStripper(ast.NodeTransformer):
    """Remove the one redundant import supported by the sandbox.

    NumPy is injected into the execution scope as ``np``. Models commonly
    emit ``import numpy as np`` anyway; dropping that exact statement avoids
    exposing Python's import machinery to submitted code.
    """

    def visit_Import(self, node: ast.Import) -> ast.AST | None:
        if len(node.names) == 1 and node.names[0].name == "numpy" and node.names[0].asname == "np":
            return None
        return node


FORBIDDEN_NAMES = {
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
    "input",
    "globals",
    "locals",
    "vars",
    "dir",
    "getattr",
    "setattr",
    "delattr",
    "breakpoint",
    "help",
}


class PolicyVisitor(ast.NodeVisitor):
    def visit_Import(self, node: ast.Import) -> None:
        raise PolicyError(
            f"第 {node.lineno} 行不允许导入：{ast.unparse(node)}；NumPy 已通过 np 提供，"
            "请移除该导入并改用 np.exp、np.log、np.sqrt 等函数或 Python 内置函数"
        )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        raise PolicyError(
            f"第 {node.lineno} 行不允许导入：{ast.unparse(node)}；NumPy 已通过 np 提供，"
            "请移除该导入并改用 np.exp、np.log、np.sqrt 等函数或 Python 内置函数"
        )

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_NAMES or "__" in node.id:
            raise PolicyError(f"不允许使用名称：{node.id}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("_"):
            raise PolicyError("不允许访问私有或魔术属性")
        self.generic_visit(node)


class LimitedWriter(io.StringIO):
    def __init__(self, limit_bytes: int):
        super().__init__()
        self.limit_bytes = limit_bytes
        self.written = 0

    def write(self, value: str) -> int:
        size = len(value.encode("utf-8", errors="replace"))
        self.written += size
        if self.written > self.limit_bytes:
            raise OutputLimitError("程序输出超过限制")
        return super().write(value)


SAFE_BUILTINS = {
    "__build_class__": __build_class__,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "Exception": Exception,
    "filter": filter,
    "float": float,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "object": object,
    "pow": pow,
    "range": range,
    "reversed": reversed,
    "round": round,
    "RuntimeError": RuntimeError,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "ValueError": ValueError,
    "zip": zip,
}


def validate_source(source: str) -> ast.Module:
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as exc:
        raise PolicyError(f"语法错误：第 {exc.lineno} 行 {exc.msg}") from exc
    tree = SafeImportStripper().visit(tree)
    ast.fix_missing_locations(tree)
    PolicyVisitor().visit(tree)
    return tree


def _alarm_handler(_signum: int, _frame: Any) -> None:
    raise ExecutionTimeout("执行超时")


@contextlib.contextmanager
def deadline(seconds: float):
    previous = signal.signal(signal.SIGALRM, _alarm_handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def json_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise ValueError("返回值包含 NaN 或 Infinity")
    return value


def build_args(function_spec: dict, values: dict) -> list[Any]:
    args: list[Any] = []
    for item in function_spec["args"]:
        if item["name"] not in values:
            raise ValueError(f"测试数据缺少参数 {item['name']}")
        value = values[item["name"]]
        if item["type"] == "ndarray":
            value = np.asarray(value)
        args.append(value)
    return args


def check_result(actual: Any, expected: Any, checker: dict) -> tuple[bool, str]:
    kind = checker.get("kind", "exact")
    actual = json_value(actual)
    expected = json_value(expected)
    if kind == "exact":
        passed = actual == expected
        return passed, "结果正确" if passed else "结果与期望不一致"
    if kind == "allclose":
        try:
            passed = bool(
                np.allclose(
                    np.asarray(actual, dtype=float),
                    np.asarray(expected, dtype=float),
                    atol=float(checker.get("atol", 1e-6)),
                    rtol=float(checker.get("rtol", 1e-6)),
                )
            )
        except (TypeError, ValueError):
            passed = False
        return passed, "数值在允许误差内" if passed else "数值误差超过限制"
    if kind == "labels_equivalent":
        try:
            left = np.asarray(actual).reshape(-1).tolist()
            right = np.asarray(expected).reshape(-1).tolist()
            passed = len(left) == len(right) and all(
                (left[i] == left[j]) == (right[i] == right[j])
                for i in range(len(left))
                for j in range(i + 1, len(left))
            )
        except (TypeError, ValueError):
            passed = False
        return passed, "聚类划分等价" if passed else "聚类划分与期望不等价"
    if kind == "mse_below":
        try:
            mse = float(np.mean((np.asarray(actual) - np.asarray(expected)) ** 2))
            threshold = float(checker["threshold"])
            passed = mse <= threshold
            return passed, f"MSE={mse:.6g}，阈值={threshold:.6g}"
        except (TypeError, ValueError, KeyError):
            return False, "无法计算 MSE"
    raise ValueError(f"未知检查器：{kind}")


@dataclass
class CaseOutcome:
    name: str
    passed: bool
    message: str
    runtime_ms: int
    actual: Any | None = None


def execute(payload: dict) -> dict:
    source = payload["code"]
    function_spec = payload["function_spec"]
    tests = payload["tests"]
    checker = payload["checker"]
    limits = payload.get("resource_limits", {})
    timeout = float(limits.get("timeout_seconds", 3))
    output_limit = int(limits.get("output_kb", 32)) * 1024
    reveal_actual = bool(payload.get("reveal_actual", False))

    try:
        tree = validate_source(source)
        scope = {
            "__builtins__": SAFE_BUILTINS,
            "__name__": "submission",
            "np": np,
        }
        output = LimitedWriter(output_limit)
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output), deadline(timeout):
            exec(compile(tree, "<submission>", "exec"), scope)
        solution_class = scope.get(function_spec.get("class_name", "Solution"))
        solution_function = scope.get(function_spec["method_name"])
        if not isinstance(solution_class, type) and not callable(solution_function):
            raise PolicyError(
                f"必须定义 {function_spec.get('class_name', 'Solution')} 类或 "
                f"{function_spec['method_name']} 函数"
            )
    except ExecutionTimeout:
        return {"status": "time_limit", "passed": 0, "total": len(tests), "cases": []}
    except (PolicyError, OutputLimitError) as exc:
        return {
            "status": "policy_error",
            "passed": 0,
            "total": len(tests),
            "message": str(exc),
            "cases": [],
        }
    except Exception as exc:
        return {
            "status": "runtime_error",
            "passed": 0,
            "total": len(tests),
            "message": f"加载代码失败：{type(exc).__name__}: {exc}",
            "cases": [],
        }

    outcomes: list[CaseOutcome] = []
    for test in tests:
        started = time.perf_counter()
        try:
            if isinstance(solution_class, type):
                instance = solution_class()
                method = getattr(instance, function_spec["method_name"], None)
            else:
                method = solution_function
            if not callable(method):
                raise AttributeError(f"缺少方法 {function_spec['method_name']}")
            output = LimitedWriter(output_limit)
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output), deadline(timeout):
                actual = method(*build_args(function_spec, test["args"]))
            passed, message = check_result(actual, test["expected"], checker)
            outcomes.append(
                CaseOutcome(
                    name=test["name"],
                    passed=passed,
                    message=message,
                    runtime_ms=round((time.perf_counter() - started) * 1000),
                    actual=json_value(actual) if reveal_actual else None,
                )
            )
        except ExecutionTimeout:
            outcomes.append(CaseOutcome(test["name"], False, "执行超时", round(timeout * 1000)))
            break
        except OutputLimitError as exc:
            outcomes.append(CaseOutcome(test["name"], False, str(exc), 0))
            break
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            outcomes.append(CaseOutcome(test["name"], False, message[:500], 0))
            break

    passed_count = sum(case.passed for case in outcomes)
    status = "accepted" if passed_count == len(tests) else "wrong_answer"
    if outcomes and any("超时" in case.message for case in outcomes):
        status = "time_limit"
    result_cases = [
        {
            "name": case.name,
            "passed": case.passed,
            "message": case.message,
            "runtime_ms": case.runtime_ms,
            **({"actual": case.actual} if reveal_actual else {}),
        }
        for case in outcomes
    ]
    return {
        "status": status,
        "passed": passed_count,
        "total": len(tests),
        "runtime_ms": sum(case.runtime_ms for case in outcomes),
        "cases": result_cases,
    }


def main() -> None:
    try:
        payload = json.load(__import__("sys").stdin)
        result = execute(payload)
    except Exception as exc:  # Runner boundary: never leak a traceback to clients.
        result = {
            "status": "internal_error",
            "passed": 0,
            "total": 0,
            "message": f"判题器错误：{type(exc).__name__}: {exc}",
        }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
