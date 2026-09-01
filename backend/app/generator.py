import copy
import json
import re

import httpx

from .config import settings
from .schemas import ProblemDraftV1
from .seed_data import KMEANS_DRAFT, KNN_DRAFT

SYSTEM_PROMPT = """你是 AI 算法编程题编辑。根据资料生成一道中文 LeetCode 风格函数题。
只允许 Python + 已注入的 NumPy(np)，答案中不得使用 import。题目必须能够用隐藏 JSON 测试确定性判题。
输出严格符合给定 JSON Schema。参考答案必须完整；至少给出两个能被测试拦截的典型错误实现。
聚类题优先使用 labels_equivalent 检查器，数值题使用 allclose，分类标签使用 exact。"""


def _extract_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def generate_draft(source_text: str, source_name: str) -> ProblemDraftV1:
    if not settings.ai_api_key:
        template = KMEANS_DRAFT if re.search(r"k.?means|聚类|簇", source_text, re.I) else KNN_DRAFT
        payload = copy.deepcopy(template)
        payload["title"] = f"{payload['title']} · AI 草稿"
        payload["slug_hint"] = f"{payload['slug_hint']}-draft"
        payload["description"] += (
            f"\n\n> 本题由本地演示生成器根据《{source_name}》创建；配置 AI_API_KEY 后会按资料内容生成。"
        )
        return ProblemDraftV1.model_validate(payload)

    schema = ProblemDraftV1.model_json_schema()
    response = httpx.post(
        f"{settings.ai_base_url.rstrip('/')}/chat/completions",
        headers={"Authorization": f"Bearer {settings.ai_api_key}"},
        json={
            "model": settings.ai_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"资料文件：{source_name}\n\n资料内容：\n{source_text[:100_000]}",
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "ProblemDraftV1", "strict": True, "schema": schema},
            },
        },
        timeout=120,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"]
    return ProblemDraftV1.model_validate(_extract_json(content))

