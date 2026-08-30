#!/usr/bin/env python3
"""Benchmark enrollment and acoustic matching without touching production data."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from statistics import mean
from typing import Any, Iterable


MODEL = {
    "id": "iic/speech_eres2netv2_sv_zh-cn_16k-common",
    "revision": "v1.0.1",
    "embedding_size": 192,
    "source_revision": "065629c313eaf1a01c65c640c46d77e61e9607b4",
    "device": "cpu",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark enrollment and acoustic matching in an isolated data root"
    )
    parser.add_argument("--cli", required=True, type=Path)
    parser.add_argument("--enroll-manifest", required=True, type=Path)
    parser.add_argument("--confirmation", required=True, type=Path)
    parser.add_argument("--match-manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--concurrency",
        default="",
        help="Comma-separated Ubuntu concurrency levels, for example 1,2,4; empty disables",
    )
    parser.add_argument("--keep-work", action="store_true")
    parser.add_argument("--sample-interval", type=float, default=0.5)
    return parser.parse_args()


def json_objects(text: str) -> list[Any]:
    decoder = json.JSONDecoder()
    objects: list[Any] = []
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        objects.append(value)
    return objects


def last_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped:
        try:
            value = json.loads(stripped)
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            pass
    objects = json_objects(text)
    dictionaries = [value for value in objects if isinstance(value, dict)]
    if not dictionaries:
        raise RuntimeError(f"Command did not return a JSON object: {text[-1000:]}")
    # Prefer the outermost/largest object when logs contain nested JSON objects.
    return max(dictionaries, key=lambda value: len(value))


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except FileNotFoundError:
            continue
    return total


def physical_memory_mb() -> float | None:
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return pages * page_size / 1024 / 1024
    except (AttributeError, OSError, ValueError):
        return None


def ps_snapshot() -> dict[int, tuple[int, float, float]]:
    commands = [
        ["ps", "-axo", "pid=,ppid=,rss=,%cpu="],
        ["ps", "-eo", "pid=,ppid=,rss=,%cpu="],
    ]
    output = ""
    for command in commands:
        try:
            output = subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL)
            break
        except (OSError, subprocess.CalledProcessError):
            continue
    result: dict[int, tuple[int, float, float]] = {}
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        try:
            pid = int(fields[0])
            ppid = int(fields[1])
            rss_kb = float(fields[2])
            cpu_pct = float(fields[3].replace(",", "."))
        except ValueError:
            continue
        result[pid] = (ppid, rss_kb, cpu_pct)
    return result


def process_tree_stats(root_pid: int, snapshot: dict[int, tuple[int, float, float]]) -> tuple[float, float]:
    pids = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, (ppid, _, _) in snapshot.items():
            if ppid in pids and pid not in pids:
                pids.add(pid)
                changed = True
    rss_kb = sum(snapshot[pid][1] for pid in pids if pid in snapshot)
    cpu_pct = sum(snapshot[pid][2] for pid in pids if pid in snapshot)
    return rss_kb / 1024, cpu_pct


def parse_number(pattern: str, text: str, cast: type = float) -> float | None:
    match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
    if not match:
        return None
    try:
        return cast(match.group(1))
    except (TypeError, ValueError):
        return None


def parse_time_output(text: str, system: str) -> dict[str, Any]:
    user = parse_number(r"User time \(seconds\):\s*([0-9.]+)", text)
    sys_time = parse_number(r"System time \(seconds\):\s*([0-9.]+)", text)
    if user is None:
        user = parse_number(r"^\s*([0-9.]+)\s+user", text)
    if sys_time is None:
        sys_time = parse_number(r"^\s*([0-9.]+)\s+sys", text)
    if user is None:
        user = parse_number(r"([0-9.]+)\s+user", text)
    if sys_time is None:
        sys_time = parse_number(r"([0-9.]+)\s+sys", text)
    if user is None:
        user = parse_number(r"^\s*user\s+([0-9.]+)", text)
    if sys_time is None:
        sys_time = parse_number(r"^\s*sys\s+([0-9.]+)", text)

    linux_rss_kb = parse_number(r"Maximum resident set size \(kbytes\):\s*([0-9]+)", text, int)
    mac_rss_bytes = parse_number(r"maximum resident set size:\s*([0-9]+)", text, int)
    fs_inputs = parse_number(r"File system inputs:\s*([0-9]+)", text, int)
    fs_outputs = parse_number(r"File system outputs:\s*([0-9]+)", text, int)
    disk_read_bytes = parse_number(r"bytes read from disk:\s*([0-9]+)", text, int)
    disk_write_bytes = parse_number(r"bytes written to disk:\s*([0-9]+)", text, int)

    max_rss_mb = None
    if linux_rss_kb is not None:
        max_rss_mb = linux_rss_kb / 1024
    elif mac_rss_bytes is not None:
        max_rss_mb = mac_rss_bytes / 1024 / 1024

    return {
        "user_seconds": user,
        "system_seconds": sys_time,
        "cpu_seconds": (user + sys_time) if user is not None and sys_time is not None else None,
        "time_max_rss_mb": max_rss_mb,
        "filesystem_inputs": fs_inputs,
        "filesystem_outputs": fs_outputs,
        "disk_read_bytes": disk_read_bytes,
        "disk_write_bytes": disk_write_bytes,
        "time_format": "gnu-time-v" if system == "Linux" else "macos-time-l",
    }


def run_timed(
    label: str,
    argv: list[str],
    env: dict[str, str],
    data_root: Path,
    raw_dir: Path,
    sample_interval: float,
) -> dict[str, Any]:
    raw_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = raw_dir / f"{label}.stdout.log"
    stderr_path = raw_dir / f"{label}.stderr.log"
    time_path = raw_dir / f"{label}.time.log"
    system = platform.system()
    if system == "Linux":
        command = ["/usr/bin/time", "-v", "-o", str(time_path), "--", *argv]
    else:
        # macOS `time -l` may exit non-zero in a sandbox because it cannot
        # read kern.clockrate. POSIX `-p` is reliable; RSS is sampled via ps.
        command = ["/usr/bin/time", "-p", *argv]

    before_bytes = directory_size(data_root)
    samples: list[tuple[float, float]] = []
    started = time.perf_counter()
    print(f"[benchmark] start {label}", flush=True)
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, env=env)
        while process.poll() is None:
            rss_mb, cpu_pct = process_tree_stats(process.pid, ps_snapshot())
            samples.append((rss_mb, cpu_pct))
            time.sleep(max(0.1, sample_interval))
        return_code = process.wait()
    wall_seconds = time.perf_counter() - started
    if system != "Linux":
        time_path.write_text(stderr_path.read_text(encoding="utf-8"), encoding="utf-8")
    time_text = time_path.read_text(encoding="utf-8") if time_path.exists() else ""
    after_bytes = directory_size(data_root)
    parsed = parse_time_output(time_text, system)
    sample_rss = max((item[0] for item in samples), default=None)
    sample_cpu = [item[1] for item in samples]
    parsed.update(
        {
            "label": label,
            "command": command,
            "return_code": return_code,
            "wall_seconds": wall_seconds,
            "sample_avg_cpu_percent": mean(sample_cpu) if sample_cpu else None,
            "sample_peak_cpu_percent": max(sample_cpu) if sample_cpu else None,
            "sample_peak_rss_mb": sample_rss,
            "peak_rss_mb": max(
                value for value in (sample_rss, parsed.get("time_max_rss_mb")) if value is not None
            )
            if any(value is not None for value in (sample_rss, parsed.get("time_max_rss_mb")))
            else None,
            "data_root_size_before_bytes": before_bytes,
            "data_root_size_after_bytes": after_bytes,
            "data_root_size_delta_bytes": after_bytes - before_bytes,
            "stdout_log": str(stdout_path),
            "stderr_log": str(stderr_path),
            "time_log": str(time_path),
        }
    )
    if parsed.get("cpu_seconds") is not None and wall_seconds > 0:
        parsed["cpu_utilization_from_time_percent"] = parsed["cpu_seconds"] / wall_seconds * 100
    else:
        parsed["cpu_utilization_from_time_percent"] = None
    if return_code != 0:
        tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"Benchmark stage failed: {label} (exit {return_code})\n{tail}")
    print(
        f"[benchmark] done {label}: {wall_seconds:.2f}s, "
        f"peak_rss={parsed.get('peak_rss_mb')!s}MB, "
        f"peak_cpu={parsed.get('sample_peak_cpu_percent')!s}%",
        flush=True,
    )
    return parsed


def command_for(cli: Path, *args: str) -> list[str]:
    return [sys.executable, str(cli), *args]


def base_env(data_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["FEISHU_SPEAKER_DATA_DIR"] = str(data_root)
    env["PYTHONUNBUFFERED"] = "1"
    return env


def copy_data_root(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


def run_enrollment(
    cli: Path,
    manifest: Path,
    confirmation: Path,
    work_root: Path,
    raw_dir: Path,
    sample_interval: float,
) -> tuple[dict[str, Any], Path]:
    data_root = work_root / "enrollment-data"
    env = base_env(data_root)
    stages: list[dict[str, Any]] = []
    stages.append(
        run_timed(
            "enroll_01_customer_upsert",
            command_for(cli, "customer", "upsert", "--manifest", str(manifest)),
            env,
            data_root,
            raw_dir,
            sample_interval,
        )
    )
    prepare = run_timed(
        "enroll_02_prepare",
        command_for(cli, "enroll", "prepare", "--manifest", str(manifest)),
        env,
        data_root,
        raw_dir,
        sample_interval,
    )
    stages.append(prepare)
    prepare_payload = last_json_object(
        Path(prepare["stdout_log"]).read_text(encoding="utf-8", errors="replace")
    )
    draft = Path(prepare_payload["draft"])
    stages.append(
        run_timed(
            "enroll_03_commit",
            command_for(
                cli,
                "enroll",
                "commit",
                "--draft",
                str(draft),
                "--confirmation",
                str(confirmation),
            ),
            env,
            data_root,
            raw_dir,
            sample_interval,
        )
    )
    return {
        "data_root": str(data_root),
        "stages": stages,
        "total_wall_seconds": sum(stage["wall_seconds"] for stage in stages),
        "draft": str(draft),
    }, data_root


def run_single_match(
    cli: Path,
    manifest: Path,
    source_data_root: Path,
    work_root: Path,
    raw_dir: Path,
    sample_interval: float,
) -> dict[str, Any]:
    data_root = work_root / "single-match-data"
    copy_data_root(source_data_root, data_root)
    env = base_env(data_root)
    stage = run_timed(
        "match_single",
        command_for(cli, "analyze", "acoustic", "--manifest", str(manifest)),
        env,
        data_root,
        raw_dir,
        sample_interval,
    )
    payload = last_json_object(
        Path(stage["stdout_log"]).read_text(encoding="utf-8", errors="replace")
    )
    stage["run_id"] = payload.get("run_id")
    stage["run_dir"] = payload.get("run_dir")
    stage["result_count"] = len(payload.get("results", []))
    return stage


def run_parallel_matches(
    level: int,
    cli: Path,
    manifest: Path,
    source_data_root: Path,
    work_root: Path,
    raw_dir: Path,
    sample_interval: float,
) -> dict[str, Any]:
    level_root = work_root / f"concurrency-{level}"
    level_root.mkdir(parents=True, exist_ok=True)
    processes: list[tuple[subprocess.Popen[str], Path, Any, Any]] = []
    for index in range(level):
        data_root = level_root / f"job-{index}"
        copy_data_root(source_data_root, data_root)
        stdout_path = raw_dir / f"concurrency_{level}_job_{index}.stdout.log"
        stderr_path = raw_dir / f"concurrency_{level}_job_{index}.stderr.log"
        stdout = stdout_path.open("w", encoding="utf-8")
        stderr = stderr_path.open("w", encoding="utf-8")
        env = base_env(data_root)
        process = subprocess.Popen(
            command_for(cli, "analyze", "acoustic", "--manifest", str(manifest)),
            stdout=stdout,
            stderr=stderr,
            env=env,
            text=True,
        )
        processes.append((process, data_root, stdout, stderr))

    started = time.perf_counter()
    aggregate_rss: list[float] = []
    aggregate_cpu: list[float] = []
    per_job_samples: dict[int, list[tuple[float, float]]] = {index: [] for index in range(level)}
    print(f"[benchmark] start concurrency {level}", flush=True)
    while any(process.poll() is None for process, _, _, _ in processes):
        snapshot = ps_snapshot()
        rss_total = 0.0
        cpu_total = 0.0
        for index, (process, _, _, _) in enumerate(processes):
            rss_mb, cpu_pct = process_tree_stats(process.pid, snapshot)
            per_job_samples[index].append((rss_mb, cpu_pct))
            rss_total += rss_mb
            cpu_total += cpu_pct
        aggregate_rss.append(rss_total)
        aggregate_cpu.append(cpu_total)
        time.sleep(max(0.1, sample_interval))
    return_codes = []
    jobs = []
    for index, (process, data_root, stdout, stderr) in enumerate(processes):
        return_code = process.wait()
        stdout.close()
        stderr.close()
        return_codes.append(return_code)
        samples = per_job_samples[index]
        stdout_path = raw_dir / f"concurrency_{level}_job_{index}.stdout.log"
        stderr_path = raw_dir / f"concurrency_{level}_job_{index}.stderr.log"
        payload = {}
        if return_code == 0:
            payload = last_json_object(stdout_path.read_text(encoding="utf-8", errors="replace"))
        jobs.append(
            {
                "job_index": index,
                "return_code": return_code,
                "data_root": str(data_root),
                "wall_seconds": None,
                "peak_rss_mb": max((item[0] for item in samples), default=None),
                "peak_cpu_percent": max((item[1] for item in samples), default=None),
                "avg_cpu_percent": mean(item[1] for item in samples) if samples else None,
                "run_id": payload.get("run_id"),
                "run_dir": payload.get("run_dir"),
                "result_count": len(payload.get("results", [])),
                "stdout_log": str(stdout_path),
                "stderr_log": str(stderr_path),
            }
        )
    wall_seconds = time.perf_counter() - started
    for job in jobs:
        job["wall_seconds"] = wall_seconds
    if any(return_code != 0 for return_code in return_codes):
        failed = [
            Path(job["stderr_log"]).read_text(encoding="utf-8", errors="replace")[-1500:]
            for job in jobs
            if job["return_code"] != 0
        ]
        raise RuntimeError("Concurrency {} failed:\n{}".format(level, "\n".join(failed)))
    result = {
        "level": level,
        "wall_seconds": wall_seconds,
        "aggregate_peak_rss_mb": max(aggregate_rss) if aggregate_rss else None,
        "aggregate_peak_cpu_percent": max(aggregate_cpu) if aggregate_cpu else None,
        "jobs": jobs,
    }
    print(
        f"[benchmark] done concurrency {level}: {wall_seconds:.2f}s, "
        f"aggregate_peak_rss={result['aggregate_peak_rss_mb']!s}MB, "
        f"aggregate_peak_cpu={result['aggregate_peak_cpu_percent']!s}%",
        flush=True,
    )
    return result


def summarize_metric(stages: Iterable[dict[str, Any]], key: str) -> float | None:
    values = [stage[key] for stage in stages if stage.get(key) is not None]
    return sum(values) if values else None


def render_markdown(report: dict[str, Any]) -> str:
    def fmt(value: Any, suffix: str = "") -> str:
        if value is None:
            return "—"
        if isinstance(value, float):
            return f"{value:.2f}{suffix}"
        return f"{value}{suffix}"

    lines = [
        "# 声纹 Skill 性能基准报告",
        "",
        "> 本报告使用隔离数据目录重跑；不覆盖正式声纹库，不保留裁剪 WAV。CPU/内存为进程树采样，Linux 磁盘输入输出计数来自 GNU time，Mac 磁盘字节指标取决于系统 time 是否提供。",
        "",
        "## 环境",
        "",
        f"- 系统：`{report['platform']['platform']}`，架构：`{report['platform']['machine']}`",
        f"- Python：`{report['platform']['python']}`，逻辑 CPU：`{report['platform']['logical_cpu']}`，物理内存：`{report['platform']['physical_memory_mb']}` MB",
        f"- 模型：`{MODEL['id']}@{MODEL['revision']}`，设备：`{MODEL['device']}`，向量：`{MODEL['embedding_size']}` 维",
        f"- 采样间隔：`{report['sampling']['interval_seconds']}` 秒",
        "",
        "## 首次建库/重建",
        "",
        "| 阶段 | 墙钟秒数 | CPU 秒数 | CPU 利用率 | 峰值 RSS MB | 数据目录变化 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for stage in report["enrollment"]["stages"]:
        cpu = stage.get("cpu_seconds")
        cpu_util = stage.get("cpu_utilization_from_time_percent")
        lines.append(
            f"| {stage['label']} | {stage['wall_seconds']:.2f} | "
            f"{fmt(cpu)} | "
            f"{fmt(cpu_util, '%')} | "
            f"{fmt(stage.get('peak_rss_mb'))} | "
            f"{stage['data_root_size_delta_bytes']} B |"
        )
    lines.extend(
        [
            f"| 合计 | {report['enrollment']['total_wall_seconds']:.2f} | — | — | — | — |",
            "",
            "## 后续单路匹配",
            "",
            "| 阶段 | 墙钟秒数 | CPU 秒数 | CPU 利用率 | 峰值 RSS MB | 数据目录变化 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    stage = report["single_match"]
    cpu = stage.get("cpu_seconds")
    cpu_util = stage.get("cpu_utilization_from_time_percent")
    lines.append(
        f"| analyze acoustic | {stage['wall_seconds']:.2f} | "
        f"{fmt(cpu)} | "
        f"{fmt(cpu_util, '%')} | "
        f"{fmt(stage.get('peak_rss_mb'))} | "
        f"{stage['data_root_size_delta_bytes']} B |"
    )
    if report.get("concurrency"):
        lines.extend(
            [
                "",
                "## Ubuntu 并发匹配",
                "",
                "| 并发路数 | 总墙钟秒数 | 聚合峰值 CPU | 聚合峰值 RSS MB | 单路结果数 |",
                "|---:|---:|---:|---:|---:|",
            ]
        )
        for item in report["concurrency"]:
            result_counts = sorted({job["result_count"] for job in item["jobs"]})
            lines.append(
                f"| {item['level']} | {item['wall_seconds']:.2f} | "
                f"{fmt(item.get('aggregate_peak_cpu_percent'), '%')} | "
                f"{fmt(item.get('aggregate_peak_rss_mb'))} | "
                f"{','.join(map(str, result_counts))} |"
            )
    lines.extend(
        [
            "",
            "## 解读边界",
            "",
            "- 这是一次基准重跑，不是长期监控；宿主机上的其他 OpenClaw 任务会影响瞬时 CPU、内存和 Swap。",
            "- `analyze acoustic` 只测音频转码、分段、向量提取和声纹匹配；观点抽取/报告最终化不属于本次声学性能指标。",
            "- Linux 的 `File system inputs/outputs` 是 GNU time 提供的系统 I/O 计数，不直接等同于字节数；报告 JSON 保留原始字段。",
            f"- 原始命令日志：`{report['artifacts']['raw_log_dir']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    for path in (args.cli, args.enroll_manifest, args.confirmation, args.match_manifest):
        if not path.exists():
            raise SystemExit(f"Missing input: {path}")
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    raw_dir = output.parent / f"{output.stem}-raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    work_root = Path(tempfile.mkdtemp(prefix="feishu-speaker-benchmark-"))
    concurrency_levels = [
        int(value.strip()) for value in args.concurrency.split(",") if value.strip()
    ]
    report: dict[str, Any] = {
        "schema_version": 1,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "platform": {
            "platform": platform.platform(),
            "system": platform.system(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
            "logical_cpu": os.cpu_count(),
            "physical_memory_mb": physical_memory_mb(),
        },
        "model": MODEL,
        "sampling": {"interval_seconds": args.sample_interval},
        "inputs": {
            "enroll_manifest": str(args.enroll_manifest),
            "confirmation": str(args.confirmation),
            "match_manifest": str(args.match_manifest),
        },
        "artifacts": {"raw_log_dir": str(raw_dir), "work_root_removed_after_run": True},
    }
    try:
        enrollment, enrollment_data_root = run_enrollment(
            args.cli,
            args.enroll_manifest,
            args.confirmation,
            work_root,
            raw_dir,
            args.sample_interval,
        )
        report["enrollment"] = enrollment
        report["single_match"] = run_single_match(
            args.cli,
            args.match_manifest,
            enrollment_data_root,
            work_root,
            raw_dir,
            args.sample_interval,
        )
        if concurrency_levels:
            report["concurrency"] = [
                run_parallel_matches(
                    level,
                    args.cli,
                    args.match_manifest,
                    enrollment_data_root,
                    work_root,
                    raw_dir,
                    args.sample_interval,
                )
                for level in concurrency_levels
            ]
        else:
            report["concurrency"] = []
    finally:
        if not args.keep_work:
            shutil.rmtree(work_root, ignore_errors=True)
    report["markdown"] = str(output.with_suffix(".md"))
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output.with_suffix(".md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"json": str(output), "markdown": str(output.with_suffix('.md')), "raw": str(raw_dir)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
