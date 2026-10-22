# LLM Token Lab

大模型推理可视化实验室：React + TypeScript + FastAPI，通过 OpenAI-compatible API 实时观察 Token、真实概率与性能，支持双模型并行对比。

## 安装

需要 Linux、Python 3.11+、Node.js 22、npm；后台脚本需要 GNU screen。

```bash
git clone https://github.com/Chen27Guan/llm-token-lab.git
cd llm-token-lab
conda create -n py11 python=3.11 pip -y
conda activate py11
python -m pip install -r requirements.lock.txt
npm ci
npm run build
```

## 启动、停止与重启

```bash
conda activate py11
# 设置自己已部署的 OpenAI-compatible /v1 地址
export TOKENLAB_DEFAULT_URL=http://127.0.0.1:8000/v1
export TOKENLAB_PYTHON="$(command -v python)"
bash scripts/start.sh
curl http://127.0.0.1:38473/api/health
# screen -ls 查看 tokenlab-app；日志 var/server.log

# 停止
bash scripts/stop.sh
# 重启：停止后重新执行
bash scripts/start.sh
```

浏览器打开 http://127.0.0.1:38473 。端口可通过 `TOKENLAB_PORT` 修改。
不用 screen 时：`python -m uvicorn backend.app:app --host 127.0.0.1 --port 38473`。
前端开发可运行 `npm run dev`；vite.config.ts 中代理端口应与后端实际端口保持一致。
默认模型名 `Qwen3.6-35B-A3B`，默认 URL 为本机示例，不附带模型权重或运行服务。

## 配置模型

A/B 可分别直接填写模型名称或服务端路径（上游接受的 model 标识，不会自动加载或下载模型）。修改 API Base URL 后点击“应用新 URL”，创建该栏独立端点，不影响另一栏。
`/models` 用于补全与服务识别；不支持列表时仍可手动指定模型。服务类型识别用于处理 vLLM 参数。
“更换服务 / API Key”仅将密钥保存在后端当前会话内存，不写入数据库、日志、JSON 或浏览器存储。后端重启需重新添加端点和密钥。
默认 A/B 是同一 35B 模型的独立请求；选择不同服务/模型后才是跨模型对比。共享 GPU 并发存在资源竞争。

## 功能和真实性

- httpx 异步转发上游流，POST SSE 推送 start/delta/metrics/error/done，支持中止上游请求。
- 文本 / Token 视图、热力图、单 Token 检查、Top-logprobs、概率曲线、序列统计、性能曲线。
- 横向交互图：Token → Embedding/QKV → Attention → MLP/Residual → 候选概率。中央结构仅示意，不代表实测注意力权重、激活、层数、头数或计算时间。
- chunk 不是 Token；边界只取上游真实 logprobs。不按字符或 chunk 编造分词。
- P=exp(logprob)，条件选择概率不等于事实正确率；候选不重新归一化，无真实数据时显示不可用。
- Token ID 未返回时 N/A；同 chunk 共享观测时间，不推断逐 Token 生成时刻。
- TTFT 是后端请求开始到首个有效生成片段的观测延迟；非流式 TTFT 不可用。
- 数量优先 usage，其次 logprob 记录；vLLM 可用 /tokenize 时提供明确标记的估算，否则 N/A，不以 chunk 计数。
- 吞吐为输出 Token / 请求总秒数（含 TTFT）；没有真实时序时只展示 Chunk Interval，不冒充 TPOT。
- 真正并行 Arena、模型交换、对比图表、JSON 导出、SQLite 历史、深浅主题、暂停渲染。
- logprobs、usage、top-k、seed 能力探测；非标准参数经适配与验证后发送。

## 存储和构建

`var/` 保存本地数据库和日志，不提交 Git。随机 HttpOnly、SameSite=Strict cookie 隔离会话；浏览器仅存主题偏好。
为兼容不支持 SQLite 文件锁的存储，使用单进程互斥与单连接 StaticPool；禁止多 worker 或其他进程直接写历史数据库。
普通本地磁盘使用 `npm ci && npm run build`。网络文件系统可使用 `TOKENLAB_BUILD_DIR=/path/on/local/disk python scripts/build.py` 在本地磁盘构建，需预装 node 和 npm。

## 可选 SSH 反向转发

使用自己有权限的中继主机，没有内置网络地址、账户或凭据。

```bash
export TOKENLAB_RELAY_HOST=relay.example.org
export TOKENLAB_RELAY_USER=your-user
export TOKENLAB_RELAY_KEY=/path/to/authorized/private-key
export TOKENLAB_RELAY_SSH_PORT=22
# 默认只监听中继回环地址。开放网络前应配置鉴权和访问范围：
# export TOKENLAB_RELAY_BIND=0.0.0.0
bash scripts/forward-campus.sh
# screen: tokenlab-relay；日志 var/relay.log
# 停止转发：
screen -S tokenlab-relay -X quit
```

转发两端端口均取 TOKENLAB_PORT，默认 38473。中继 SSH 需允许远程转发及对应绑定方式。脚本断线重连，screen 不提供开机自启。

## 测试

```bash
TOKENLAB_TEST=1 python -m pytest -q tests/test_core.py
# 需启动应用并接入可用模型，会发起真实请求
TOKENLAB_TEST_URL=http://127.0.0.1:38473 python tests/live_check.py
```

单测使用内存库，覆盖 SSE、chunk/token 区别、时间、usage、概率、密钥脱敏、跨站写请求与参数限制。真实联调覆盖流式、非流式、无 logprobs、并发、取消与历史。

## 安全与许可证

可信开发环境实验工具，尚无登录、权限与配额系统，不要直接暴露公网。面向不可信用户前须配置 TLS、鉴权、限流、上游白名单；SSH 隧道不意味着浏览器 HTTP 已加密。
不提交 .env、私钥、数据库、日志、依赖和构建产物。许可证由项目所有者决定，目前未指定开源许可证。
