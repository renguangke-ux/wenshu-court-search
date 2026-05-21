import argparse
import json
import re
import subprocess
import sys
import time
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError as exc:
    raise SystemExit("缺少 playwright。请先运行：pip install playwright") from exc


CDP_URL = "http://127.0.0.1:9222"
EDGE_EXE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
EDGE_PROFILE = r"C:\Users\zyrenguangke\AppData\Local\Microsoft\Edge\User Data"
LIST_BASE = "https://wenshu.court.gov.cn/website/wenshu/181217BMTKHNT2W0/index.html"
DETAIL_MARKER = "181107ANFZ0BXSK4"
SKIP_VALUES = {"", "无", "none", "None", "NONE", "null", "NULL"}
KEYWORD_KEYS = {"s21", "s22", "s23", "s25", "s26", "s27", "s28", "s45", "s54"}
FILTER_LABELS = [
    "全文关键词",
    "案件名称",
    "案号",
    "法院名称",
    "法院层级",
    "案件类型",
    "案由",
    "裁判年份",
    "审判程序",
    "文书类型",
]


def is_skip(value: str) -> bool:
    return value.strip() in SKIP_VALUES


def prompt(label: str, default: str = "") -> str:
    suffix = f"（默认：{default}）" if default else "（无则跳过）"
    value = input(f"{label}{suffix}: ").strip()
    if not value and default:
        return default
    return value


def empty_filters() -> dict:
    return {label: "" for label in FILTER_LABELS}


def chinese_int(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    if value.isdigit():
        return int(value)

    digits = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    if value in digits:
        return digits[value]
    if value == "十":
        return 10
    if "十" in value:
        left, _, right = value.partition("十")
        tens = digits.get(left, 1 if not left else None)
        ones = digits.get(right, 0 if not right else None)
        if tens is not None and ones is not None:
            return tens * 10 + ones
    return None


def first_mapping_match(text: str, mappings: list[tuple[str, str]]) -> str:
    for pattern, value in mappings:
        if re.search(pattern, text):
            return value
    return ""


def extract_query_keyword(text: str) -> str:
    quoted = re.search(r"(?:全文)?(?:包含|含有|含|关键词|检索词)[为是：:\s]*[“\"'‘]([^”\"'’]+)[”\"'’]", text)
    if quoted:
        return quoted.group(1).strip()

    fallback = re.search(
        r"(?:全文)?(?:包含|含有|关键词|检索词)[为是：:\s]*([^，。；;、]+?)(?:的?前\s*[0-9一二两三四五六七八九十]+篇|[，。；;]|$)",
        text,
    )
    return fallback.group(1).strip(" “\"'‘”’") if fallback else ""


def extract_query_count(text: str) -> int:
    for pattern in [
        r"前\s*([0-9一二两三四五六七八九十]+)\s*篇",
        r"导出\s*([0-9一二两三四五六七八九十]+)\s*篇",
        r"([0-9一二两三四五六七八九十]+)\s*篇",
    ]:
        match = re.search(pattern, text)
        if match:
            count = chinese_int(match.group(1))
            if count:
                return max(1, count)
    return 5


def parse_natural_query(query: str) -> tuple[dict, int, str]:
    raw = empty_filters()
    text = query.strip()

    keyword = extract_query_keyword(text)
    if keyword:
        raw["全文关键词"] = keyword

    raw["法院层级"] = first_mapping_match(
        text,
        [
            (r"最高人民法院|最高法院|最高法", "最高法院"),
            (r"高级人民法院|高级法院|高院", "高级法院"),
            (r"中级人民法院|中级法院|中院", "中级法院"),
            (r"基层人民法院|基层法院|基层", "基层法院"),
        ],
    )
    raw["案件类型"] = first_mapping_match(
        text,
        [
            (r"民事案件|民事", "民事案件"),
            (r"刑事案件|刑事", "刑事案件"),
            (r"行政案件|行政", "行政案件"),
            (r"赔偿案件|赔偿", "赔偿案件"),
            (r"执行案件|执行", "执行案件"),
        ],
    )
    raw["文书类型"] = first_mapping_match(
        text,
        [
            (r"判决书", "判决书"),
            (r"裁定书", "裁定书"),
            (r"调解书", "调解书"),
            (r"决定书", "决定书"),
            (r"通知书", "通知书"),
        ],
    )

    year = re.search(r"(?:裁判年份|裁判年度|裁判日期|裁判时间)?\s*((?:19|20)\d{2})\s*年?", text)
    if year:
        raw["裁判年份"] = year.group(1)

    target_total = extract_query_count(text)
    return raw, target_total, keyword


def cdp_available() -> bool:
    try:
        with urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return bool(data.get("webSocketDebuggerUrl"))
    except Exception:
        return False


def restart_edge():
    list_url = f"{LIST_BASE}?pageId={uuid.uuid4().hex}"
    args = (
        f"--remote-debugging-port=9222 "
        f'--user-data-dir="{EDGE_PROFILE}" '
        f"--profile-directory=Default "
        f'"{list_url}"'
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Stop-Process -Name msedge -Force -ErrorAction SilentlyContinue"],
        check=False,
    )
    subprocess.Popen([EDGE_EXE, args], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        if cdp_available():
            return
        time.sleep(1)
    raise RuntimeError("Edge 已尝试重启，但 127.0.0.1:9222 仍不可连接。")


def ensure_edge():
    if cdp_available():
        return
    print("未检测到 Edge 调试端口 9222，正在自动重启 Edge。")
    restart_edge()


def clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def norm_label_text(text: str) -> str:
    return re.sub(r"[\s\u3000\xa0]+", "", text)


def sanitize_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:max_len] or "未命名文书"


def unique_links(raw_links):
    seen = set()
    links = []
    for item in raw_links:
        href = item.get("href") or ""
        title = clean_text(item.get("title") or item.get("text") or "")
        if DETAIL_MARKER not in href or not title or href in seen:
            continue
        seen.add(href)
        links.append({"title": title, "href": href})
    return links


def extract_after_label(text: str, label: str) -> str:
    lines = [line.strip() for line in text.splitlines()]
    compact_label = norm_label_text(label)
    for i, line in enumerate(lines):
        if norm_label_text(line) == compact_label:
            for nxt in lines[i + 1 : i + 4]:
                if nxt:
                    return nxt
    pattern = re.compile(label.replace(" ", r"\s*") + r"\s*[:：]?\s*([^\n]+)")
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def extract_case_no(text: str) -> str:
    explicit = extract_after_label(text, "案 号")
    if explicit and "号" in explicit:
        return explicit
    match = re.search(r"（\d{4}）最高法[^\s，。,；;：:]{1,40}?号", text)
    if match:
        return match.group(0)
    match = re.search(r"（\d{4}）[^\s，。,；;：:]{2,60}?号", text)
    return match.group(0) if match else ""


def extract_title(text: str, fallback: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for i, line in enumerate(lines):
        if norm_label_text(line) == "目录" and i + 1 < len(lines):
            return lines[i + 1]
    for line in lines:
        if any(skip in line for skip in ["中国裁判文书网", "首页", "文书全文", "登录"]):
            continue
        if len(line) >= 8 and ("判决书" in line or "裁定书" in line or "民事" in line or "裁定" in line):
            return line
    return fallback


def extract_body(text: str) -> str:
    starts = ["中华人民共和国最高人民法院", "最高人民法院", "中华人民共和国"]
    start = -1
    for token in starts:
        idx = text.find(token)
        if idx >= 0:
            start = idx
            break
    if start < 0:
        start = 0
    end_candidates = []
    for token in ["\n公 告\n", "\n公告\n", "\n一、本裁判文书库"]:
        idx = text.find(token, start)
        if idx >= 0:
            end_candidates.append(idx)
    end = min(end_candidates) if end_candidates else len(text)
    return clean_text(text[start:end])


def keyword_paragraphs(body: str, keywords: list[str]) -> list[str]:
    if not keywords:
        return []
    parts = re.split(r"\n\s*\n|(?<=。)\n", body)
    hits = []
    for part in parts:
        if any(keyword and keyword in part for keyword in keywords):
            hits.append(clean_text(part))
    return hits


def markdown_for_doc(meta: dict, keywords: list[str]) -> str:
    label = "、".join(keywords) if keywords else "检索词"
    paras = meta["keyword_paragraphs"] or ["未在正文切分段落中定位到检索词，但原文可能仍包含相关命中。"]
    quoted = "\n\n".join("> " + p.replace("\n", "\n> ") for p in paras)
    return clean_text(
        f"""# {meta['title']}

- 案号：{meta['case_no'] or '未识别'}
- 案由：{meta['cause'] or '未识别'}
- 来源链接：{meta['href']}
- 发布日期：{meta['publish_date'] or '未识别'}

## 包含“{label}”的段落

{quoted}

## 正文

{meta['body']}
"""
    ) + "\n"


def make_output_dir(base_dir: Path, keyword: str) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = sanitize_filename(keyword if keyword and not is_skip(keyword) else "未设全文", 40)
    out_dir = base_dir / f"裁判文书_{stamp}_{suffix}"
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "artifacts").mkdir(exist_ok=True)
    return out_dir


def collect_inputs(query: str = "") -> tuple[dict, int, str]:
    if query:
        raw, target_total, keyword = parse_natural_query(query)
        print("已解析自然语言检索请求：")
        for label in FILTER_LABELS:
            value = raw.get(label, "")
            if value:
                print(f"- {label}: {value}")
        print(f"- 导出篇数: {target_total}")
        return raw, target_total, keyword

    print("请输入检索条件；输入“无”或直接回车表示不设置。")
    raw = {
        "全文关键词": prompt("全文关键词"),
        "案件名称": prompt("案件名称"),
        "案号": prompt("案号"),
        "法院名称": prompt("法院名称"),
        "法院层级": prompt("法院层级：最高法院/高级法院/中级法院/基层法院"),
        "案件类型": prompt("案件类型：民事案件/刑事案件/行政案件/赔偿案件/执行案件/其他案件"),
        "案由": prompt("案由"),
        "裁判年份": prompt("裁判年份，例如 2025"),
        "审判程序": prompt("审判程序"),
        "文书类型": prompt("文书类型：判决书/裁定书/调解书/决定书/通知书/令/其他"),
    }
    total_raw = prompt("导出篇数", "5")
    try:
        target_total = max(1, int(total_raw))
    except ValueError:
        target_total = 5
    return raw, target_total, raw["全文关键词"]


def wait_for_list_ready(page):
    for _ in range(45):
        try:
            ready = page.evaluate("typeof addParams1545035259000 === 'function' && !!window.$page")
            if ready:
                return
        except Exception:
            pass
        page.wait_for_timeout(1000)
    raise RuntimeError("文书列表页未加载完成，未找到站内检索函数。")


def reverse_map(page, dict_name: str, value: str) -> str:
    if is_skip(value):
        return ""
    return page.evaluate(
        """({dictName, value}) => {
            const dic = window.wenshulist && window.wenshulist.dic;
            if (!dic) return value;
            const map = dic[dictName] || {};
            for (const [code, name] of Object.entries(map)) {
                if (String(name).trim() === value) return code;
            }
            for (const [code, name] of Object.entries(map)) {
                if (String(name).includes(value) || value.includes(String(name))) return code;
            }
            return value;
        }""",
        {"dictName": dict_name, "value": value.strip()},
    )


def find_cause_code(page, value: str) -> tuple[str, str]:
    if is_skip(value):
        return "", ""
    return page.evaluate(
        """value => {
            const dic = window.wenshulist && window.wenshulist.dic;
            const map = (dic && dic.ayMap) || {};
            for (const [code, name] of Object.entries(map)) {
                if (String(name).trim() === value) return [code, name];
            }
            for (const [code, name] of Object.entries(map)) {
                if (String(name).includes(value) || value.includes(String(name))) return [code, name];
            }
            return ["s16", value];
        }""",
        value.strip(),
    )


def cause_key_for_code(code: str) -> str:
    if not code or code == "s16":
        return "s16"
    digits = re.sub(r"\D", "", str(code))
    if not digits:
        return "s16"
    length = len(digits)
    if length <= 4:
        return "s11"
    if length <= 6:
        return "s12"
    if length <= 8:
        return "s13"
    if length <= 10:
        return "s14"
    return "s15"


def build_params(page, raw: dict) -> tuple[dict, list[str], list[str]]:
    params = {}
    labels = []
    keywords = []

    simple_map = {
        "全文关键词": "s21",
        "案件名称": "s1",
        "案号": "s7",
        "法院名称": "s2",
        "裁判年份": "s42",
    }
    for label, key in simple_map.items():
        value = raw.get(label, "").strip()
        if not is_skip(value):
            params[key] = value
            labels.append(f"{label}={value}")
            if key in KEYWORD_KEYS:
                keywords.extend([part for part in re.split(r"\s+", value) if part])

    dict_specs = [
        ("法院层级", "s4", "fycjMap"),
        ("案件类型", "s8", "ajlxMap"),
        ("审判程序", "s9", "spcxMap"),
        ("文书类型", "s6", "wslxMap"),
    ]
    for label, key, dict_name in dict_specs:
        value = raw.get(label, "").strip()
        if not is_skip(value):
            code = reverse_map(page, dict_name, value)
            params[key] = code
            labels.append(f"{label}={value}")

    cause = raw.get("案由", "").strip()
    if not is_skip(cause):
        code, name = find_cause_code(page, cause)
        params[cause_key_for_code(code)] = code if code != "s16" else cause
        labels.append(f"案由={name or cause}")

    return params, keywords, labels


def apply_filters(page, params: dict):
    page.evaluate(
        """params => {
            const box = document.querySelector('.LT_Filter_right.clearfix');
            if (box) box.querySelectorAll('p').forEach(p => p.remove());
            window.localStorage.setItem('$listPageSearchItem', '{}');
            addParams1545035259000(params);
            if (window.$page && window.$page.loadData) window.$page.loadData();
        }""",
        params,
    )
    page.wait_for_timeout(10000)


def extract_visible_links(page):
    raw_links = page.eval_on_selector_all(
        "a[href]",
        """els => els.map(a => ({
            href: a.href,
            text: a.innerText,
            title: a.getAttribute('title') || ''
        }))""",
    )
    return unique_links(raw_links)


def click_next(page) -> bool:
    return page.evaluate(
        """() => {
            const buttons = [...document.querySelectorAll('.pageButton, a, span, button')];
            const next = buttons.find(el => (el.innerText || '').trim() === '下一页' && !String(el.className).includes('disabled'));
            if (!next) return false;
            next.click();
            return true;
        }"""
    )


def extract_one(context, link: dict, index: int, out_dir: Path, keywords: list[str]) -> dict:
    detail = context.new_page()
    try:
        detail.goto(link["href"], wait_until="domcontentloaded", timeout=60000)
        detail.wait_for_timeout(7000)
        text = clean_text(detail.evaluate("document.body.innerText"))
        decoded_url = unquote(detail.url)
    finally:
        detail.close()

    title = extract_title(text, link["title"])
    case_no = extract_case_no(text)
    cause = extract_after_label(text, "案 由")
    publish_date_raw = extract_after_label(text, "发布日期")
    publish_match = re.search(r"\d{4}-\d{2}-\d{2}", publish_date_raw)
    publish_date = publish_match.group(0) if publish_match else publish_date_raw
    body = extract_body(text)
    paras = keyword_paragraphs(body, keywords)

    meta = {
        "index": index,
        "title": title,
        "case_no": case_no,
        "cause": cause,
        "publish_date": publish_date,
        "href": decoded_url,
        "body": body,
        "keyword_paragraphs": paras,
    }
    filename = sanitize_filename(f"{index:03d}_{case_no or '未识别案号'}_{title}.md")
    path = out_dir / filename
    path.write_text(markdown_for_doc(meta, keywords), encoding="utf-8")
    meta["path"] = str(path)
    meta["filename"] = filename
    return meta


def total_result_text(body_text: str) -> str:
    matches = re.findall(r"共检索到\s*([0-9]+)\s*篇文书", body_text)
    return matches[-1] if matches else "未识别"


def write_record(
    out_dir: Path,
    filter_labels: list[str],
    total_text: str,
    extracted: list[dict],
    skipped: int,
    failures: list[str],
    original_query: str = "",
    parsed_raw: dict | None = None,
):
    lines = [
        "# 检索记录",
        "",
        "- 检索网站：中国裁判文书网",
    ]
    if original_query:
        parsed_labels = []
        if parsed_raw:
            parsed_labels = [f"{label}={value}" for label, value in parsed_raw.items() if value and not is_skip(value)]
        lines.extend(
            [
                f"- 原始自然语言请求：{original_query}",
                "- 解析后的检索条件：" + ("；".join(parsed_labels) if parsed_labels else "未设置"),
            ]
        )
    lines.extend(
        [
            "- 检索条件：" + ("；".join(filter_labels) if filter_labels else "未设置"),
            f"- 页面显示总量：{total_text} 篇（网站提示仅显示前600条时以页面为准）",
            f"- 实际导出文书：{len(extracted)} 篇",
            f"- 跳过重复文书：{skipped} 篇",
            f"- 失败链接：{len(failures)} 条",
            "",
            "## 已导出文件",
            "",
        ]
    )
    for item in extracted:
        lines.append(f"- {item['case_no'] or '未识别案号'}：{item['title']} -> {item['filename']}")
    if failures:
        lines.extend(["", "## 失败链接", ""])
        lines.extend(f"- {url}" for url in failures)
    (out_dir / "检索记录.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="通过 Edge 登录态检索中国裁判文书网并导出 Markdown。")
    parser.add_argument("--query", default="", help="自然语言检索请求；未提供时进入逐项交互输入模式。")
    return parser.parse_args()


def run():
    args = parse_args()
    original_query = args.query.strip()
    raw, target_total, keyword = collect_inputs(original_query)
    out_dir = make_output_dir(Path.cwd(), keyword)
    artifacts = out_dir / "artifacts"
    ensure_edge()

    extracted = []
    failures = []
    skipped = 0
    seen_cases = set()

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        page = context.new_page()
        list_url = f"{LIST_BASE}?pageId={uuid.uuid4().hex}"
        page.goto(list_url, wait_until="domcontentloaded", timeout=60000)
        page.bring_to_front()
        wait_for_list_ready(page)
        params, keywords, filter_labels = build_params(page, raw)
        apply_filters(page, params)

        page_no = 1
        last_body = page.evaluate("document.body.innerText")
        while len(extracted) < target_total and page_no <= 120:
            body_text = page.evaluate("document.body.innerText")
            (artifacts / f"list_page_{page_no:03d}.txt").write_text(body_text, encoding="utf-8")
            last_body = body_text
            links = extract_visible_links(page)
            if not links:
                break
            for link in links:
                if len(extracted) >= target_total:
                    break
                try:
                    meta = extract_one(context, link, len(extracted) + 1, out_dir, keywords)
                    if meta["case_no"] and meta["case_no"] in seen_cases:
                        Path(meta["path"]).unlink(missing_ok=True)
                        skipped += 1
                        continue
                    if meta["case_no"]:
                        seen_cases.add(meta["case_no"])
                    extracted.append(meta)
                    print(f"已导出 {len(extracted)}/{target_total}: {meta['case_no'] or meta['title']}")
                    time.sleep(2)
                except Exception as exc:
                    failures.append(f"{link['href']} | {exc}")
            if len(extracted) >= target_total:
                break
            if not click_next(page):
                break
            page.wait_for_timeout(10000)
            page_no += 1
        page.close()

    write_record(
        out_dir,
        filter_labels,
        total_result_text(last_body),
        extracted,
        skipped,
        failures,
        original_query,
        raw,
    )
    print(f"\n完成。导出目录：{out_dir}")
    print(f"导出 {len(extracted)} 篇；跳过重复 {skipped} 篇；失败 {len(failures)} 条。")


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\n已取消。")
        sys.exit(130)
    except PlaywrightTimeoutError as exc:
        print(f"页面超时：{exc}")
        sys.exit(2)
    except Exception as exc:
        print(f"失败：{exc}")
        sys.exit(1)
