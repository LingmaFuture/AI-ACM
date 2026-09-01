export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(`/api/v1${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : Array.isArray(body.detail)
          ? body.detail.map((item: { msg?: string }) => item.msg ?? "字段无效").join("；")
          : "请求失败，请稍后再试";
    throw new ApiError(detail, response.status);
  }
  return body as T;
}

export function difficultyLabel(value: string) {
  return { easy: "入门", medium: "进阶", hard: "挑战" }[value] ?? value;
}

export function statusLabel(value: string) {
  return (
    {
      queued: "排队中",
      running: "判题中",
      accepted: "已通过",
      wrong_answer: "答案错误",
      runtime_error: "运行错误",
      time_limit: "超出时间",
      memory_limit: "超出内存",
      internal_error: "系统错误",
    }[value] ?? value
  );
}
