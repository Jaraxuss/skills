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

## 运行时路径

`FEISHU_SPEAKER_DATA_DIR` 可覆盖默认的声纹数据根目录。

- macOS default: `~/Library/Application Support/feishu-speaker-insights`
- Linux default: `${XDG_DATA_HOME:-~/.local/share}/feishu-speaker-insights`

`FEISHU_SPEAKER_CACHE_DIR` 可覆盖模型和固定源码版本的缓存目录。

- macOS default: `~/Library/Caches/feishu-speaker-insights`
- Linux default: `${XDG_CACHE_HOME:-~/.cache}/feishu-speaker-insights`

运行 `paths` 可查看实际生效的路径。迁移声纹时只需复制数据根目录；模型缓存可重新下载。

## 以客户目录为根的生产布局

将 `FEISHU_SPEAKER_CUSTOMERS_ROOT` 设为现有客户目录。之后的新数据按以下结构写入：

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
    ├── candidates/
    ├── runs/
    └── calibrations/
```

macOS value: `/Users/velen/Desktop/Velen/Z7Z8/客户`.

Ubuntu value: `/home/velen/velen/客户`.

所有新的 SQLite 声纹、运行记录和候选路径均使用 `customer://` 或 `shared://` URI；历史绝对路径仍可读取。

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

## Ubuntu 迁移检查

1. 复制数据根目录，并保留原始权限。
2. 将 `FEISHU_SPEAKER_DATA_DIR` 指向复制后的目录。
3. 安装 Skill 和运行环境。
4. 如未复制缓存，执行一次 `doctor --download`。
5. 运行黄金样例会议并比较最终状态；声纹分数允许最多 `0.02` 的浮动。

## 审核服务

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

Ubuntu 使用 `deploy/feishu-speaker-review.service` 中的用户级服务。它绑定 `192.168.31.169:8765`，以 `FEISHU_SPEAKER_CPU_THREADS=3` 启动一个队列 Worker，失败后自动重启，并将滚动日志写入 `共享数据/声纹数据/service-logs`。不要绑定到 `0.0.0.0`，也不要通过公开代理暴露该端口。
