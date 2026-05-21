# wenshu-court-search

中国裁判文书网检索与 Markdown 导出工具。适用于 Codex、Claude Code 或其它能运行本地命令的智能体。

该 skill 通过本机 Microsoft Edge 的登录态和 Chrome DevTools Protocol 访问 `wenshu.court.gov.cn`，使用站内 JavaScript 检索函数完成搜索、翻页、打开文书详情，并把裁判文书导出为 Markdown 文件。

## 功能

- 支持自然语言检索入口。
- 支持旧版逐项交互输入。
- 自动解析常见检索条件：
  - 法院层级：最高法院、高级法院、中级法院、基层法院
  - 案件类型：民事案件、刑事案件、行政案件、赔偿案件、执行案件
  - 全文关键词：如 `包含“无明显不当”`
  - 导出篇数：如 `前20篇`、`导出50篇`
  - 文书类型：判决书、裁定书、调解书
  - 裁判年份：如 `2025年`
- 每次运行生成独立输出目录。
- 每篇文书保存为独立 Markdown。
- 生成 `检索记录.md`，记录原始请求、解析条件、导出数量和失败链接。
- 保存列表页诊断文本到 `artifacts/`，方便排查登录、验证或站点跳转问题。

## 环境要求

- Windows
- Python 3.10+
- Microsoft Edge
- Python 依赖：`playwright`
- 已在默认 Edge 用户配置中登录中国裁判文书网
- 脚本能访问或启动 Edge 调试端口：`127.0.0.1:9222`

安装依赖：

```powershell
pip install playwright
```

如果 Playwright 浏览器依赖缺失，可运行：

```powershell
python -m playwright install
```

## 自然语言调用

推荐用法：

```powershell
python "$env:USERPROFILE\.codex\skills\wenshu-court-search\scripts\wenshu_search.py" --query "在裁判文书网上检索最高法院裁判的民事案件，包含‘无明显不当’内容的20篇裁判文书"
```

解析结果示例：

```text
全文关键词=无明显不当
法院层级=最高法院
案件类型=民事案件
导出篇数=20
```

更多示例：

```powershell
python "$env:USERPROFILE\.codex\skills\wenshu-court-search\scripts\wenshu_search.py" --query "检索最高法院民事判决书，包含‘合同无效’的前10篇"
```

```powershell
python "$env:USERPROFILE\.codex\skills\wenshu-court-search\scripts\wenshu_search.py" --query "检索2025年高级法院执行案件调解书，全文包含“执行异议”的导出5篇"
```

## 交互式调用

不传 `--query` 时进入逐项输入模式：

```powershell
python "$env:USERPROFILE\.codex\skills\wenshu-court-search\scripts\wenshu_search.py"
```

脚本会依次询问：

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

输入空白、直接回车或 `无` 表示跳过该条件。

## 输出结构

每次运行会在当前工作目录生成新文件夹：

```text
裁判文书_YYYYMMDD_HHMMSS_关键词
```

目录内容：

```text
裁判文书_YYYYMMDD_HHMMSS_关键词/
├── 001_案号_标题.md
├── 002_案号_标题.md
├── ...
├── 检索记录.md
└── artifacts/
    ├── list_page_001.txt
    └── ...
```

单篇 Markdown 包含：

- 标题
- 案号
- 案由
- 来源链接
- 发布日期
- 命中关键词段落
- 正文全文

## 给智能体的使用建议

当用户用自然语言提出文书网检索需求时，智能体应优先直接调用 `--query`，不要再反问用户逐项填写字段。

例如用户说：

```text
下载最高法院裁判的民事案件中包含“无明显不当”内容的20篇裁判文书
```

智能体应运行：

```powershell
python "$env:USERPROFILE\.codex\skills\wenshu-court-search\scripts\wenshu_search.py" --query "下载最高法院裁判的民事案件中包含“无明显不当”内容的20篇裁判文书"
```

仅在请求缺少关键意图、目标网站不可用、登录态失效或用户要求精确字段控制时，再改用交互式模式或询问澄清问题。

## 常见问题

### 只导出 0 篇，诊断文本是“返回首页 / 注册”

通常表示 Edge 中的裁判文书网登录态失效，或站点把列表页跳转到了注册/登录相关页面。

处理方式：

1. 打开默认 Edge。
2. 登录 `https://wenshu.court.gov.cn/`。
3. 确认能正常进入文书列表页。
4. 重新运行脚本。

### 脚本提示未找到站内检索函数

可能是页面未加载完成、站点结构变化、登录态失效或出现验证。

处理方式：

- 查看可见 Edge 窗口是否有验证码、登录提示或异常页面。
- 手动完成验证后重新运行。
- 查看输出目录中的 `artifacts/list_page_*.txt`。

### Edge 被自动重启

如果 `127.0.0.1:9222` 不可用，脚本会尝试关闭并重启 Edge，以启用远程调试端口并使用默认用户配置。

如不希望脚本自动重启 Edge，可先手动用调试端口启动 Edge，或在已有调试端口可用时再运行脚本。

### Claude Code 等其它智能体能否使用

可以作为普通本地脚本调用。前提是该智能体能访问本目录、运行 PowerShell/Python，并使用同一台机器上的 Edge 登录态。

需要注意：Codex 的 `SKILL.md` 触发机制不一定被其它智能体原生识别，但 `scripts/wenshu_search.py` 是普通 Python 脚本，可以直接复用。

## 文件说明

- `SKILL.md`：Codex skill 说明与触发规则。
- `scripts/wenshu_search.py`：实际检索、解析、导出脚本。
- `README.md`：面向人和其它智能体的使用说明。

## 限制

- 自然语言解析采用规则匹配，不依赖外部 NLP 或大模型 API。
- 第一版覆盖常见检索表达，不保证理解所有复杂法律检索句式。
- 依赖裁判文书网当前页面结构和登录态。
- 网站可能限流、验证或仅展示部分结果。
