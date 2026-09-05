type JsonValue = null | boolean | number | string | JsonValue[] | { [key: string]: JsonValue };

function formatValue(value: JsonValue, depth: number): string {
  const indent = "  ".repeat(depth);
  const childIndent = `${indent}  `;

  if (Array.isArray(value)) {
    // Keep numeric vectors on one line so each matrix row stays readable.
    if (value.every((item) => typeof item === "number")) {
      return `[${value.join(", ")}]`;
    }
    const items = value.map((item) => `${childIndent}${formatValue(item, depth + 1)}`);
    return `[\n${items.join(",\n")}\n${indent}]`;
  }

  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value);
    if (entries.length === 0) return "{}";
    const items = entries.map(
      ([key, item]) => `${childIndent}${JSON.stringify(key)}: ${formatValue(item, depth + 1)}`,
    );
    return `{\n${items.join(",\n")}\n${indent}}`;
  }

  return JSON.stringify(value);
}

export function formatJson(value: unknown): string {
  // Preserve JSON serialization rules for omitted properties and escaped strings.
  const serialized = JSON.stringify(value);
  if (serialized === undefined) return "";
  return formatValue(JSON.parse(serialized) as JsonValue, 0);
}
