export type Difficulty = "easy" | "medium" | "hard";

export interface User {
  id: string;
  email: string;
  display_name: string;
  role: "user" | "admin";
  email_verified: boolean;
  created_at: string;
}

export interface FunctionArg {
  name: string;
  type: string;
  description: string;
}

export interface ProblemSummary {
  id: string;
  slug: string;
  status: string;
  language: string;
  version: number;
  title: string;
  difficulty: Difficulty;
  tags: string[];
  author: string;
  solved: boolean;
  can_edit: boolean;
  has_accepts: boolean;
  published_at: string;
}

export interface TestCase {
  name: string;
  args: Record<string, unknown>;
  expected: unknown;
}

export interface Problem extends ProblemSummary {
  description: string;
  function_spec: {
    class_name: string;
    method_name: string;
    args: FunctionArg[];
    return_type: string;
  };
  starter_code: string;
  public_cases: TestCase[];
  constraints: string[];
  checker: Record<string, unknown>;
  resource_limits: Record<string, unknown>;
}

export interface Submission {
  id: string;
  problem_id: string;
  version_id: string;
  kind: "run" | "submit";
  status: string;
  passed_cases: number;
  total_cases: number;
  runtime_ms: number | null;
  result: {
    message?: string;
    cases?: Array<{
      name: string;
      passed: boolean;
      message: string;
      runtime_ms: number;
      actual?: unknown;
    }>;
  } | null;
  created_at: string;
  finished_at: string | null;
}

export interface ProblemDraftPayload {
  schema_version: "ProblemDraftV1";
  title: string;
  slug_hint: string;
  description: string;
  difficulty: Difficulty;
  tags: string[];
  constraints: string[];
  function_spec: Record<string, unknown>;
  starter_code: string;
  public_cases: TestCase[];
  hidden_cases: TestCase[];
  checker: Record<string, unknown>;
  resource_limits: Record<string, unknown>;
  reference_solution: string;
  mutants: string[];
}

export interface Draft {
  id: string;
  status: string;
  source_upload_id: string | null;
  payload: ProblemDraftPayload;
  rights_attested: boolean;
  validation_report: {
    passed: boolean;
    checks: Array<{ name: string; passed: boolean; message: string }>;
    similar: Array<{ slug: string; title: string; score: number }>;
  } | null;
  published_problem_id: string | null;
  created_at: string;
  updated_at: string;
}
