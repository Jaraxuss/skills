# 部署与迁移

首次安装、迁移到 Ubuntu、准备模型或排查环境问题时，阅读本文档。

## 支持的基础环境

- macOS arm64，仅 CPU。
- Ubuntu Server 22.04 或 24.04，x86_64，仅 CPU。
- Conda 环境 `voiceprint-poc`，Python 3.10。
- ERes2NetV2 模型 `iic/speech_eres2netv2_sv_zh-cn_16k-common@v1.0.1`。
- 3D-Speaker 固定提交 `065629c313eaf1a01c65c640c46d77e61e9607b4`。

第一版不支持 CUDA、MPS、Windows、Ubuntu arm64 或直接从飞书下载。审核服务仅限本机或局域网使用，不得作为互联网公开服务。

## 运行环境

先用 `environment/environment.yml` 创建环境，再安装对应平台的锁定依赖文件：

- `requirements-macos-arm64.lock.txt`
- `requirements-ubuntu-x86_64-cpu.lock.txt`

引导脚本在 Ubuntu 使用官方 PyTorch CPU wheel 源。FFmpeg 和 libsndfile 均安装在 Conda 环境中，不依赖系统级 Homebrew 或 apt。

## Skill 源码与安装链接

版本库中的目录是唯一源码：

```text
/Users/velen/Desktop/Velen/Z7Z8/skills/skills/feishu-speaker-insights
```

Codex 安装位置只使用软链接：

```text
~/.codex/skills/feishu-speaker-insights
  -> /Users/velen/Desktop/Velen/Z7Z8/skills/skills/feishu-speaker-insights
```

不要分别编辑两份 Skill，也不要把客户数据、模型缓存或运行产物写进源码目录。仓库更新后软链接会立即指向新版内容；升级后运行 `capabilities`、`doctor` 和自动测试。

## 后端持有的运行时路径

客户根目录、SQLite 和声纹文件路径只配置在后端服务。网页和 OpenClaw 不设置也不读取这些值。

`FEISHU_SPEAKER_DATA_DIR` 可覆盖默认的声纹数据根目录。

- macOS default: `~/Library/Application Support/feishu-speaker-insights`
- Linux default: `${XDG_DATA_HOME:-~/.local/share}/feishu-speaker-insights`

`FEISHU_SPEAKER_CACHE_DIR` 可覆盖模型和固定源码版本的缓存目录。

- macOS default: `~/Library/Caches/feishu-speaker-insights`
- Linux default: `${XDG_CACHE_HOME:-~/.cache}/feishu-speaker-insights`

管理员在后端主机运行 `paths` 可查看实际生效路径。迁移声纹时只需复制数据根目录；模型缓存可重新下载。

## 以客户目录为根的生产布局

在后端服务中将 `FEISHU_SPEAKER_CUSTOMERS_ROOT` 设为现有客户目录。之后的新数据按以下结构写入：

```text
<客户根>/
├── 共享数据/声纹数据/
│   ├── registry.sqlite3
│   ├── staff/<person-id>/profiles/
│   ├── .locks/
│   └── service-logs/
└── <客户名称>/声纹数据/
    ├── customer.json
    ├── people/<person-id>/profiles/
    ├── enrollments/
    ├── agent-tasks/
    ├── candidates/
    ├── runs/
    └── calibrations/
```

macOS value: `/Users/velen/Desktop/Velen/Z7Z8/客户`.

Ubuntu value: `/home/velen/velen/客户`.

所有新的 SQLite 声纹、运行记录和候选路径均使用 `customer://` 或 `shared://` URI；历史绝对路径仍可读取。

业务任务的哈希、阶段、进度、检查点、短租约和结果索引保存在共享 SQLite 的 `task_executions` 表；较大的审核包、声学产物和报告仍放在对应客户的 `agent-tasks/` 与 `runs/` 目录。等待飞书确认或语义生成时不占用 Worker 租约。OpenClaw 只保留后端返回的内部任务 ID，不读取这些目录。

### 复制式迁移

请先执行 dry-run；它不会移动或删除旧数据。

```text
speaker_insights.py migrate layout --from-data-dir OLD --customers-root NEW --dry-run
speaker_insights.py migrate layout --from-data-dir OLD --customers-root NEW --apply
```

`--apply` 会将客户数据复制到名称精确匹配的客户目录，将员工数据复制到共享目录；使用 SQLite 原生备份 API 备份数据库；把路径索引转换为 URI；校验全部声纹维度、JSON、哈希和外键，并保留 `OLD` 不变。旧数据根目录至少保留 30 天。目标注册库已存在，或目标客户声纹目录非空时，不要执行 `--apply`。

如已存在检出的 3D-Speaker 源码或 ModelScope 缓存，请在运行 `doctor` 前设置 `FEISHU_SPEAKER_3D_SPEAKER_DIR` 或 `MODELSCOPE_CACHE`。

## 环境准备

`doctor` 为只读检查。`doctor --download` 可能会克隆固定的源码版本，并将固定 checkpoint 下载到缓存中；它会验证平台、依赖导入、FFmpeg、源码版本、checkpoint 形状和数据目录权限。

准备完成后，建库与分析可以在断网环境运行。

仅含开始时间的飞书转写分段采用基于 NumPy 的自适应能量 VAD 与文本时长上限。它不增加平台专属依赖，在 macOS arm64 和 Ubuntu x86_64 CPU 上行为一致；不要求转写提供 `stop_time`。

## 客户端 API 地址

网页与后端同源，不需要单独配置 API 地址。OpenClaw 优先直接访问后端；使用薄 CLI 时按以下顺序确定地址：

1. 命令参数 `--api-url`；
2. `FEISHU_SPEAKER_API_URL`；
3. `http://127.0.0.1:8765`。

Ubuntu OpenClaw 只需配置：

```text
FEISHU_SPEAKER_API_URL=http://192.168.31.169:8765
```

不要在 OpenClaw 环境中配置 `FEISHU_SPEAKER_CUSTOMERS_ROOT`、SQLite 路径或声纹文件路径。业务 CLI 在后端不可用时返回 `BACKEND_UNAVAILABLE`，不会退回本地数据库。

## Ubuntu 迁移检查

1. 备份 Skill、systemd 用户服务和 `registry.sqlite3`。
2. 同步 Skill 源码并安装运行环境。
3. 仅在后端 systemd 服务中设置客户根目录和 CPU 线程数。
4. 如未复制缓存，执行一次 `doctor --download`。
5. 启动后端；SQLite 会自动执行只增列的兼容迁移。
6. 运行 `admin db-check`，核对人员、当前版本和 NPZ 摘要。
7. 让 OpenClaw 仅使用 API 地址执行黄金样例；声纹分数允许最多 `0.02` 的浮动。

## 统一业务服务

安装 Conda 依赖后，构建静态前端：

```text
cd review_app
npm ci
npm run build
```

Mac 按需启动：

```text
FEISHU_SPEAKER_CUSTOMERS_ROOT=/Users/velen/Desktop/Velen/Z7Z8/客户 \
conda run -n voiceprint-poc python scripts/speaker_insights.py review serve \
  --host 127.0.0.1 --port 8765 --base-url http://127.0.0.1:8765
```

Ubuntu 使用 `deploy/feishu-speaker-review.service` 中的用户级服务。虽然文件名保留了历史名称，它现在同时承载网页审核和机器业务 API。服务绑定 `192.168.31.169:8765`，以 `FEISHU_SPEAKER_CPU_THREADS=3` 启动一个队列 Worker，模型首次使用后常驻复用，失败后自动重启，并将滚动日志写入 `共享数据/声纹数据/service-logs`。不要绑定到 `0.0.0.0`，也不要通过公开代理暴露该端口。

服务启动后先检查：

```text
curl http://192.168.31.169:8765/api/v1/capabilities
curl http://192.168.31.169:8765/api/v1/customers
```

调度优先级依次为报告定稿、审核包准备、新声学任务；任何时刻只运行一个模型任务。语义等待和用户确认不占用 Worker。

## 管理员维护模式

`doctor`、`paths`、`capabilities`、`admin db-check` 和 `admin task-inspect` 是只读检查，可在服务运行时执行。`migrate layout`、`admin repair` 等写操作必须先停止服务；维护命令会尝试获取服务锁，无法获取时拒绝修改数据。

隔离离线测试必须显式指定临时数据目录：

```text
speaker_insights.py --data-dir /tmp/voiceprint-test offline test \
  --manifest meeting.yaml --viewpoints viewpoints.json
```

不要把生产客户根目录用于离线测试。
