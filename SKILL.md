---
name: wenshu-court-search
description: Use this skill when the user wants to search 中国裁判文书网 / wenshu.court.gov.cn from a natural-language request or interactive filters, and export retrieved judgments as Markdown files. This skill uses the logged-in Microsoft Edge browser through CDP to avoid brittle direct HTTP scraping.
---

# 中国裁判文书网检索

When the user describes a court-search request in natural language, parse that request and pass it directly to the bundled script with `--query`. Do not ask the user to fill out each filter unless the request is too ambiguous to run safely.

If the request is to retrieve documents by one or more exact case numbers（案号）, prefer the dedicated case-number mode. It uses the visible site search box, clears conditions before each case number, and verifies that the opened detail page contains the target case number before saving.

```powershell
python "$env:USERPROFILE\.codex\skills\wenshu-court-search\scripts\wenshu_search.py" --query "在裁判文书网上检索最高法院裁决的民事案件，包含‘无明显不当’的前50篇裁判文书"
```

Exact case-number examples:

```powershell
# One or more case numbers inline
python "$env:USERPROFILE\.codex\skills\wenshu-court-search\scripts\wenshu_search.py" --case-nos "（2025）最高法民再354号,（2023）最高法知民终1511号" --connect-only

# Many case numbers, one per line
python "$env:USERPROFILE\.codex\skills\wenshu-court-search\scripts\wenshu_search.py" --case-file .\案号.txt --connect-only
```

If no natural-language request is available, run the script without arguments to use the interactive fallback:

```powershell
python "$env:USERPROFILE\.codex\skills\wenshu-court-search\scripts\wenshu_search.py"
```

## Workflow

1. Run the script from the user's desired output workspace.
2. For exact case numbers, use `--case-nos` or `--case-file`. This mode searches one case number at a time, clears prior conditions, and treats no result as non-fatal.
3. For broader searches, use `--query "..."`. The script extracts common filters and runs non-interactively.
4. If `--query` is not provided, the script prompts for filters one by one. Enter `无`, blank, or press Enter to skip a filter.
5. If Edge is not listening on `127.0.0.1:9222`, the script starts a dedicated Edge profile at `C:\tmp\wenshu-edge-profile` by default. It must not kill the user's normal Edge session.
6. If the user has already logged in through a visible Edge window, use `--connect-only` so the script fails rather than restarting or replacing the session.
7. The script writes Markdown files and a search record for each run.

## Login and Browser Safety

- Prefer a dedicated Edge profile for this site:

```powershell
Start-Process -FilePath 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' -ArgumentList @('--remote-debugging-port=9222','--user-data-dir=C:\tmp\wenshu-edge-profile','--no-first-run','--profile-directory=Default','https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html')
```

- Ask the user to log in, solve CAPTCHA/slider challenges, and keep that window open.
- Verify login state before extraction:

```powershell
Invoke-RestMethod 'http://127.0.0.1:9222/json/version'
```

- Do not run broad `Stop-Process msedge -Force` during extraction. It can destroy the user's logged-in session.
- If a previous run was interrupted, check for stale processes before restarting:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'wenshu_search|remote-debugging-port=9222|wenshu-edge-profile' }
```

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
- Case numbers like `（2025）最高法民再354号` -> dedicated exact case-number mode

Defaults for `--query`: if no full-text keyword is found, it is not set; if no export count is found, export `5` judgments.

## Output

Each ordinary query creates a new folder in the current directory:

```text
裁判文书_YYYYMMDD_HHMMSS_关键词
```

Exact case-number mode creates one folder per case number and writes a top-level `批量案号提取汇总.md`.

The folder contains:

- `001_案号_标题.md`, etc.
- `检索记录.md`
- `artifacts/` with diagnostic page text

For `--query` runs, `检索记录.md` also includes the original natural-language request and the parsed search conditions for review.

Each judgment Markdown includes title, case number, cause of action, source URL, publish date, keyword-hit paragraphs, and full body text.

## Case-Number Mode Details

- The site combines multiple visible conditions as AND clauses. Therefore the script must clear search conditions before each case number.
- Use the real input box and `Enter` key for case-number searches. Do not rely on manually setting DOM values or internal parameter injection; the site's front-end state will not necessarily update.
- Save a document only if the detail page contains the target case number. Some detail pages expose the case-number label with stray HTML fragments, so validate against the full text/body instead of strict equality with the label field alone.
- If no result is found, record `未命中` and continue.
- If the site asks for verification, let the user solve it in the visible Edge window, then rerun with `--connect-only`.

## Notes

- The user must already be logged in to `wenshu.court.gov.cn` in the Edge profile exposed on `127.0.0.1:9222`, or allow the script to start a dedicated profile and then log in there.
- The site may throttle or show verification. If extraction stalls, inspect the visible Edge window and resolve the site prompt manually, then rerun.
- Prefer this script over direct HTTP requests because the site uses dynamic scripts, login state, and anti-automation behavior.
