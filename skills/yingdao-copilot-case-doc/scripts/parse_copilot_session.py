#!/usr/bin/env python3
"""
解析影刀 AI 流程助手（Copilot）导出的会话文件 (copilot-session-*.json)，
自动提取：
1. 会话基本信息与时间跨度
2. 影刀客户端版本、操作系统线索、编码偏好模式 (codeFlow / visualFlow)
3. 用户发送的所有正文指令（自动剥离 [[SHADOWBOT_RUNTIME_CONTEXT]]）
4. AI 发起的 question 问答交互（问题、选项、用户最终选择）
5. 流程创建与修改概况（VisualFlow / CodeFlow 子流程）
6. 运行与报错调试记录（studio-mcp_app_run / wait_run_finish / logs）
"""

import argparse
import datetime
import json
import re
import sys
from pathlib import Path


def fmt_ts(ms):
    if not ms:
        return None
    return datetime.datetime.fromtimestamp(ms / 1000.0).strftime("%Y-%m-%d %H:%M:%S")


def parse_session(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    session_info = data.get("session", {})
    messages = data.get("messages", [])

    # 按消息 ID 字典序排序（影刀 msg_ 之后为单调递增时间戳前缀，比偶发时钟偏移的 createdAt 更保序）
    messages_sorted = sorted(messages, key=lambda m: m.get("id", ""))

    raw_text = path.read_text(encoding="utf-8")
    versions = sorted(set(re.findall(r"shadowbot-(\d+\.\d+\.\d+)", raw_text, re.IGNORECASE)))

    assistant_ts = [
        m.get("createdAt")
        for m in messages_sorted
        if m.get("role") == "assistant" and m.get("createdAt")
    ]
    assistant_end_ts = [
        m.get("completedAt") or m.get("createdAt")
        for m in messages_sorted
        if m.get("role") == "assistant" and (m.get("completedAt") or m.get("createdAt"))
    ]
    start_ms = min(assistant_ts) if assistant_ts else None
    end_ms = max(assistant_end_ts) if assistant_end_ts else None
    duration_min = round((end_ms - start_ms) / 60000.0, 1) if (start_ms and end_ms) else None

    user_prompts = []
    questions_asked = []
    flows_touched = []
    run_events = []

    for msg in messages_sorted:
        role = msg.get("role")
        parts = msg.get("parts", [])

        if role == "user":
            authoring_mode = None
            prompt_texts = []
            for pt in parts:
                if pt.get("type") == "text":
                    txt = pt.get("text", "")
                    if "[[SHADOWBOT_RUNTIME_CONTEXT]]" in txt:
                        m_mode = re.search(r'"authoring_mode"\s*:\s*"([^"]+)"', txt)
                        if m_mode:
                            authoring_mode = m_mode.group(1)
                    else:
                        prompt_texts.append(txt.strip())
            if prompt_texts:
                user_prompts.append(
                    {
                        "message_id": msg.get("id"),
                        "authoring_mode": authoring_mode,
                        "text": "\n\n".join(prompt_texts),
                    }
                )

        for pt in parts:
            if pt.get("type") != "tool":
                continue
            tname = pt.get("tool", "")
            state = pt.get("state", {})
            inp = state.get("input", {})
            out = state.get("output", "")

            if tname == "question":
                q_list = inp.get("questions", []) if isinstance(inp, dict) else []
                questions_asked.append(
                    {
                        "message_id": msg.get("id"),
                        "question_count": len(q_list),
                        "questions": [
                            {
                                "header": q.get("header"),
                                "question": q.get("question"),
                                "options": [opt.get("label") for opt in q.get("options", [])],
                            }
                            for q in q_list
                        ],
                        "user_answer_raw": out,
                    }
                )

            elif tname in (
                "studio-mcp_app_create_flow",
                "studio-mcp_codeflow_write",
                "studio-mcp_codeflow_edit",
                "studio-mcp_flow_fill_blocks",
                "studio-mcp_flow_edit_blocks",
            ):
                flows_touched.append(
                    {
                        "tool": tname,
                        "input_summary": {
                            k: v
                            for k, v in (inp.items() if isinstance(inp, dict) else [])
                            if k in ("name", "flow_name", "flow", "type", "flow_type")
                        },
                    }
                )

            elif tname in (
                "studio-mcp_app_run",
                "studio-mcp_app_wait_run_finish",
                "studio-mcp_app_logs",
            ):
                run_events.append(
                    {
                        "tool": tname,
                        "output_preview": str(out)[:500],
                    }
                )

    total_question_items = sum(q["question_count"] for q in questions_asked)

    summary = {
        "session_id": session_info.get("id"),
        "session_title": session_info.get("title"),
        "shadowbot_versions_detected": versions,
        "timeline": {
            "start_time": fmt_ts(start_ms),
            "end_time": fmt_ts(end_ms),
            "duration_minutes": duration_min,
        },
        "interaction_stats": {
            "user_prompt_turns": len(user_prompts),
            "ai_question_rounds": len(questions_asked),
            "ai_question_total_items": total_question_items,
            "total_messages": len(messages),
        },
        "user_prompts": user_prompts,
        "questions_and_answers": questions_asked,
        "flows_touched_count": len(flows_touched),
        "flows_touched_sample": flows_touched[:15],
        "run_and_log_events": run_events,
    }
    return summary


def main():
    parser = argparse.ArgumentParser(description="Parse Yingdao Copilot session JSON")
    parser.add_argument("session_json", help="Path to copilot-session-*.json")
    args = parser.parse_args()

    path = Path(args.session_json).expanduser().resolve()
    if not path.is_file():
        print(f"Error: File not found: {path}", file=sys.stderr)
        sys.exit(1)

    res = parse_session(path)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
