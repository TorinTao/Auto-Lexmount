# Auto Lexmount · 快乐参赛流水线

一个轻量的活动工作流 Agent：读取官网 → 提炼规则 → 生成并筛选 ideas → 生成 Python → 测试/修复 → 打包材料 → 按配置填写和提交表单。

第一版把自动选题限定为「读取 1–3 个公开网页，生成带来源的摘要清单」。活动规则必须有原文引用；测试验证输出格式、来源覆盖和运行结果。摘要语义是否准确仍需核对。

仓库包含 Agent、网页控制台、展示页源码、测试和工具脚本。本文中的 `runs/`、截图及历史验证记录属于本地运行产物，不随源码上传；新环境需要自行配置凭据并运行流程生成。

## 网页控制台

```bash
python -m autolex serve
# 自定义端口与运行目录：
python -m autolex serve --port 8766 --runs runs
```

本机已经配置 DeepSeek 的情况下，使用下面的启动器加载被 Git 忽略的 `.env`，并优先使用项目的 `.venv`：

```bash
./scripts/autolex.sh doctor
./scripts/autolex.sh check-model
./scripts/autolex.sh serve
./scripts/autolex.sh run --out runs/deepseek-live
```

新环境可先执行 `python -m venv .venv` 和 `.venv/bin/python -m autolex configure-deepseek`，通过不回显的终端输入设置密钥。该命令创建权限为 `0600` 的 `.env`，拒绝覆盖已有配置；不会把密钥打印到终端。

启动后打开 http://127.0.0.1:8765 。控制台与 Python API 同源，无需 npm 安装或前端构建。

- 新建离线演示或真实任务，选择停止阶段和修复次数。
- 每 2 秒读取实际阶段状态，浏览历史任务并继续未完成任务。
- 查看选题、生成代码、每轮测试、成果摘要和投稿回执。
- 下载作品包、说明和测试结果。
- 查看服务端配置状态；API 密钥不进入浏览器。

界面支持窄屏布局、键盘切换标签页、断线提示和任务错误提示。仅绑定本机回环地址，并检查 Host、Origin 和请求 token。它是本地开发控制台，不应直接代理到公网。运行中的服务关闭后，刷新可识别中断状态并重新发起恢复。

配置服务端发布资料后，网页可直接发布并提交指定作品；也支持下面的 CLI。演示产物仍明确标注，不能作为真实云端证据。

前端测试：`node tests/frontend.test.cjs`（Node.js 22+）。使用 DOM 替身测试交互逻辑，不替代浏览器布局检查。本机监听和真实 HTTP 接口已验证；已用 Chrome 156 检查桌面和手机布局、标签切换和任务弹窗，没有页面异常或横向溢出。截图在 `runs/qa/`。

## 立即运行演示

需要 Linux / WSL、Python 3.11+。基础流程只有标准库依赖。

```bash
python -m autolex demo --out runs/demo
python -m autolex status runs/demo
python -m unittest discover -s tests -v
```

查看 `runs/demo/submission.md`、`output.json`、`tests.json` 和 `submission.zip`。演示使用固定网页和固定程序，**不调用模型或 Lexmount，不是云端实践证据，也不能投稿**。

## 真实模式

复制 `.env.example` 到自己的本地配置后，在终端导出变量，或使用上面的启动器。原始 `python -m autolex` 不自动读取 `.env`，可显式加 `--env-file .env`（放在子命令前）。不要提交任何凭证。

- `LEXMOUNT_API_KEY`、`LEXMOUNT_PROJECT_ID`：同一个项目的云端凭证。
- `LEXMOUNT_BASE_URL`：中国区默认 `https://api.lexmount.cn`。
- 或设置 `LEXMOUNT_FETCH_CLI` 为已认证的官方 CLI 的绝对路径。
- `LEXMOUNT_FETCH_ENGINE=http`：当前预设。实测默认浏览器引擎返回 502 超时，HTTP 引擎能提取活动页；CLI 先生成云端 DOM 快照再提取。需要 JavaScript 渲染的网页应按服务可用情况选择 `chrome_cdp` 等引擎。
- `MODEL_API_KEY`、`MODEL_NAME`、`MODEL_BASE_URL`：兼容 Chat Completions 的模型服务；base URL 应包含 `/v1`（若服务要求）。
- DeepSeek 预设使用 `https://api.deepseek.com` 和 `deepseek-flash`；`MODEL_JSON_MODE=true` 启用结构化 JSON 输出，`MODEL_MAX_TOKENS=16384` 限制单次输出，`MODEL_THINKING=disabled` 避免简单结构化任务耗尽推理输出额度。截断响应会报错，不会当作成功。模型名和接口依据：[DeepSeek 官方文档](https://api-docs.deepseek.com/)、[JSON 输出](https://api-docs.deepseek.com/guides/json_mode/)。

代码执行需要可用的 Docker daemon 和预先下载的镜像：

```bash
docker pull python:3.12-slim
python -m autolex doctor
python -m autolex run --out runs/live --until rules
python -m autolex run --out runs/live
```

同一路径重新执行会继续未完成阶段；已完成阶段不重复调用 API。修改已完成的证据文件会被拒绝，需要新建运行目录。`doctor` 只检查本地配置，不声称 API 或 Docker 已连通。

通用模型默认最多调用 10 次，DeepSeek 预设通过 `MODEL_MAX_CALLS=20` 配置为 20 次（计数跨恢复保留），一次测试阶段最多修复 3 轮。真实模式会逐字核对引用、校验结论引用 ID，并调用模型按选题验收标准复核；模型辅助验收不等于人工验证。重试历史保存在 `test-history.json`，不会包装失败结果。每次程序执行最多 45 秒。容器无网络、无 API 密钥、只挂载当次执行目录，并限制进程数、内存、CPU、输出文件大小。支持的项目不安装第三方依赖。

这不是按人民币计费的预算管理器；不同服务的 token 和浏览器费用仍按各自实际用量计算。失败阶段重新执行可能再次产生抓取费用。

## 投稿

网页表单需要实际查看后配置，项目没有猜测官网字段。安装可选依赖：

```bash
pip install -e '.[browser]'
```

复制 `examples/submission.example.json` 为本地配置，补全：

- 已登录的 Lexmount `context_id`（需要登录时）；登录/验证码由本人完成。
- 真实作者 `authors` 和已上传、可公开访问的材料链接 `artifact_links`。
- `fields`：字段名到 Playwright locator 的映射。内置字段为 `title`、`description`、`authors`、`artifact_links`；其余文本字段放入 `extra_values`。
- `submit_selector`：提交按钮；`success_selector`：提交后出现且包含回执文本的元素。

先填表并截图预览，或显式发送：

```bash
python -m autolex submit runs/live --config my-submission.json
python -m autolex submit runs/live --config my-submission.json --send
# 也支持从读取官网到提交的一条命令：
python -m autolex run --out runs/live --submit-config my-submission.json --send
```

真实提交必须满足：完整 live 工作流、原始 Lexmount 证据、测试通过、材料校验和一致、截止时间明确且未过期、作者和材料链接已配置。预检查只检查链接格式，不验证外部附件访问权限。日期由模型从官网提取，应在首次投稿前核对原文。

通用 submit 适配器只填文本字段；特殊上传、勾选授权和复杂动态控件需要根据实际表单扩展。通用 submit 适配器不会自动上传材料；专用 release 流程支持 Yours 上传。两者均不代填身份或绕过验证码。表单和 SDK 接入需要在有网络与登录状态的环境实测。

提交前持久化 `sending` 状态，超时后标为 `unknown` 并阻止重试。此时需去官网核实，不能简单重跑。成功后保存回执和截图。浏览器会话在正常或异常退出时释放。

## 文件结构

| 文件 | 用途 |
| --- | --- |
| `autolex/clients.py` | Lexmount 提取与模型 API |
| `autolex/workflow.py` | 阶段推进、恢复、规则校验、代码修复和打包 |
| `autolex/runner.py` | 容器执行与固定输出契约校验 |
| `autolex/submission.py` | 表单适配、提交前检查、回执与防重复 |
| `autolex/demo.py` | 明确标记的离线演示数据 |
| `autolex/server.py` | 本地网页 API、后台任务和文件下载 |
| `autolex/web/` | 无构建依赖的响应式网页控制台 |
| `tests/` | 模块、失败恢复、HTTP 协议与 CLI 集成测试 |

运行目录中 `official-page.json` / `input.json` 保存来源与请求 ID，`attempts/` 保存每轮代码和日志，`manifest.json` 保存打包文件的 SHA-256。运行目录可能包含投稿个人信息，请按自己的公开范围分享；zip 仅收录指定作品文件，不包含环境配置和浏览器截图。

## API 依据

- https://browser.lexmount.cn/docs/webfetch/reference/all-in-one-extract
- https://browser.lexmount.cn/docs/python-sdk/quickstart

离线/模拟测试不等于真实云 API 或投稿验证。真实运行需要上述外部条件齐备。

2026-11-07 验证记录：72 项 Python 测试、11 项前端逻辑测试通过。真实工作流 `runs/live-recheck` 已完成规则读取、选题、DeepSeek 代码生成、Docker 执行、引用校验、模型辅助验收和材料打包，产出 9 条带引用的要点及 3 条结论；另做 2 次真实容器复跑，输出一致。浏览器桌面和手机检查通过。详见 `tests/verification.json`、`tests/live-workflow-verification.json` 和 `tests/browser-verification.json`。

控制台当前由用户会话服务 `autolex-dashboard` 运行，可用 `systemctl --user restart autolex-dashboard` 重启。该服务是本次会话创建的临时 systemd 单元，不是开机自动启动配置；服务不存在时仍可用 `./scripts/autolex.sh serve` 启动。

2026-11-07 已完成真实投稿：Auto Lexmount 第 1 版，收件编号 `e15da2e1-f41e-4b96-beae-1953f1dbd6fb`。首发材料保存在 Yours（访问码方式分享），上传与提交过程截图、回执核对记录在 `runs/submission-proof/`。这只是收件成功，不代表获奖。首发材料是提交时的固定版本；后续质量实验另存，未冒充为首发已验证内容。

## 本机 Docker 服务

已安装 Ubuntu 发行版的 Docker 26.1.3，systemd 服务为 `docker`，已启用自动启动。`usr` 已加入 docker 组；已有终端需重新打开或执行 `newgrp docker` 才能取得新组权限。控制台已按新权限重启。

Docker Hub 拉取使用当前机器的 `http://127.0.0.1:7890` 代理，配置位于 `/etc/systemd/system/docker.service.d/autolex-proxy.conf`；代理地址变化时需调整配置并重启 Docker。

`python:3.12-slim` 已下载，实际验证了普通用户运行、只读根目录、禁用网络和挂载目录写入，结果见 `tests/docker-verification.json`。同时修正了执行器的文件大小限制：Docker 的 `fsize` 单位为字节，现为 2,000,000 字节。


## 多作品迭代与视觉检查

现在可以指定方向，并在独立目录中按反馈重做同一个作品。新版本保留原选题和验收标准，旧版本的失败记录不覆盖。

```bash
./scripts/autolex.sh run --out runs/my-v1 --brief '比较两个官方文档，整理中文指南'
./scripts/autolex.sh run --out runs/my-v2 --revise-from runs/my-v1 --feedback feedback.txt
./scripts/autolex.sh audit runs/my-v2 --out runs/my-v2-audit
# 三个预设方向；每个方向最多三轮，每轮仍受模型调用预算限制
.venv/bin/python scripts/quality_lab.py --prefix experiment --rounds 3
# 使用已经启动并开放 CDP 的 Chromium；不自动安装或启动浏览器
.venv/bin/python scripts/visual_qa.py --cdp http://127.0.0.1:9229 --runs my-v2
```

输入变化检查包括原样复跑、调换页面顺序、移除一页正文、清空全部正文，以及用无关文字替换正文。后三项必须在写出 output.json 前明确拒绝；意外崩溃、容器超时或沿用旧结论均不算通过。常见中文验收中的要点总数、结论数量由程序核对；语义验收得到实际字数与独立源码、抓取日志，减少格式误判。代码语法和规则引用首次验证失败时反馈重试一次，记录失败响应，仍受总调用预算限制。

每个新作品包含 `index.html`：可直接打开的中文报告、引用跳转、可展开源码和带用途说明的文件目录。`quality.json` 保存输入变化检查。浏览器脚本保存桌面、手机、源码、测试与目录截图，自动检查溢出和页面异常。**截图采集不等于视觉验收**：本轮图片由 Codex 看图检查，发现的问题写入版本反馈；当前 DeepSeek 文本接口未配置自动图像理解。

实验覆盖 CSV/JSON 选择、Git 撤销、SQLite 备份三个方向，保存 v1/v2/v3 的独立目录。具体通过情况、模型调用次数、代码与目录检查、截图见 `runs/quality-lab/summary.json` 和对应视觉报告。小样本前后对照用于发现问题，不能证明对任意选题都有同样成功率。


## 2026-11-08 三轮打磨

1. **恢复与验收**：模型请求发出前持久化调用计数，进程被强制结束后仍受预算限制；保存最新修复代码及校验值，恢复时只处理最新失败原因；保留历史测试且不重复追加同一失败。数量验收识别中文范围、至少和至多。规则引文错误给出真实原文片段，重启后继续使用上次反馈，仍保持精确引用校验。
2. **控制台使用流程**：显示作品名称、来源和依据数量、调用预算、执行记录及下一步；直接打开隔离的 HTML 预览；“按反馈改一版”继承选题、来源和已有代码，在独立目录生成新版本。手机弹窗保持提交按钮可见，运行模式说明与实际模式一致。
3. **真实复跑与沉淀**：更严格的检查发现旧 CSV/JSON、SQLite 作品在无关正文上未正确拒绝。修复后的 CSV/JSON、SQLite 以及新选题 pathlib 均完成真实 Lexmount 提取、DeepSeek 生成/验收、Docker 执行和打包；调用次数分别为 3、7、5（SQLite 包含 4 次失败的规则提取，记录保留）。三个新版本另做独立容器审计，不覆盖原作品。

模块与集成回归：84 项 Python 测试、15 项前端逻辑测试通过。浏览器验证实际预览路由、桌面/手机布局和“反馈→新版本→父作品保留”流程。输入变化检查只覆盖这五类确定性场景，模型验收和静态源码盘点不能证明任意代码或事实都正确。

- 完整报告：`runs/polish-20261108/index.html`，机器可读记录：`tests/polish-verification.json`。
- 新作品：`runs/polish-csv/`、`runs/polish-sqlite/`、`runs/polish-pathlib/`。
- 前后审计与截图：`runs/polish-20261108/`；源码和本轮成果包：`dist/auto-lexmount-polished.zip`。
- Agent 本体的原投稿继续保留；生成作品现在使用下述独立发布投稿流程，各自拥有材料链接与回执。

复验操作（需要已配置环境、Docker 和已启动的 CDP 浏览器；Playwright 是视觉检查的额外开发依赖）：

```bash
.venv/bin/python -m unittest discover -s tests -q
node --test tests/frontend.test.cjs
./scripts/autolex.sh audit runs/polish-csv --out runs/my-independent-audit
.venv/bin/python scripts/visual_qa.py --runs polish-csv polish-sqlite polish-pathlib --out runs/my-visual-check
# 会创建两个标注为 DEMO 的本地任务，以实际点击验证改版流程
.venv/bin/python scripts/dashboard_qa.py --out runs/my-dashboard-check
```


## Agent 自动提交它生成的其他作品

Agent 本体与生成作品是两类独立投稿对象。`release` 只读取指定运行目录：标题来自该作品的 `spec.json`，网页与代码来自该作品的输出和源码，发布包不包含 Agent 仓库。每件作品的 Yours 链接、访问码、访客核验截图和官方收件编号都存回自己的运行目录。

复制 `examples/release-profile.example.json` 为本地 `.release-profile.json`，填写真实作者、联系邮箱和已经登录 Yours/活动官网的 Lexmount Context ID；配置文件保持私有。发布使用已登录的官方 browser-cli 与 Playwright，不需要把浏览器凭据提供给 DeepSeek。

```bash
# 已完成作品：先生成本地发布包；不产生远程写入
./scripts/autolex.sh release runs/my-work --profile .release-profile.json
# 同一命令完成独立上传、访问码分享、无登录访客核验和真实投稿
./scripts/autolex.sh release runs/my-work --profile .release-profile.json --send
# 新作品从生成开始一路执行到真实投稿
./scripts/autolex.sh run --out runs/new-work --brief '一个独立的公开资料整理任务' --release-profile .release-profile.json --send
```

网页在服务端设置 `AUTOLEX_RELEASE_PROFILE` 后，提供“发布并提交这件作品”；新建真实任务时也可以勾选“通过测试后，自动发布并提交这件新作品”。网页显示该作品自己的分享链接与收件编号，离线演示不能投稿。

发布状态独立保存在 `release-state.json`。发布包包含可访问报告和可直接阅读的该作品源码、抓取证据、测试记录；作者联系信息仅写入活动表单。发布后的恢复沿用已上传文件，不会因为模板变化重打包替换。跨版本的相同标题和来源会命中重复投稿检查；该检查不能判断语义相同但改写了标题与来源的任务，仍需遵守活动对独立作品的定义。

Yours 归档上传是异步处理：以创建接口或完成状态的返回值确认发布结果，不以页面是否跳转判断成功。远程写入前保存状态；若结果未知则停止重试。已在 Yours 的“My works”中核对到作品时，可通过以下命令验证源码、接续同一个链接：

```bash
./scripts/autolex.sh recover-release runs/my-work --profile .release-profile.json --url https://yours.lexmount.cn/artifact-site/s/已核对的作品标识
./scripts/autolex.sh release runs/my-work --profile .release-profile.json --send
```

这个恢复入口只处理“发布未知”，不能把“投稿未知”重置成可再次发送。后者必须先在比赛官网核对收件记录。首次两件发布实测暴露了跳转判断问题，保留其恢复过程；之后新增选题用于验证修正后的完整链路。

当前生成器仍聚焦公开资料整理与带来源的中文报告，不是任意类型应用的通用开发平台。DeepSeek 负责选题、代码生成、修复与模型辅助验收；工作流负责抓取、执行、发布和投稿。作品展示采用固定前端报告模板，截图保存和访客核验不代表自动视觉评分。

### 独立投稿最终实测

2026-11-08：最终 107 项 Python、16 项前端测试通过；5 件最终作品独立复验的 25 项容器检查全部通过。CSV/JSON、SQLite、URL 解析和 Git 四件生成作品已分别收件，具体链接、访问码、调用计数与回执在 `runs/polish-20261108/publications.json`。前三件记录了发布适配调试和恢复，Git 作品在修正后的单条命令中完成生成、自动修复、发布、访客核验和投稿。

## 七作品受控迭代实验

`examples/batch7.json` 固定了集合、时区、HTTP 缓存、CSS 布局、Promise、SQLite 外键事务、Git 工作区七项任务。它们是公开文档资料工具，仍在当前 MVP 的任务范围内，不代表七类任意应用开发能力。

```bash
# 真实调用模型和 Lexmount，生成作品但不发布
sg docker -c '.venv/bin/python scripts/benchmark.py --round my-baseline'
# 复用已捕获的来源，隔离网页变化；每轮使用新的名称
sg docker -c '.venv/bin/python scripts/benchmark.py --round my-replay --reuse-evidence'
# 独立压力检查，输出必须放在原作品目录之外
sg docker -c '.venv/bin/python scripts/adversarial_audit.py runs/b7-my-replay-collections --out runs/my-audit'
```

每个任务保留模型调用数、API 报告 token 数、阶段耗时、获取资料耗时、容器执行记录和原始任务校验。运行目录保持不可变，实验遥测另存于 `runs/batch7-lab/`。`scripts/benchmark_report.py` 为本次各轮生成对比 JSON 和可浏览的作品目录。

本次改进把原 brief 的明确数量置于模型生成验收标准之上；中文“仅使用/只使用/只用/来源限定为”后、句号或分号前列出的 URL 保留为完整资料集合（最多三页）。这不是通用自然语言解析器，其他约束仍需要模型评审及独立复核。所有候选选题都应覆盖同一完整任务，不能把任务拆小后挑最容易的一部分。

鲁棒性契约升级为 v3：原样复跑、反转页面、清空正文、无关正文之外，新增空白格式等价、逐个移除来源、逐个清空来源和重复来源拒绝。单页八项、双页十项隔离检查。无效证据必须明确拒绝，意外异常不算通过。空白变化只允许引用空白不同，不允许摘要或事实改变。

生成与评审现在要求短引用支撑整条摘要、结论的每个事实由其引用要点支撑；删减要点时同步重建结论。修复返回完全相同的代码会被拦截并给出具体反馈。模型评审仍可能遗漏事实问题；独立复核记录和截图是额外证据，不是官方评分或正确性证明。

新版复用网页快照，总耗时不能直接当成速度提升；模型调用数、模型耗时和资料获取耗时应分开看。七个随机生成样本不足以得出统计意义上的性能结论。本轮实验不执行投稿。

后续的引用修订轮增加了 `autolex/citations.py`：只向 DeepSeek 提供各要点的短摘录、摘要与结论，不提供邻近正文，逐项列出 `unsupported_clauses`。缺失审查项、重复 ID 或“支持=true 但仍列出缺失事实”都不能通过。引用检查先于耗时较多的容器输入扰动检查，失败时先修正文案和引用，避免反复执行已经无意义的完整测试。它仍是模型辅助判断，并非形式化语义证明。

`scripts/citation_audit.py` 可以对完成作品进行同样的外部复核。`scripts/benchmark.py --parent-round improved --feedback runs/batch7-lab/refinement-feedback.json --round refined --reuse-evidence` 使用原作品源码及具体反馈生成新目录，保留父作品。第三轮属于修订，不应与从零生成的调用量直接比较。

超长字面引用的修复反馈现在包含实际词数，以及同一来源的 25 词首尾候选摘录（`quotation_hints`）。它们只是机械提取的建议，不会自动改写生成程序，也不保证独立语义完整；生成器仍须调整摘要，后续引用、语义和容器检查照常执行。

对于原 brief 明确规定要点/结论数量的任务，`acceptance_authority=brief` 将整段原始要求直接绑定为验收契约。模型选题中的描述性建议不能额外变成必选条件；未提供明确契约的普通任务仍使用生成的验收标准。修订使用父任务的深拷贝，避免修改父任务元数据或破坏断点恢复。

实验驱动器的 `--resume-existing` 只用于已经检查过的中断任务。它保留累计模型计数和遥测，不重复已完成阶段；恢复样本的总耗时包含中断时间，未返回请求的 token 用量可能缺失。独立压力测试可用 `--workers 1/2/3` 在互不共享目录的进程中执行；它的延时不作为模型生成性能指标。

最后的收尾补充：引用检查也覆盖页级摘要，防止要点已修正而页首仍残留旧说法；修复提示带原文邻近上下文，帮助找到被摘录遗漏的选项标题。验收评审若“总体通过”却包含失败子项，会保存 `review-errors.json` 并要求评审重答一次，不能用 notes 直接覆盖布尔结果。真正的失败子项会把 requirement 与 reason 一起反馈，避免只给生成器一个泛泛的“不满足要求”。

本次实验最终保留七个主题作品，共经历 7+7+7 次批量构建/修订与 4+3 次定向修订，失败版本未覆盖。最终验证：123 项 Python、17 项前端逻辑、3 项真实模型小样本探针通过；七件最终作品的 68 项工作流输入扰动与 40 项外部复验通过；桌面/手机共 14 个视口检查通过，42 张作品过程截图及新任务界面截图已保存。模型探针不足以推断一般准确率，评审仍可能漏判或误判。

结果入口：`runs/batch7-lab/report.html`，最终作品选择：`runs/batch7-lab/final-runs.json`，哈希与成果包核验：`runs/batch7-lab/verification.json`。本轮未投稿；缓存、任务修订和一次调度中断都在报告中标注，不能把不同轮次的总耗时直接解释成速度提升。


## 自动截图评审与发布前修复（11 月 8 日后续更新）

真实任务可以启用 `--visual-review`，或在服务端设置 `AUTOLEX_VISUAL_REVIEW=true`。
DeepSeek Flash 直接接收 PNG 图片；视觉请求和修复共用原任务调用预算。接口依据：
https://api-docs.deepseek.com/guides/vision/ 。此前“没有自动视觉评分”的描述是历史版本状态。

```bash
# 安装本机截图浏览器；Linux 还需要可用的中文字体与浏览器系统依赖
.venv/bin/python -m playwright install chromium
./scripts/autolex.sh run --out runs/my-visual-work --visual-review --brief '你的公开资料任务'
# 可以继续附加 --release-profile .release-profile.json --send，验收后自动投稿
```

默认使用 Playwright 本机 Chromium；也可用 `AUTOLEX_VISUAL_CDP=http://127.0.0.1:9229` 连接已有浏览器。
每轮采集桌面/手机的页首、来源、展开源码和文件目录共 8 张截图。模型逐张返回观察和问题，浏览器另外核对溢出、锚点和正文字号。
发现阻碍阅读的问题后，DeepSeek 自动提出受范围限制的字号、间距、宽度和列数设置，再重新截图验收，最多修复 2 次。
本轮支持表现层修复，不自动改写事实、隐藏引用或任意执行模型生成的 CSS/JavaScript；无法解决的问题阻止打包投稿。

`visual-review.json`、`visual-history.json`、`visual-theme.json` 和 `visual-evidence.zip` 保存结果、修改和截图。
通过记录绑定最终 HTML 哈希，投稿前重新核验；控制台测试页显示视觉验收状态。
这是抽样截图的模型辅助验收，不代表整个长页面或内容准确性已被证明。模型可能漏判，确定性浏览器检查不能被模型的通过结论覆盖。
独立故障夹具实测包括过小正文和过窄多列；不会作为真实参赛作品发布。


### 对已有作品做视觉回顾

`scripts/revisit_visuals.py` 读取七作品最终清单，校验父作品哈希，在 `visual-revisit-*` 独立目录继承原程序、输入、输出和内容验收记录，再执行视觉验收。
`scripts/polish_visuals.py` 把实际截图反馈交给 DeepSeek，创建 `visual-final-*`，应用受限制的样式建议后重新截图验收。
旧作品与发布回执保留，新目录不继承投稿状态。此次只复查表现层，内容验收记录明确标注继承，并另做容器复跑。
新增 `code_wrap`、`size_nowrap` 两个 0/1 设置，支持长代码自动换行和字节单位保持同行；旧主题仍兼容。
脚本固定本次目录名，有已有尝试时应先检查记录，不能覆盖历史。结果与前后截图见 `runs/visual-retrospective/report.html`。

### 按题材生成展示页

真实工作流现在在打包前调用 DeepSeek 生成 `design.json`：默认沿用浅紫底、白色卡片的单栏报告，只精修标题、导读和阅读顺序；用户明确指定时才切换蓝色技术图鉴、暖色编辑刊物或绿色笔记手册。它只能引用已有要点 ID，所有原文、结论和程序源码仍由可信渲染器完整保留。设计过程计入原有模型预算，最多一次格式修复；恢复时校验输入指纹并复用已有设计。

`autolex/design.py` 管设计契约，`autolex/presentation.py` 和 `autolex/report.css` 管版式。视觉检查包含首屏阅读目的与层次；发布包追加说明后再次检查布局，避免校验码等长文本撑开手机页面。设计记录可从工作台下载，并随 Yours 的源码页发布。

重新设计既有作品（保留原版本与验证数据，不重新投稿）：

```bash
.venv/bin/python scripts/regenerate_presentation.py --parent runs/原作品 --out runs/新展示版本
.venv/bin/python scripts/check_report_design.py runs/新展示版本 runs/检查记录
```

该操作重跑设计、截图评审和打包，沿用已校验的资料、程序与结果；不能声称重新抓取、重新编写或重新运行了作品程序。离线 demo 使用固定设计，不调用模型。
