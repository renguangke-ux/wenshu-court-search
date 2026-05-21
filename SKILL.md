---
name: wenshu-court-search
description: Use this skill when the user wants to search 中国裁判文书网 / wenshu.court.gov.cn from a natural-language request or interactive filters, and export retrieved judgments as Markdown files. This skill uses the logged-in Microsoft Edge browser through CDP to avoid brittle direct HTTP scraping.
---

# 中国裁判文书网检索

When the user describes a court-search request in natural language, parse that request and pass it directly to the bundled script with `--query`. Do not ask the user to fill out each filter unless the request is too ambiguous to run safely.

```powershell
python "$env:USERPROFILE\.codex\skills\wenshu-court-search\scripts\wenshu_search.py" --query "在裁判文书网上检索最高法院裁决的民事案件，包含‘无明显不当’的前50篇裁判文书"
```

If no natural-language request is available, run the script without arguments to use the interactive fallback:

```powershell
python "$env:USERPROFILE\.codex\skills\wenshu-court-search\scripts\wenshu_search.py"
```

## Workflow

1. Run the script from the user's desired output workspace.
2. Prefer `--query "..."` for natural-language requests. The script extracts common filters and runs non-interactively.
3. If `--query` is not provided, the script prompts for filters one by one. Enter `无`, blank, or press Enter to skip a filter.
4. If Edge is not listening on `127.0.0.1:9222`, the script restarts Edge with the default user profile and opens the judgment list page.
5. The script applies filters through the site's own JavaScript search functions, paginates results, opens each judgment, and writes Markdown files.

## Supported Filters

- 全文关键词
- 案件名称
- 案号
- 法院名称
- 法院层级
- 案件类型
- 案由
- 裁判年份
- 审判程序
- 文书类型
- 导出篇数

Natural-language parsing currently recognizes common expressions:

- `最高法院` / `高级法院` / `中级法院` / `基层法院` -> 法院层级
- `民事` / `刑事` / `行政` / `赔偿` / `执行案件` -> 案件类型
- `包含“...”` / `全文包含...` / `含有...` -> 全文关键词
- `前50篇` / `50篇` / `导出50篇` -> 导出篇数
- `判决书` / `裁定书` / `调解书` -> 文书类型
- `2025年` / `裁判年份2025` -> 裁判年份

Defaults for `--query`: if no full-text keyword is found, it is not set; if no export count is found, export `5` judgments.

## Output

Each run creates a new folder in the current directory:

```text
裁判文书_YYYYMMDD_HHMMSS_关键词
```

The folder contains:

- `001_案号_标题.md`, etc.
- `检索记录.md`
- `artifacts/` with diagnostic page text

For `--query` runs, `检索记录.md` also includes the original natural-language request and the parsed search conditions for review.

Each judgment Markdown includes title, case number, cause of action, source URL, publish date, keyword-hit paragraphs, and full body text.

## Notes

- The user must already be logged in to `wenshu.court.gov.cn` in the default Edge profile.
- The site may throttle or show verification. If extraction stalls, inspect the visible Edge window and resolve the site prompt manually, then rerun.
- Prefer this script over direct HTTP requests because the site uses dynamic scripts, login state, and anti-automation behavior.
