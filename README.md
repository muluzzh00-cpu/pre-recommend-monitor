# 2027 建筑 / 规划推免、预推免、直博通知监控

面向指定的七个学院和对应学校研招官网。Python 抓取、规则判断、HTML 邮件、GitHub Actions 每小时执行，状态保存到同一仓库的 `monitor-state` 独立分支。

**已部署：[GitHub 仓库](https://github.com/muluzzh00-cpu/pre-recommend-monitor)。7 校 34 页云端抓取、真实邮件送达、两轮正式运行和持久化去重已验证。详见 [云端验收报告](reports/云端验收报告.md)；定时历史及首次日报仍待后续观察。**


最新升级：已启用最近 75 分钟、今天首次发现、去重优先和 baseline 策略；见 [近 75 分钟升级验收](reports/近75分钟升级验收.md)。

## 1. 系统监控什么

| 学校 | 核心学院 |
|---|---|
| 浙江大学 | 建筑工程学院 |
| 南京大学 | 建筑与城市规划学院 |
| 苏州大学 | 金螳螂建筑学院 |
| 湖南大学 | 建筑与规划学院 |
| 华南理工大学 | 建筑学院 |
| 天津大学 | 建筑工程学院 |
| 武汉大学 | 城市设计学院 |

天津大学建筑工程学院和建筑学院是不同学院。本项目遵照指定名单监控 **建筑工程学院**，没有自行添加建筑学院。如果你原本想报建筑学、城市规划、风景园林方向，需要自行确认目标学院并修改配置。

只抓取官方 `.edu.cn` 来源。学校网页中的微信、第三方转载、需要登录的报名系统不会被抓取。校级通用政策保留，不延伸抓取其它学院的独立网站。校级列表标题明确指向其它学院且无目标学科的通知会被排除。

`config/sites.yaml` 保存全部入口、学校、学院、来源级别、选择器、抓取方式和真实验证状态。南大使用网页自带 `dataList` JSON 的专用解析器，直接解析数据，不执行网页脚本；其它已验证静态页面使用 requests / BeautifulSoup。当前不需要安装 Playwright。不能用浏览器来绕过访问限制。

## 2. 首次创建 GitHub 仓库

1. 注册或登录 [GitHub](https://github.com/)。
2. 打开 [创建仓库](https://github.com/new)。
3. Repository name 填 `pre-recommend-monitor`。
4. 建议选 **Private**，避免暴露你的收件地址及监控偏好。公共仓库也可运行，但状态分支和提交历史公开可见。
5. 不勾选自动生成 README、gitignore 或 license（本项目已提供文件）。
6. 点击 Create repository。

## 3. 上传项目

推荐使用 GitHub Desktop，能完整上传 `.github` 隐藏目录：

1. 解压项目到一个固定文件夹，例如 `Documents/pre-recommend-monitor`。
2. 安装 [GitHub Desktop](https://desktop.github.com/)，登录你的账号。
3. File → New repository，选择项目父目录，名称填 `pre-recommend-monitor`，创建或添加此文件夹。
4. 确认文件列表里包含 `.github/workflows/monitor.yml`、`main.py`、`config/sites.yaml`。
5. 写提交说明 `Initial monitor`，点击 Commit to main。
6. Publish repository，保持私有。若已在网页创建同名仓库，可以用 Repository → Repository settings 配置远程地址，或先 Clone 空仓库再把项目文件复制进去。

熟悉命令行也可在项目根目录执行（替换仓库链接）：

```powershell
git init -b main
git add .
git commit -m "Add 2027 admission monitor"
git remote add origin https://github.com/YOUR_ACCOUNT/pre-recommend-monitor.git
git push -u origin main
```

如使用网页 Upload files，须确认 `.github/workflows/monitor.yml` 确实上传，不能只上传 ZIP 文件；GitHub 不会解压 ZIP 并执行其中工作流。不要上传本地 `.env`、`state/` 或虚拟环境。

## 4. 配置 Gmail 发送邮箱

接收邮箱是 `muluzzh00@gmail.com`。发送邮箱可以是另一个 Gmail，也可以是支持加密 SMTP 的邮箱。

Gmail 的步骤：

1. 登录用于发送邮件的 Google 账号。
2. 打开 Google 账号 → 安全性，启用两步验证。
3. 进入 [应用专用密码](https://myaccount.google.com/apppasswords)，为此程序创建一个密码。
4. 将新密码直接填入本机 `.env` 或 GitHub Secrets。不要把它发到聊天、截图、代码、README 或提交历史。
5. 此处不能使用平时网页登录 Gmail 的密码。Google 账号修改密码后，原应用专用密码可能被撤销，需要重新创建。

没有应用专用密码选项时，可能与组织账号、只使用安全密钥的两步验证或高级保护有关。以 [Google 官方说明](https://support.google.com/mail/answer/185833?hl=zh-Hans) 为准。也可以换用你自己的另一个 SMTP 发送邮箱。

## 5. 配置 GitHub Actions Secrets

打开仓库 → Settings → Secrets and variables → Actions → New repository secret，逐个新建：

| Name | Gmail 示例值 |
|---|---|
| `EMAIL_HOST` | `smtp.gmail.com` |
| `EMAIL_PORT` | `465` |
| `EMAIL_USER` | 你的发送 Gmail 地址 |
| `EMAIL_PASSWORD` | Google 生成的应用专用密码 |
| `EMAIL_TO` | `muluzzh00@gmail.com` |

不要填到普通 Variables 或源码。465 使用隐式 TLS；587 使用 STARTTLS，两者都校验证书。代码不打印密码、不关闭 TLS 校验。

进入 Settings → Actions → General，允许本仓库运行 GitHub Actions。Workflow permissions 允许 **Read and write permissions**，用于写入 `monitor-state` 分支。若组织政策禁止写分支，需要仓库管理员开放该权限；程序会报错并停止发信，而不是丢失去重记录后继续运行。

## 6. 测试邮件和首次云端运行

1. 打开仓库的 Actions 标签。
2. 左侧选择 **2027 Admission Monitor**。
3. 点击 **Run workflow**，选择默认分支 `main`。
4. mode 先选 `test-email`，再点击绿色 Run workflow。
5. 在 Gmail 中确认收到“【测试】【2027推免监控】邮件连接测试”；同时查看垃圾邮件和所有邮件。
6. 再次 Run workflow，mode 选 `run`。
7. 查看 Run monitor 步骤和 Summary；全新数据库首次运行先建立 baseline，仅对明确在 2026-09-10 起发布、同时含 2027 和推免/直博关键词的高度相关通知合并发送一次。历史记录只保存、不批量补发。
8. 再手动运行一次 `run`：没有网站内容重要变化时，普通新通知邮件数量应为零。到达截止提醒或日报时间时，这些独立类型的邮件仍可能按规则发送。

测试邮件“SMTP accepted”表示服务器接收，不保证一定进入主收件箱。实际收件确认仍要查看 Gmail。

## 7. 电脑关机后是否运行

成功部署后，GitHub 云端运行和你的电脑无关。关机、睡眠、断网、关闭 Codex 都不影响计划任务。

工作流 `17 * * * *` 使用 UTC，每小时第 17 分钟触发；北京时间也是每小时第 17 分钟。选择非整点减少排队影响。**GitHub Actions 不是实时调度服务，平台繁忙时可能延迟甚至丢弃定时任务，不能承诺精确每 60 分钟或零漏报。** 这是 GitHub [官方说明](https://docs.github.com/en/actions/how-tos/troubleshoot-workflows) 中的限制。程序下次运行会补抓最近列表，提醒按剩余时间触发。

工作流必须存在于默认分支。确认 Actions 页面出现事件为 `schedule` 的记录，而不仅是 `workflow_dispatch`；观察至少两个连续小时。程序输出 `checked_at` 和 `http_requests`。只上传代码或手动运行成功一次，都不代表定时调度已经验证。

私有仓库消耗账号的 Actions 免费配额，额度随账号方案变化；请查看 GitHub Billing / Actions usage。此短期项目不用付费 LLM 或数据库。公共仓库的标准托管 runner 有不同计费规则，以 GitHub 当前账号页面为准。

## 8. 状态持久化与去重

选择 JSON + 独立 Git 分支，而非 SQLite + 临时 Runner：短期数据量小，JSON 可直接审阅；不依赖会过期/被淘汰的 Actions cache；每次都恢复权威状态，然后以 Git 原子提交保存。

`monitor-state/state.json` 保存：

- 已发现通知、`publish_date`、允许为空的 `publish_time`、`first_seen_time`、`last_seen_time`、来源、相关度和日期原句。
- 原文 URL、别名 URL、内容指纹、版本和通知状态。
- `reminded_72h`、`reminded_24h`、`reminded_6h`。
- 每日发送状态 `daily_reports`。
- 邮件事务 `deliveries` 和各页面健康状态 `health`。

工作流使用统一 concurrency group，禁止取消运行中的任务，保证只有一个程序修改状态。恢复失败、权限不足、文件损坏、Git push 失败都按故障处理，禁止偷偷创建空状态再发邮件。

先去重，再判断时间。相同 URL + 相同标题（忽略空白）只更新最后发现时间，直接跳过相关性分析和详情页；同校完全相同标题的其它 URL 记为别名，也不重复抓详情、发普通邮件。不同学校不会仅因标题相同合并。查询参数中的跟踪标记和已知 VSB content.jsp 地址会规范化。标题变化且满足本轮时间规则时才重新分析；标题不变、仅正文内部修改的截止日期不会被本轮机制自动发现，需人工查看原文。

默认每个配置列表仅取靠前最多 40 条（`crawler.max_notices_per_source`；单个 sites 条目可用 `max_notices` 覆盖），最多 3 页，达到数量上限即停止翻页。全新状态按来源建立一次 baseline，失败来源下次成功时再建立自己的 baseline；升级已有状态直接沿用已记录通知，不重新发送。

每次使用实际运行的北京时间减去 `monitoring.lookback_minutes: 75`，不用固定整点。精确发布时间必须在闭区间 `[now - 75 分钟, now]` 内；只有日期时必须是今天且数据库首次发现，设置 `potential_new_notice=true`。精确时间保留秒/微秒和时区，日期不擅自补成 00:00。新候选的详情页提供更精确时间时，会再校验窗口。日期完全缺失的相关新条目只查一次详情；仍无法确认时保留并列入日报待核实，不发普通新通知。首次发现时间始终保留，后续只更新最后看到时间。

配置为 `interval_minutes: 60`、`lookback_minutes: 75`、`initial_scan_mode: baseline`、`baseline_notify_since: '2026-09-10'`。15 分钟重叠由数据库消除重复；超过重叠时长的调度空档仍可能漏过有精确时间的通知，可按实际延迟增大 lookback。`initial_lookback_days` 仅供相关性分类识别明显旧年份，不再决定普通新通知是否发送。

baseline 仅对可确认发布日期在 2026-09-10 至今天、且同时明确涉及 2027 和推免/直博的高相关通知提醒，最多合并为一封普通新通知邮件。其它历史公告存入 baseline，之后不再当新公告。学院来源加 5 分，推免/直博关键词加 5 分，2027/接收推荐免试/直接攻读博士加 4 分，报名/申请等加 3 分，目标学科加 2 分，招生词加 1 分。指定学院的推免/直博通知优先为五星。

### SMTP 不确定情况

SMTP 服务器和 Git 仓库之间没有共同事务，无法数学保证“必达且恰好一次”。本项目在发信前将发送预约提交到远端。若发信后进程崩溃或 SMTP 回执丢失，记录会停留在 `sending` / `uncertain`，程序 **不会自行重发**，并使工作流失败、在健康日报提示。

这样优先满足不重复发信，但不确定状态需要人工核对 Gmail：打开 `monitor-state/state.json`，找到对应 batch / event。已收到则确认状态为 `sent`；确认未收到时，可删除该 batch 及所有 `batch` 指向它的事件记录，下一轮重新排队。修改前下载备份并暂停工作流，修改后手动运行一次。不要仅删除整个 state.json 或整个分支，那会丢失全部去重记录。

确认持久化：在分支下拉列表选 `monitor-state`，应看到 state.json 和连续提交；两次 Run 的新通知计数不应重复。Artifacts 用于审计报告，**不是权威状态恢复源**。

## 9. 日期与提醒

日期全部按 Asia/Shanghai 显示。标题中的“2027”是招生年份，绝不能拿来当报名日期的年份。省略年份时只允许使用已确认的文章发布时间年份；无法确认年份、具体时刻、多个批次冲突时，保存原句并标 `uncertain`。只给日期、不写时刻时不擅自填 23:59。

每个确定的关键日期字段可以独立保存，整体状态仍可能 uncertain。提醒取已确认的报名截止与材料截止中较早的一个。未来不足 24h 红色、不足 72h 橙色、不足 7 天黄色，其余绿色，未知灰色。已截止不再发送截止提醒。

重要通知在进入 72h / 24h / 6h 窗口后分别最多提醒一次。若首次发现只剩 5 小时，新通知邮件即为紧急提示，同时标记已跨过的阈值，不在同一轮连发三封补提醒。图片、PDF、Word 附件中的日期不会伪造提取结果，邮件会提示人工查看官方附件。正文选择器失效也会提示，不将不完整内容当作可靠截止时间。

## 10. 每天 22:00 健康日报

北京时间当日 22 点之后首次成功执行时，尝试发送一次日报（正常约 22:17）。如果整晚 GitHub 没调度成功，则不能在那一晚送达日报；次日不会冒充补发前一天的完整日报。

日报统计北京时间当天全部运行，不限最近 75 分钟：当日发现的相关新记录、高优先级通知、所有保存记录中的即将截止事项，以及当日累计网站故障。故障写入持久化 `daily_stats`，即使晚间已经恢复，日报仍列出曾失败 URL、次数、错误及最后失败时间。普通通知时间窗口不限制既有截止提醒。另列发布时间待核实公告。缺失发布时间或详情读取失败会显示部分正常。成功检查学院仅统计至少一个学院核心页面成功，不能仅靠校级页面把学院标成成功。

## 11. 查看结果和错误

- Actions → 对应运行 → Summary：各页抓取数、匹配数、错误。
- Run monitor 的日志：哪所学校成功、连接错误、403/404、超时或选择器失效。
- 运行页面下方 Artifacts → `monitor-report-运行号`：下载 `latest.json`、`health.html`、`monitor.log`。
- 红色运行不一定全部失败，一个页面失败时仍检查其他页面并发送可用结果。失败页面不可解释为“今天没有通知”。
- 在 GitHub 个人 Settings → Notifications → Actions 启用工作流失败邮件；若 SMTP 本身坏了，无法指望同一 SMTP 通道报告它自己的故障。

不会绕过验证码、登录或安全机制。robots.txt 明确禁止时停止该站抓取；规则服务临时不可达时保守报错。404 表示未提供规则；某些 CMS 对不存在的 robots.txt 返回首页，机器人解析器会忽略非规则文本。每站有合理间隔、超时和有限指数退避重试，403/404 不无限重试。分页最多 3 页且默认最多 40 条，任一上限达到即停止；需要时可按来源调整数量。

## 12. 本地安装与运行

需要 Python 3.12、Git。在项目文件夹打开终端：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
.\.venv\Scripts\python.exe main.py --test-email
.\.venv\Scripts\python.exe main.py --run-once
```

本地运行使用 `state/state.json`；云端使用状态分支，两套默认独立。不要同时把两个实例连接到同一个状态分支。若只是验收而不发邮件：

```powershell
python main.py --run-once --console --state-dir test-state --report-dir test-reports
python main.py --run-once --console --state-dir test-state --report-dir test-reports-2
python -m pytest -q
```

`--console` 强制指定独立状态目录，避免将模拟已发送状态误用于生产。不要上传上述 `test-state/`、`test-reports/`；测试完可手动删除。对普通收件邮箱的真实测试仍需要 Secrets 或 `.env`。

退出码：0 表示完成；2 表示部分页面故障/邮件待核实；1 表示配置或整体运行失败。时间窗口之外返回 0，且不创建 HTTP/SMTP 客户端。

## 13. 增删页面、改关键词

编辑 `config/sites.yaml`：复制同校条目，给新条目不同 `id`，修改 `page_name`、`list_url`、`domain` 和经过测试的选择器。`source_level` 必须为 `college` 或 `university`。`university_domain` 限制所有链接留在该大学。删除条目或设 `enabled: false` 即暂停该页；不要为掩盖故障而禁用必要的唯一核心源。

先用真实页面测试标题、日期、链接，再上传。普通静态页使用 `generic`；南大嵌入 JSON 页使用 `nju`。不同页面模板应在 `crawlers/custom/` 加专用类并注册。不要把仅有导航、已过期空栏目或只包含首页新闻的入口当作招生列表验收成功。

编辑 `config/settings.yaml` 的 keywords；强词、行为词、专业词、招生词分组独立，**不要求 2027 + 推免 + 建筑同时出现**。排除词仅用于明显的转专业、职称、导师资格等无关内容；不要添加过宽的排除词。

## 14. 修改结束时间、暂停和恢复

默认时间：2026-09-10 至 **2026-09-25 23:59:59 Asia/Shanghai**。

每次启动 Python 先检查时间；HTTP 请求（含 robots、重试、跳转）之前再次检查。超过结束时间输出：

```text
Monitoring period has ended.
```

不访问学校，不发测试邮件。工作流另有标准库时间门禁，结束后跳过 pip、状态恢复和实际监控。GitHub 仍可能启动很短的工作流外壳，这是调度平台行为；如果也不想有外壳执行，请在 Actions 中禁用该工作流。

修改时间只需编辑 settings.yaml，不用改 Python。`interval_minutes` 记录预期频率，GitHub 调度实际由 workflow 的 cron 控制；改频率时必须同时修改这两处。

暂停：Actions → 2027 Admission Monitor → 右侧 `…` → Disable workflow。

恢复：Enable workflow，确认当前时间在设置窗口内，再手动 Run workflow。保留 `monitor-state` 分支才能延续去重和提醒状态。过期后要重新启动，先调整 start_date / end_date 和招生年份、查询范围；跨年度建议新建项目并有意识地初始化新状态。

## 15. 部署验收清单

云端也兼容已有的 `SMTP_USER` / `SMTP_PASSWORD` Secrets；若未设置 `EMAIL_HOST` / `EMAIL_PORT`，默认使用 Gmail 的 `smtp.gmail.com:465`。其他发送邮箱请显式设置服务器与端口。

上传 `main` 分支后，`Project tests` 自动运行单元测试。尚未配置邮箱时，可手动运行 `Cloud crawl acceptance`：连续两轮真实抓取，恢复独立测试状态，保存报告，检查第二轮普通事件是否重复，并明确报告失败页面。该工作流只模拟邮件。生产通知与状态分支仍须使用 `2027 Admission Monitor` 单独验收。

1. 代码和 `.github/workflows/monitor.yml` 在默认分支。
2. 五个 Secrets 已配置，真实测试邮件到达 Gmail。
3. 手动运行两次，普通同通知没有重发。
4. `monitor-state` 正常恢复和持续提交。
5. 至少观察两次实际 schedule 云端运行。
6. 逐学院核心源与校级源成功；失败要修复或明确标注。
7. 日报及三档提醒的自动化测试通过；生产首个日报需真实观察。

本地报告中的通过项不能替代尚未完成的云端验收；本系统也不能保证网站不封禁、附件内容一定可解析或学校不会临时更改时间。报名以官方原文为准。
