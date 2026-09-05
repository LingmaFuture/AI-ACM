import copy
import json
import re
from collections.abc import Callable

import httpx
from pydantic import ValidationError

from .config import settings
from .schemas import ProblemDraftV1
from .seed_data import KMEANS_DRAFT, KNN_DRAFT

SYSTEM_PROMPT = """你是 AI 算法编程题编辑。根据资料生成一道中文 LeetCode 风格函数题。
只允许 Python + 已注入的 NumPy(np)，答案中不得使用 import。题目必须能够用隐藏 JSON 测试确定性判题。
starter_code、reference_solution 和每份 mutants 都不得使用 import 或 from ... import，
也不要导入 math、typing、numpy 等模块。指数、对数、平方根直接使用 np.exp、np.log、np.sqrt；
例如 ELU 的负数分支使用 alpha * (np.exp(x) - 1)，无需 math.exp。
输出严格符合给定 JSON Schema。参考答案必须完整；至少给出两个能被测试拦截的典型错误实现。
每份错误实现应在代码注释中说明真实算法缺陷，以及哪个测试会触发该缺陷；为每份错解设计至少一个
符合题目约束、使其输出与参考答案在当前检查器下不等价的测试。仅改写代码或改变等价标签不是错解。
聚类题优先使用 labels_equivalent 检查器，数值题使用 allclose，分类标签使用 exact。
只输出一个 JSON 对象，不要解释文字或 Markdown 代码围栏。顶层字段名必须严格使用：
schema_version、title、slug_hint、description、difficulty、tags、constraints、function_spec、
starter_code、public_cases、hidden_cases、checker、resource_limits、reference_solution、mutants。
difficulty 只能是 easy、medium、hard；schema_version 必须是 ProblemDraftV1。
每个测试用例的 args 必须是对象，并包含 function_spec.args 中的全部同名参数；expected 的 JSON 类型必须与
function_spec.return_type 一致（list/ndarray 必须用 JSON 数组，不能用空格分隔的字符串）。"""

MAX_GENERATION_ATTEMPTS = 3


class DraftGenerationError(RuntimeError):
    """AI 服务有响应，但没有生成可用的题目草稿。"""

    def __init__(
        self,
        message: str,
        *,
        draft: ProblemDraftV1 | None = None,
        validation_error: str | None = None,
    ):
        super().__init__(message)
        self.draft = draft
        self.validation_error = validation_error


def _content_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def _extract_json(raw: str) -> dict:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("AI 返回了空内容")
    raw = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as original_error:
        decoder = json.JSONDecoder()
        for match in re.finditer(r"\{", raw):
            try:
                payload, _ = decoder.raw_decode(raw[match.start() :])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                break
        else:
            raise ValueError("AI 返回内容不是有效的 JSON 对象") from original_error
    if not isinstance(payload, dict):
        raise ValueError("AI 返回 JSON 的顶层必须是对象")
    return payload


def _validation_summary(error: Exception) -> str:
    if isinstance(error, ValidationError):
        messages = []
        for item in error.errors(include_url=False)[:8]:
            location = ".".join(str(part) for part in item["loc"]) or "顶层"
            messages.append(f"{location}: {item['msg']}")
        return "；".join(messages)
    return str(error)[:1000]


def _normalize_type(value: object, name: str = "", sample: object = None) -> str:
    if isinstance(value, dict):
        value = value.get("type") or value.get("dtype") or value.get("name")
    raw = str(value or "").lower().replace(" ", "")
    if any(marker in raw for marker in ("ndarray", "numpy", "matrix", "array")):
        return "ndarray"
    if raw in {"int", "integer", "int32", "int64"}:
        return "int"
    if raw in {"float", "number", "double", "float32", "float64"}:
        return "float"
    if raw in {"str", "string"}:
        return "str"
    if raw in {"bool", "boolean"}:
        return "bool"
    if "list" in raw or "sequence" in raw or "tuple" in raw:
        return "list"

    lowered_name = name.lower()
    if lowered_name.startswith(("x_", "y_")) or lowered_name in {
        "x",
        "y",
        "features",
        "labels",
        "points",
        "centroids",
    }:
        return "ndarray"
    if isinstance(sample, bool):
        return "bool"
    if isinstance(sample, int):
        return "int"
    if isinstance(sample, float):
        return "float"
    if isinstance(sample, str):
        return "str"
    if isinstance(sample, list):
        return "ndarray" if sample and isinstance(sample[0], list) else "list"
    return "list"


def _signature_parts(starter_code: str) -> tuple[str | None, list[str]]:
    match = re.search(
        r"def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)",
        starter_code,
    )
    if not match:
        return None, []
    names = []
    for raw in (match.group(2) or "").split(","):
        name = raw.strip().split(":", 1)[0].split("=", 1)[0].strip().lstrip("*")
        if name == "self":
            continue
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            names.append(name)
    return match.group(1), names


def _case_input(case: dict) -> object:
    for key in ("args", "inputs", "input"):
        if key in case:
            return case[key]
    return None


def _normalize_draft_payload(raw: dict) -> dict:
    """Convert common OpenAI-compatible schema variations to ProblemDraftV1."""
    payload = copy.deepcopy(raw)
    if "slug_hint" not in payload and payload.get("slug"):
        payload["slug_hint"] = payload.pop("slug")
    payload.setdefault("schema_version", "ProblemDraftV1")

    difficulty = str(payload.get("difficulty", "")).lower()
    payload["difficulty"] = {
        "入门": "easy",
        "简单": "easy",
        "初级": "easy",
        "进阶": "medium",
        "中等": "medium",
        "中级": "medium",
        "挑战": "hard",
        "困难": "hard",
        "高级": "hard",
    }.get(difficulty, difficulty)

    tags = payload.get("tags")
    if isinstance(tags, str):
        payload["tags"] = [item for item in re.split(r"[,，、;；\s]+", tags) if item][:8]

    constraints = payload.get("constraints")
    if isinstance(constraints, str):
        payload["constraints"] = [constraints]
    elif isinstance(constraints, dict):
        payload["constraints"] = [
            f"{key}: {json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value}"
            for key, value in constraints.items()
        ]

    starter_code = str(payload.get("starter_code") or "")
    parsed_method, parsed_names = _signature_parts(starter_code)
    raw_spec = payload.get("function_spec")
    raw_spec = raw_spec if isinstance(raw_spec, dict) else {}

    raw_cases = payload.get("public_cases")
    raw_cases = raw_cases if isinstance(raw_cases, list) else []
    first_case = raw_cases[0] if raw_cases and isinstance(raw_cases[0], dict) else {}
    first_input = _case_input(first_case)

    raw_args = raw_spec.get("args")
    if not isinstance(raw_args, list):
        raw_args = raw_spec.get("arguments") or raw_spec.get("parameters") or []
    arg_names: list[str] = []
    normalized_args: list[dict] = []
    candidate_count = max(len(raw_args) if isinstance(raw_args, list) else 0, len(parsed_names))
    for index in range(candidate_count):
        item = raw_args[index] if isinstance(raw_args, list) and index < len(raw_args) else {}
        if isinstance(item, dict):
            name = item.get("name") or item.get("id")
            declared_type = item.get("type") or item.get("data_type") or item.get("dtype")
            description = str(item.get("description") or "")
        elif isinstance(item, str):
            name = item.split(":", 1)[0].strip()
            declared_type = item.split(":", 1)[1].strip() if ":" in item else None
            description = ""
        else:
            name = None
            declared_type = None
            description = ""
        name = str(name or (parsed_names[index] if index < len(parsed_names) else f"arg{index + 1}"))
        sample = None
        if isinstance(first_input, dict):
            sample = first_input.get(name)
        elif isinstance(first_input, list) and index < len(first_input):
            sample = first_input[index]
        arg_names.append(name)
        normalized_args.append(
            {
                "name": name,
                "type": _normalize_type(declared_type, name, sample),
                "description": description,
            }
        )

    raw_return = raw_spec.get("return_type") or raw_spec.get("returns") or raw_spec.get("return")
    expected_sample = first_case.get("expected", first_case.get("output"))
    payload["function_spec"] = {
        "class_name": raw_spec.get("class_name") or "Solution",
        "method_name": raw_spec.get("method_name") or raw_spec.get("name") or parsed_method,
        "args": normalized_args,
        "return_type": _normalize_type(raw_return, "return", expected_sample),
    }

    def normalize_cases(value: object, prefix: str) -> object:
        if not isinstance(value, list):
            return value
        result = []
        for index, item in enumerate(value, start=1):
            if not isinstance(item, dict):
                result.append(item)
                continue
            raw_input = _case_input(item)
            if isinstance(raw_input, dict):
                args = raw_input
            elif isinstance(raw_input, list):
                args = {name: value for name, value in zip(arg_names, raw_input, strict=False)}
            else:
                direct_args = {name: item[name] for name in arg_names if name in item}
                if direct_args:
                    args = direct_args
                else:
                    args = {arg_names[0]: raw_input} if len(arg_names) == 1 else {}
            expected = item.get("expected", item.get("output", item.get("result")))
            if payload["function_spec"]["return_type"] in {"list", "ndarray"} and isinstance(
                expected, str
            ):
                tokens = [token for token in re.split(r"[,，\s]+", expected.strip()) if token]
                try:
                    expected = [float(token) for token in tokens]
                except ValueError:
                    pass
            result.append(
                {
                    "name": str(item.get("name") or f"{prefix} {index}"),
                    "args": args,
                    "expected": expected,
                }
            )
        return result

    payload["public_cases"] = normalize_cases(payload.get("public_cases"), "样例")
    payload["hidden_cases"] = normalize_cases(payload.get("hidden_cases"), "隐藏测试")

    checker = payload.get("checker")
    if isinstance(checker, str):
        checker = {"kind": checker}
    elif not isinstance(checker, dict):
        checker = {}
    params = checker.get("params") if isinstance(checker.get("params"), dict) else {}
    raw_checker_kind = str(checker.get("kind") or checker.get("type") or "").lower()
    topic = " ".join(
        [str(payload.get("title") or ""), str(payload.get("description") or "")]
        + [str(tag) for tag in payload.get("tags") or []]
    ).lower()
    is_clustering = any(
        value in topic for value in ("聚类", "簇", "cluster", "k-means", "kmeans")
    )
    if raw_checker_kind in {"exact", "allclose", "labels_equivalent", "mse_below"}:
        checker_kind = raw_checker_kind
    elif "mse" in raw_checker_kind or "mean_squared" in raw_checker_kind:
        checker_kind = "mse_below"
    elif any(value in raw_checker_kind for value in ("cluster", "label_equiv", "permutation")):
        checker_kind = "labels_equivalent"
    elif any(value in raw_checker_kind for value in ("float", "close", "tolerance", "numeric")):
        checker_kind = "allclose"
    elif any(value in raw_checker_kind for value in ("exact", "equal", "match", "classification")):
        checker_kind = "exact"
    else:
        if is_clustering:
            checker_kind = "labels_equivalent"
        elif any(value in topic for value in ("分类", "classification", "knn")):
            checker_kind = "exact"
        elif params.get("threshold") is not None or checker.get("threshold") is not None:
            checker_kind = "mse_below"
        else:
            checker_kind = "allclose"
    if checker_kind == "labels_equivalent" and not is_clustering:
        checker_kind = "allclose"
    payload["checker"] = {
        "kind": checker_kind,
        "atol": checker.get("atol", params.get("atol", 1e-6)),
        "rtol": checker.get("rtol", params.get("rtol", 1e-6)),
        "threshold": checker.get("threshold", params.get("threshold")),
    }

    mutants = payload.get("mutants")
    if isinstance(mutants, list):
        normalized_mutants = []
        for item in mutants:
            if isinstance(item, str):
                normalized_mutants.append(item)
                continue
            if isinstance(item, dict):
                code = next(
                    (
                        item.get(key)
                        for key in ("code", "implementation", "solution", "mutant", "content")
                        if isinstance(item.get(key), str)
                    ),
                    None,
                )
                normalized_mutants.append(code if code is not None else item)
                continue
            normalized_mutants.append(item)
        payload["mutants"] = normalized_mutants

    limits = payload.get("resource_limits")
    limits = limits if isinstance(limits, dict) else {}
    timeout = limits.get("timeout_seconds")
    if timeout is None and limits.get("time_limit_ms") is not None:
        timeout = float(limits["time_limit_ms"]) / 1000
    memory = limits.get("memory_mb", limits.get("memory_limit_mb", 256))
    payload["resource_limits"] = {
        "timeout_seconds": min(10, max(0.2, float(timeout or 3))),
        "memory_mb": min(512, max(64, int(memory))),
        "output_kb": min(128, max(4, int(limits.get("output_kb", 32)))),
    }
    return payload


def generate_draft(
    source_text: str,
    source_name: str,
    reference_validator: Callable[[ProblemDraftV1], str | None] | None = None,
) -> ProblemDraftV1:
    if not settings.ai_api_key:
        template = KMEANS_DRAFT if re.search(r"k.?means|聚类|簇", source_text, re.I) else KNN_DRAFT
        payload = copy.deepcopy(template)
        payload["title"] = f"{payload['title']} · AI 草稿"
        payload["slug_hint"] = f"{payload['slug_hint']}-draft"
        payload["description"] += (
            f"\n\n> 本题由本地演示生成器根据《{source_name}》创建；配置 AI_API_KEY 后会按资料内容生成。"
        )
        draft = ProblemDraftV1.model_validate(payload)
        validation_error = reference_validator(draft) if reference_validator else None
        if validation_error:
            raise DraftGenerationError(validation_error)
        return draft

    schema = ProblemDraftV1.model_json_schema()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"资料文件：{source_name}\n\n资料内容：\n{source_text[:100_000]}",
        },
    ]
    last_error = "未知错误"
    previous_content: str | None = None
    last_draft: ProblemDraftV1 | None = None
    last_validation_error: str | None = None
    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        request_messages = list(messages)
        if attempt > 1:
            if previous_content:
                request_messages.append({"role": "assistant", "content": previous_content})
            request_messages.append(
                {
                    "role": "user",
                    "content": (
                        f"上一次输出无法使用：{last_error}\n"
                        "请针对上一版草稿的失败项进行修复，并返回完整草稿。"
                        "若错解未被拦截，请检查对应 mutants 代码与参考答案是否等价："
                        "等价则替换为有真实算法缺陷的错解；否则补充能触发缺陷的测试，"
                        "在错解注释中注明对应测试。保留题意、函数接口与已有有效用例，"
                        "不要通过删除错解、放宽检查器或修改题意来规避校验。"
                        "若执行报导入错误，请按反馈中的具体语句与行号移除导入，"
                        "并将依赖它的调用改用已提供的 np 函数或 Python 内置函数。"
                        "只输出符合 JSON Schema 的 JSON 对象，"
                        "不要省略字段，不要使用 Markdown 代码围栏。"
                    ),
                }
            )
        try:
            response = httpx.post(
                f"{settings.ai_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {settings.ai_api_key}"},
                json={
                    "model": settings.ai_model,
                    "messages": request_messages,
                    "response_format": {
                        "type": "json_schema",
                        "json_schema": {
                            "name": "ProblemDraftV1",
                            "strict": True,
                            "schema": schema,
                        },
                    },
                    "max_tokens": 8192,
                },
                timeout=120,
            )
            response.raise_for_status()
            body = response.json()
            if not isinstance(body, dict):
                raise ValueError("AI 服务返回的数据结构无效")
            choices = body.get("choices") or []
            if not choices:
                service_error = body.get("error") or {}
                message = (
                    service_error.get("message")
                    if isinstance(service_error, dict)
                    else str(service_error)
                )
                raise ValueError(message or "AI 服务没有返回候选答案")
            choice = choices[0]
            message = choice.get("message") or {}
            content = _content_text(message.get("content"))
            previous_content = content
            if not content.strip():
                reason = choice.get("finish_reason") or "未知"
                raise ValueError(f"AI 返回了空内容（结束原因：{reason}）")
            raw_payload = _extract_json(content)
            draft = ProblemDraftV1.model_validate(_normalize_draft_payload(raw_payload))
            validation_error = reference_validator(draft) if reference_validator else None
            previous_content = json.dumps(draft.model_dump(mode="json"), ensure_ascii=False)
            if validation_error:
                last_draft = ProblemDraftV1.model_validate(draft.model_dump(mode="json"))
                last_validation_error = validation_error
                raise ValueError(validation_error)
            return draft
        except (KeyError, TypeError, ValueError, ValidationError) as exc:
            last_error = _validation_summary(exc)
            if attempt == MAX_GENERATION_ATTEMPTS:
                break
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                raise DraftGenerationError(
                    "OpenRouter 免费模型请求过于频繁，请稍等几分钟后重新生成"
                ) from exc
            raise DraftGenerationError(f"AI 服务请求失败：{exc}") from exc
        except httpx.HTTPError as exc:
            raise DraftGenerationError(f"AI 服务请求失败：{exc}") from exc

    raise DraftGenerationError(
        f"AI 连续 {MAX_GENERATION_ATTEMPTS} 次未返回可用题目：{last_error}",
        draft=last_draft,
        validation_error=last_validation_error,
    )
