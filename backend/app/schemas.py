from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator


class FunctionArg(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    type: Literal["int", "float", "str", "bool", "list", "ndarray"]
    description: str = ""


class FunctionSpec(BaseModel):
    class_name: str = "Solution"
    method_name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")
    args: list[FunctionArg] = Field(min_length=1)
    return_type: Literal["int", "float", "str", "bool", "list", "ndarray"]


class TestCase(BaseModel):
    name: str
    args: dict[str, Any]
    expected: Any


class CheckerSpec(BaseModel):
    kind: Literal["exact", "allclose", "labels_equivalent", "mse_below"]
    atol: float = Field(default=1e-6, ge=0)
    rtol: float = Field(default=1e-6, ge=0)
    threshold: float | None = None


class ResourceLimits(BaseModel):
    timeout_seconds: float = Field(default=3, ge=0.2, le=10)
    memory_mb: int = Field(default=256, ge=64, le=512)
    output_kb: int = Field(default=32, ge=4, le=128)


class ProblemDraftV1(BaseModel):
    schema_version: Literal["ProblemDraftV1"] = "ProblemDraftV1"
    title: str = Field(min_length=4, max_length=180)
    slug_hint: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=30)
    difficulty: Literal["easy", "medium", "hard"]
    tags: list[str] = Field(min_length=1, max_length=8)
    constraints: list[str] = Field(min_length=1)
    function_spec: FunctionSpec
    starter_code: str = Field(min_length=20)
    public_cases: list[TestCase] = Field(min_length=1)
    hidden_cases: list[TestCase] = Field(min_length=2)
    checker: CheckerSpec
    resource_limits: ResourceLimits = Field(default_factory=ResourceLimits)
    reference_solution: str = Field(min_length=30)
    mutants: list[str] = Field(min_length=2)

    @field_validator("tags")
    @classmethod
    def unique_tags(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(tag.strip() for tag in value if tag.strip()))


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=40)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class DraftUpdate(BaseModel):
    payload: ProblemDraftV1
    rights_attested: bool = False


class SubmissionRequest(BaseModel):
    code: str = Field(min_length=20, max_length=50_000)


class ReportRequest(BaseModel):
    reason: Literal["incorrect", "duplicate", "copyright", "abuse", "other"]
    details: str = Field(min_length=5, max_length=2000)


class ModerationRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)

