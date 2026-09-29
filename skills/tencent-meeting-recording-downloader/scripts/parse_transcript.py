#!/usr/bin/env python3
"""
解析腾讯会议逐字稿JSON数据，生成格式化的TXT文本文件。

输入：从浏览器React fiber提取的逐字稿原始JSON数组
输出：带时间戳和发言人的可读文本文件

用法：
    python3 parse_transcript.py input.json output.txt --title "会议标题"
"""

import json
import sys
import argparse


def ms_to_timestamp(ms):
    """将毫秒时间戳转换为 HH:MM:SS 格式"""
    total_sec = ms // 1000
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    seconds = total_sec % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def extract_speaker_name(speaker):
    """从speaker对象中提取发言人姓名"""
    if not speaker:
        return "未知"
    if isinstance(speaker, dict):
        return speaker.get("user_name", speaker.get("name", "未知"))
    if isinstance(speaker, str) and speaker.startswith("{"):
        try:
            speaker_dict = json.loads(speaker)
            return speaker_dict.get("user_name", "未知")
        except (json.JSONDecodeError, AttributeError):
            return "未知"
    return str(speaker) if speaker else "未知"


def parse_transcript(data):
    """
    解析逐字稿数据数组，返回格式化的行列表。
    
    每行格式：[{time}] {speaker}\n{text}\n
    """
    lines = []
    for para in data:
        if not para:
            continue
        
        pid = para.get("pid", "")
        start_ms = para.get("start_time", 0)
        speaker = extract_speaker_name(para.get("speaker", ""))
        
        # 提取所有文字
        text_parts = []
        for sent in para.get("sentences", []):
            for word in sent.get("words", []):
                text_parts.append(word.get("text", ""))
        full_text = "".join(text_parts)
        
        if not full_text.strip():
            continue
        
        time_str = ms_to_timestamp(start_ms)
        lines.append({
            "pid": pid,
            "time": time_str,
            "speaker": speaker,
            "text": full_text,
        })
    
    return lines


def main():
    parser = argparse.ArgumentParser(description="解析腾讯会议逐字稿JSON为TXT文本")
    parser.add_argument("input_json", help="输入的逐字稿JSON文件路径")
    parser.add_argument("output_txt", help="输出的TXT文件路径")
    parser.add_argument("--title", default="腾讯会议逐字稿", help="会议标题（可选）")
    parser.add_argument("--date", default="", help="会议日期（可选）")
    args = parser.parse_args()
    
    # 读取原始JSON
    with open(args.input_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # 解析
    lines = parse_transcript(data)
    
    # 计算统计信息
    total_chars = sum(len(line["text"]) for line in lines)
    speakers = set(line["speaker"] for line in lines)
    
    # 写入输出文件
    with open(args.output_txt, "w", encoding="utf-8") as f:
        f.write("=" * 60 + "\n")
        f.write(f"{args.title}\n")
        if args.date:
            f.write(f"会议时间：{args.date}\n")
        f.write("=" * 60 + "\n\n")
        
        for line in lines:
            f.write(f"[{line['time']}] {line['speaker']}\n")
            f.write(f"{line['text']}\n\n")
    
    # 输出统计信息
    print(f"逐字稿已保存到: {args.output_txt}")
    print(f"共 {len(lines)} 条记录")
    print(f"总字数: {total_chars} 字")
    print(f"发言人: {', '.join(speakers)}")


if __name__ == "__main__":
    main()
