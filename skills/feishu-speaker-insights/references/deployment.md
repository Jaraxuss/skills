# Deployment and migration

Read this reference for first-time setup, Ubuntu migration, model preparation, or environment failures.

## Supported baseline

- macOS arm64, CPU only.
- Ubuntu Server 22.04 or 24.04, x86_64, CPU only.
- Conda environment `voiceprint-poc`, Python 3.10.
- ERes2NetV2 model `iic/speech_eres2netv2_sv_zh-cn_16k-common@v1.0.1`.
- 3D-Speaker commit `065629c313eaf1a01c65c640c46d77e61e9607b4`.

CUDA, MPS, Windows, Ubuntu arm64, direct Feishu download, and a long-running HTTP service are outside v1.

## Environment

Create the environment with `environment/environment.yml`, then install the matching lock file:

- `requirements-macos-arm64.lock.txt`
- `requirements-ubuntu-x86_64-cpu.lock.txt`

The bootstrap script uses the official PyTorch CPU wheel source on Ubuntu. FFmpeg and libsndfile live in the Conda environment, avoiding a system Homebrew or apt dependency.

## Runtime paths

`FEISHU_SPEAKER_DATA_DIR` overrides the biometric data root.

- macOS default: `~/Library/Application Support/feishu-speaker-insights`
- Linux default: `${XDG_DATA_HOME:-~/.local/share}/feishu-speaker-insights`

`FEISHU_SPEAKER_CACHE_DIR` overrides model and pinned source caches.

- macOS default: `~/Library/Caches/feishu-speaker-insights`
- Linux default: `${XDG_CACHE_HOME:-~/.cache}/feishu-speaker-insights`

Run `paths` to display resolved locations. Copy only the data root when migrating profiles; model caches can be downloaded again.

For an existing checked-out 3D-Speaker source or ModelScope cache, set `FEISHU_SPEAKER_3D_SPEAKER_DIR` or `MODELSCOPE_CACHE` before `doctor`.

## Preparation

`doctor` is read-only. `doctor --download` may clone the pinned source and download the pinned checkpoint into the cache. It verifies platform, dependency imports, FFmpeg, source revision, checkpoint shape, and data permissions.

After preparation, enrollment and analysis run without network access.

## Ubuntu migration check

1. Copy the data root with permissions preserved.
2. Set `FEISHU_SPEAKER_DATA_DIR` to the copied directory.
3. Install the Skill and environment.
4. Run `doctor --download` once if caches were not copied.
5. Run the golden meeting and compare final statuses; allow up to `0.02` score drift.
