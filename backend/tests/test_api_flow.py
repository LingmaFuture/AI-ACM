import copy
from uuid import uuid4

import httpx
import pytest

from app import generator
from app.seed_data import KNN_DRAFT

from .conftest import create_verified_user

KNN_SOLUTION = """class Solution:
    def predict(self, X_train, y_train, X_test, k):
        predictions = []
        for sample in X_test:
            distances = np.sqrt(np.sum((X_train - sample) ** 2, axis=1))
            neighbors = np.argsort(distances, kind="stable")[:k]
            labels, counts = np.unique(y_train[neighbors], return_counts=True)
            largest = np.max(counts)
            predictions.append(int(np.min(labels[counts == largest])))
        return predictions
"""


@pytest.mark.anyio
async def test_public_problem_and_judging_flow(client: httpx.AsyncClient):
    suffix = uuid4().hex[:8]
    await create_verified_user(client, suffix)
    response = await client.get("/api/v1/problems")
    assert response.status_code == 200
    problems = response.json()["items"]
    knn = next(item for item in problems if "KNN" in item["tags"])
    detail = await client.get(f"/api/v1/problems/{knn['slug']}")
    assert detail.status_code == 200
    assert "hidden_cases" not in detail.text
    assert "reference_solution" not in detail.text

    submitted = await client.post(
        f"/api/v1/problems/{knn['id']}/submit", json={"code": KNN_SOLUTION}
    )
    assert submitted.status_code == 202, submitted.text
    result = await client.get(f"/api/v1/submissions/{submitted.json()['id']}")
    assert result.status_code == 200
    assert result.json()["status"] == "accepted"
    assert result.json()["passed_cases"] == result.json()["total_cases"]

    profile = await client.get("/api/v1/profile")
    assert profile.json()["stats"]["solved"] >= 1


@pytest.mark.anyio
async def test_upload_generate_validate_and_publish(client: httpx.AsyncClient):
    suffix = uuid4().hex[:8]
    owner = await create_verified_user(client, suffix)
    content = (
        "KNN 算法认证资料。实现 K 近邻分类，计算欧氏距离，选择最近的 k 个样本，"
        "按照多数投票输出预测标签，平票时选择较小的标签。"
    ).encode()
    uploaded = await client.post(
        "/api/v1/uploads",
        files={"file": ("knn-notes.txt", content, "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    assert "object_key" not in uploaded.text

    generation = await client.post(f"/api/v1/uploads/{uploaded.json()['id']}/generate")
    assert generation.status_code == 202, generation.text
    job = (await client.get(f"/api/v1/jobs/{generation.json()['job_id']}")).json()
    assert job["status"] == "completed", job
    draft_id = job["draft_id"]
    draft = (await client.get(f"/api/v1/drafts/{draft_id}")).json()
    assert draft["payload"]["reference_solution"]

    update = await client.patch(
        f"/api/v1/drafts/{draft_id}",
        json={"payload": draft["payload"], "rights_attested": True},
    )
    assert update.status_code == 200, update.text
    validation = await client.post(f"/api/v1/drafts/{draft_id}/validate")
    assert validation.status_code == 202, validation.text
    validation_job = (
        await client.get(f"/api/v1/jobs/{validation.json()['job_id']}")
    ).json()
    assert validation_job["status"] == "completed", validation_job
    assert validation_job["result"]["passed"] is True, validation_job["result"]

    published = await client.post(f"/api/v1/drafts/{draft_id}/publish")
    assert published.status_code == 201, published.text
    public = await client.get(f"/api/v1/problems/{published.json()['slug']}")
    assert public.status_code == 200
    assert "reference_solution" not in public.text
    assert public.json()["version"] == 1

    revision = await client.post(f"/api/v1/problems/{published.json()['id']}/revisions")
    assert revision.status_code == 201, revision.text
    revision_body = revision.json()
    revision_body["payload"]["description"] += "\n\n这是通过不可变版本流程发布的修订说明。"
    saved_revision = await client.patch(
        f"/api/v1/drafts/{revision_body['id']}",
        json={"payload": revision_body["payload"], "rights_attested": True},
    )
    assert saved_revision.status_code == 200
    revision_validation = await client.post(
        f"/api/v1/drafts/{revision_body['id']}/validate"
    )
    revision_job = (
        await client.get(f"/api/v1/jobs/{revision_validation.json()['job_id']}")
    ).json()
    assert revision_job["result"]["passed"] is True
    revision_publish = await client.post(f"/api/v1/drafts/{revision_body['id']}/publish")
    assert revision_publish.status_code == 201
    revised_public = await client.get(f"/api/v1/problems/{published.json()['slug']}")
    assert revised_public.json()["version"] == 2

    await client.post("/api/v1/auth/logout")
    outsider_suffix = uuid4().hex[:8]
    outsider = await create_verified_user(client, outsider_suffix)
    assert outsider["id"] != owner["id"]
    forbidden = await client.get(f"/api/v1/drafts/{draft_id}")
    assert forbidden.status_code == 403


@pytest.mark.anyio
async def test_generation_preserves_failed_precheck_as_private_editable_draft(client, monkeypatch):
    await create_verified_user(client, uuid4().hex[:8])
    payload = copy.deepcopy(KNN_DRAFT)
    payload["mutants"][1] = payload["reference_solution"]
    requests = []

    def fake_post(url, **kwargs):
        requests.append(kwargs["json"])
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={"choices": [{"message": {"content": generator.json.dumps(payload)}}]},
        )

    monkeypatch.setattr(generator.settings, "ai_api_key", "test-key")
    monkeypatch.setattr(generator.httpx, "post", fake_post)
    content = (
        "KNN 算法资料：按欧氏距离选取最近的 k 个邻居，多数投票分类，平票选较小标签。"
    ).encode()
    uploaded = await client.post(
        "/api/v1/uploads",
        files={"file": ("knn-repair.txt", content, "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    generation = await client.post(f"/api/v1/uploads/{uploaded.json()['id']}/generate")
    assert generation.status_code == 202, generation.text
    job = (await client.get(f"/api/v1/jobs/{generation.json()['job_id']}")).json()
    assert len(requests) == generator.MAX_GENERATION_ATTEMPTS
    assert job["status"] == "completed", job
    assert job["error"] is None
    draft_id = job["draft_id"]
    draft = (await client.get(f"/api/v1/drafts/{draft_id}")).json()
    assert draft["status"] == "needs_revision"
    assert draft["validation_report"]["passed"] is False
    assert "错误实现 2" in draft["validation_report"]["checks"][0]["message"]
    assert draft["payload"]["mutants"][1] == payload["reference_solution"]
    assert draft["published_problem_id"] is None

    # Attesting rights and rerunning validation must not bypass the failing mutant.
    saved = await client.patch(
        f"/api/v1/drafts/{draft_id}",
        json={"payload": draft["payload"], "rights_attested": True},
    )
    assert saved.status_code == 200, saved.text
    validation = await client.post(f"/api/v1/drafts/{draft_id}/validate")
    assert validation.status_code == 202, validation.text
    failed = (await client.get(f"/api/v1/jobs/{validation.json()['job_id']}")).json()
    assert failed["result"]["passed"] is False
    publish = await client.post(f"/api/v1/drafts/{draft_id}/publish")
    assert publish.status_code == 400
    assert "尚未通过自动质量门禁" in publish.text

    # Repairing the mutant allows the ordinary quality gate and publishing flow.
    draft["payload"]["mutants"] = KNN_DRAFT["mutants"]
    repaired = await client.patch(
        f"/api/v1/drafts/{draft_id}",
        json={"payload": draft["payload"], "rights_attested": True},
    )
    assert repaired.status_code == 200, repaired.text
    validation = await client.post(f"/api/v1/drafts/{draft_id}/validate")
    assert validation.status_code == 202, validation.text
    passed = (await client.get(f"/api/v1/jobs/{validation.json()['job_id']}")).json()
    assert passed["result"]["passed"] is True
    publish = await client.post(f"/api/v1/drafts/{draft_id}/publish")
    assert publish.status_code == 201, publish.text
