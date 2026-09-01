#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Export the momentum screener execution logic markdown doc to HTML and PDF."""

from __future__ import annotations

import argparse
import html
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import mistune


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MARKDOWN_PATH = REPO_ROOT / "docs" / "momentum-screener-execution-logic.md"
DEFAULT_HTML_PATH = REPO_ROOT / "docs" / "momentum-screener-execution-logic.html"
DEFAULT_PDF_PATH = REPO_ROOT / "docs" / "momentum-screener-execution-logic.pdf"
HTML_TO_PDF_SCRIPT = REPO_ROOT / "scripts" / "render_html_to_pdf.js"


class MermaidRenderer(mistune.HTMLRenderer):
    def block_code(self, code: str, info: str | None = None) -> str:
        language = (info or "").strip().lower()
        if language == "mermaid":
            return f'<div class="diagram mermaid">{html.escape(code)}</div>\n'
        return super().block_code(code, info)


def build_markdown_renderer() -> mistune.Markdown:
    renderer = MermaidRenderer(escape=False)
    return mistune.create_markdown(
        renderer=renderer,
        plugins=["table", "strikethrough"],
    )


def render_html(markdown_text: str, *, title: str) -> str:
    markdown = build_markdown_renderer()
    body = markdown(markdown_text)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f7fb;
      --paper: #ffffff;
      --ink: #162033;
      --muted: #5b667a;
      --line: #d8dfeb;
      --line-strong: #b6c4da;
      --accent: #0f7bff;
      --code-bg: #0f1729;
      --code-ink: #f3f7ff;
      --quote-bg: #eef4ff;
      --table-head: #eef3fb;
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "Segoe UI", sans-serif;
      line-height: 1.72;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }}

    .page {{
      width: 210mm;
      margin: 0 auto;
      padding: 16mm 16mm 18mm;
      background: var(--paper);
      box-shadow: 0 0 0.8mm rgba(18, 28, 45, 0.10);
    }}

    .meta {{
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 10px;
    }}

    h1, h2, h3 {{
      color: var(--ink);
      line-height: 1.3;
      break-after: avoid-page;
      page-break-after: avoid;
    }}

    h1 {{
      font-size: 26px;
      margin: 0 0 10px;
      padding-bottom: 10px;
      border-bottom: 2px solid var(--line-strong);
    }}

    h2 {{
      font-size: 20px;
      margin-top: 28px;
      margin-bottom: 10px;
      padding-left: 10px;
      border-left: 4px solid var(--accent);
    }}

    h3 {{
      font-size: 16px;
      margin-top: 18px;
      margin-bottom: 8px;
    }}

    p, li {{
      font-size: 13px;
    }}

    p, ul, ol, table, blockquote, pre, .diagram {{
      margin-top: 0;
      margin-bottom: 12px;
    }}

    ul, ol {{
      padding-left: 24px;
    }}

    li + li {{
      margin-top: 4px;
    }}

    code {{
      font-family: "Cascadia Code", "Consolas", monospace;
      font-size: 12px;
      background: #edf2fb;
      color: #0d315f;
      padding: 1px 4px;
      border-radius: 4px;
    }}

    pre {{
      background: var(--code-bg);
      color: var(--code-ink);
      padding: 12px 14px;
      border-radius: 10px;
      overflow: auto;
      break-inside: avoid;
      page-break-inside: avoid;
    }}

    pre code {{
      background: transparent;
      color: inherit;
      padding: 0;
    }}

    blockquote {{
      margin-left: 0;
      padding: 10px 14px;
      background: var(--quote-bg);
      border-left: 4px solid var(--accent);
      border-radius: 0 8px 8px 0;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      break-inside: avoid;
      page-break-inside: avoid;
      font-size: 12px;
    }}

    th, td {{
      border: 1px solid var(--line);
      padding: 8px 10px;
      vertical-align: top;
    }}

    th {{
      background: var(--table-head);
      text-align: left;
    }}

    .diagram {{
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: #fbfdff;
      break-inside: avoid;
      page-break-inside: avoid;
    }}

    .mermaid {{
      text-align: center;
    }}

    .mermaid svg {{
      max-width: 100%;
      height: auto;
    }}

    hr {{
      border: none;
      border-top: 1px solid var(--line);
      margin: 20px 0;
    }}

    @media print {{
      body {{
        background: #fff;
      }}

      .page {{
        width: auto;
        margin: 0;
        padding: 0;
        box-shadow: none;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <div class="meta">生成时间：{generated_at}</div>
    {body}
  </main>
  <script>
    window.__MERMAID_READY = false;
  </script>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
  <script>
    (async function () {{
      try {{
        mermaid.initialize({{
          startOnLoad: false,
          securityLevel: "loose",
          theme: "base",
          themeVariables: {{
            fontFamily: "Microsoft YaHei, PingFang SC, Noto Sans CJK SC, Segoe UI, sans-serif",
            primaryColor: "#eef4ff",
            primaryBorderColor: "#8bb5ff",
            primaryTextColor: "#162033",
            lineColor: "#5b667a",
            secondaryColor: "#ffffff",
            tertiaryColor: "#f5f7fb"
          }}
        }});
        await mermaid.run({{ querySelector: ".mermaid" }});
        for (const container of document.querySelectorAll(".diagram")) {{
          const svg = container.querySelector("svg");
          if (!svg) {{
            continue;
          }}
          const box = svg.getBoundingClientRect();
          const maxWidth = Math.max(container.clientWidth - 24, 480);
          const maxHeight = 760;
          const scale = Math.min(1, maxWidth / Math.max(box.width, 1), maxHeight / Math.max(box.height, 1));
          if (scale < 1) {{
            svg.style.width = `${{Math.round(box.width * scale)}}px`;
            svg.style.height = `${{Math.round(box.height * scale)}}px`;
          }}
        }}
      }} catch (error) {{
        console.error("Mermaid render failed:", error);
      }} finally {{
        window.__MERMAID_READY = true;
      }}
    }})();
  </script>
</body>
</html>
"""


def export(markdown_path: Path, html_path: Path, pdf_path: Path) -> None:
    markdown_text = markdown_path.read_text(encoding="utf-8")
    html_path.write_text(
        render_html(markdown_text, title="强势筛选执行逻辑说明"),
        encoding="utf-8",
    )

    subprocess.run(
        [
            "node",
            str(HTML_TO_PDF_SCRIPT),
            str(html_path),
            str(pdf_path),
        ],
        check=True,
        cwd=str(REPO_ROOT),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_MARKDOWN_PATH)
    parser.add_argument("--html-output", type=Path, default=DEFAULT_HTML_PATH)
    parser.add_argument("--pdf-output", type=Path, default=DEFAULT_PDF_PATH)
    args = parser.parse_args()

    markdown_path = args.input.resolve()
    html_path = args.html_output.resolve()
    pdf_path = args.pdf_output.resolve()

    if not markdown_path.exists():
        raise FileNotFoundError(f"Markdown doc not found: {markdown_path}")

    html_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    export(markdown_path, html_path, pdf_path)
    print(f"HTML exported to: {html_path}")
    print(f"PDF exported to: {pdf_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
