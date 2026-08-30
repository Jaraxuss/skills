#!/usr/bin/env python3
from __future__ import annotations

import json
import platform
import sys
import tempfile
from pathlib import Path

import numpy as np
import soundfile as sf


SCRIPTS = Path(__file__).resolve().parents[1]
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from speaker_engine.storage import DataStore
from speaker_engine.transcript import convert_to_wav, parse_transcript


def main() -> None:
    machine = platform.machine().lower()
    if platform.system() != "Linux" or machine not in {"x86_64", "amd64"}:
        raise SystemExit(f"Unexpected platform: {platform.system()} {machine}")
    with tempfile.TemporaryDirectory(prefix="speaker-linux-smoke-") as temporary:
        root = Path(temporary)
        source = root / "输入 音频.wav"
        converted = root / "输出 音频.wav"
        transcript = root / "中文 转写.txt"
        sample_rate = 48000
        wave = np.zeros(sample_rate * 4, dtype=np.float32)
        wave[::100] = 0.05
        sf.write(source, wave, sample_rate)
        transcript.write_text(
            "内部CSM 00:00\n测试开始\n\n说话人 1 00:02\n继续测试\n",
            encoding="utf-8-sig",
        )
        convert_to_wav(source, converted, 16000)
        rows = parse_transcript(transcript, 4.0)
        store = DataStore(root / "数据 root")
        people = store.upsert_manifest(
            {
                "customer": {"id": "linux-smoke", "name": "Linux 测试"},
                "attendees": [
                    {"name": "内部CSM", "role": "CSM", "organization": "yingdao"},
                    {"name": "客户甲", "role": "老板", "organization": "customer"},
                ],
            }
        )
        print(
            json.dumps(
                {
                    "ok": True,
                    "platform": f"{platform.system()}-{machine}",
                    "python": platform.python_version(),
                    "converted_sample_rate": sf.info(converted).samplerate,
                    "labels": [row.label for row in rows],
                    "staff_scope": people["内部CSM"]["scope"],
                    "customer_scope": people["客户甲"]["scope"],
                    "sqlite": str(store.db_path),
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
