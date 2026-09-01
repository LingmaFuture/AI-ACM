"use client";

import Editor, { type BeforeMount } from "@monaco-editor/react";

export function CodeEditor({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const beforeMount: BeforeMount = (monaco) => {
    monaco.editor.defineTheme("aiacm", {
      base: "vs-dark",
      inherit: true,
      rules: [
        { token: "keyword", foreground: "FF8A80" },
        { token: "number", foreground: "F5C451" },
        { token: "type.identifier", foreground: "57D3C5" },
      ],
      colors: {
        "editor.background": "#12263A",
        "editor.foreground": "#DBE7EF",
        "editorLineNumber.foreground": "#61788D",
        "editor.lineHighlightBackground": "#183149",
        "editor.selectionBackground": "#26586B",
      },
    });
  };

  return (
    <Editor
      height="100%"
      language="python"
      theme="aiacm"
      beforeMount={beforeMount}
      value={value}
      onChange={(next) => onChange(next ?? "")}
      options={{
        minimap: { enabled: false },
        fontFamily: "var(--font-mono)",
        fontSize: 13,
        lineHeight: 22,
        padding: { top: 18 },
        scrollBeyondLastLine: false,
        automaticLayout: true,
        tabSize: 4,
        wordWrap: "on",
      }}
    />
  );
}

