# 实现说明

前端 React/TypeScript/Vite、Tailwind、Radix/CVA 按钮、Recharts、Zustand、Framer Motion、Lucide。
后端 FastAPI/httpx/Pydantic/SQLAlchemy，SQLite 历史与同源静态资源服务。

数据链：浏览器 POST → 后端异步上游请求 → SSE 解析与 Tracker → 标准化事件 → 实时前端。
概率取上游 logprobs；chunk 与 Token 分开统计。Token ID 和细粒度时序缺失时不推断。
流程图中央仅为结构示意，实际候选概率随位置联动；两模型真正并行请求。
端点/API Key 会话隔离且仅存内存，报告与持久化历史不含密钥；跨站写请求被拒绝。
数据库互斥防止不支持 SQLite 文件锁的存储遭多 worker 写入，不支持多进程部署。

开发验证覆盖 TypeScript/Vite 构建、9 项后端测试、真实流式/非流式、无 logprobs、取消、历史、并发与浏览器交互。
公开版另将部署配置替换为环境变量和通用示例，不包含实际部署信息。
