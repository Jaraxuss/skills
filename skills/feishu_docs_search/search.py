#!/usr/bin/env python3
"""
飞书云文档搜索脚本
API 文档：https://open.feishu.cn/document/server-docs/docs/drive-v1/search/document-search

用法示例：
    python3 search.py --token "u-xxxx" --key "项目周报"
    python3 search.py --token "u-xxxx" --key "需求文档" --count 20 --offset 0 --types "doc,sheet"
    python3 search.py --token "u-xxxx" --key "会议" --types "doc" --owners "ou_abc123,ou_def456"
"""

import argparse
import json
import sys
import urllib.request
import urllib.error

# 飞书搜索云文档 API 地址（旧版接口，支持 user_access_token）
API_URL = "https://open.feishu.cn/open-apis/suite/docs-api/search/object"

# 文件类型中文映射
TYPE_LABELS = {
    "doc": "📄 文档",
    "sheet": "📊 电子表格",
    "slides": "📑 幻灯片",
    "bitable": "🗃️ 多维表格",
    "mindnote": "🧠 思维笔记",
    "file": "📎 文件",
}

# 飞书文档直达链接模板
LINK_TEMPLATES = {
    "doc": "https://docs.feishu.cn/docs/{token}",
    "sheet": "https://docs.feishu.cn/sheets/{token}",
    "slides": "https://docs.feishu.cn/slides/{token}",
    "bitable": "https://docs.feishu.cn/base/{token}",
    "mindnote": "https://docs.feishu.cn/mindnotes/{token}",
    "file": "https://docs.feishu.cn/file/{token}",
}


def build_feishu_link(docs_type: str, docs_token: str) -> str:
    """根据文档类型和 Token 构建飞书直达链接。"""
    template = LINK_TEMPLATES.get(docs_type, "https://docs.feishu.cn/docs/{token}")
    return template.format(token=docs_token)


def search_docs(token: str, search_key: str, count: int = 10, offset: int = 0,
                docs_types: list = None, owner_ids: list = None) -> dict:
    """
    调用飞书搜索云文档 API。

    Args:
        token: user_access_token（不含 "Bearer " 前缀）
        search_key: 搜索关键词
        count: 返回数量，范围 [0, 50]
        offset: 偏移量，offset + count < 200
        docs_types: 文件类型列表，如 ["doc", "sheet"]
        owner_ids: 文件所有者 Open ID 列表

    Returns:
        API 响应的完整 JSON 字典
    """
    payload = {
        "search_key": search_key,
        "count": count,
        "offset": offset,
    }
    if docs_types:
        payload["docs_types"] = docs_types
    if owner_ids:
        payload["owner_ids"] = owner_ids

    body = json.dumps(payload).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    req = urllib.request.Request(API_URL, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            response_body = resp.read().decode("utf-8")
            return json.loads(response_body)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            return json.loads(error_body)
        except json.JSONDecodeError:
            return {
                "code": e.code,
                "msg": f"HTTP Error {e.code}: {error_body}",
                "data": None,
            }
    except urllib.error.URLError as e:
        return {
            "code": -1,
            "msg": f"Network error: {e.reason}",
            "data": None,
        }
    except Exception as e:
        return {
            "code": -1,
            "msg": f"Unexpected error: {str(e)}",
            "data": None,
        }


def format_results(result: dict, search_key: str) -> str:
    """将 API 响应格式化为 Markdown 字符串。"""
    code = result.get("code", -1)
    msg = result.get("msg", "unknown error")

    if code != 0:
        return (
            f"## ❌ 搜索失败\n\n"
            f"- **错误码**：`{code}`\n"
            f"- **错误信息**：{msg}\n\n"
            f"请参考[飞书服务端错误码说明](https://open.feishu.cn/document/ukTMukTMukTM/ugjM14COyUjL4ITN)排查问题。"
        )

    data = result.get("data", {}) or {}
    docs_entities = data.get("docs_entities") or []
    total = data.get("total", 0)
    has_more = data.get("has_more", False)

    lines = [
        f"## 🔍 搜索结果：`{search_key}`\n",
        f"共找到 **{total}** 个相关文档，本次返回 **{len(docs_entities)}** 个。\n",
    ]

    if not docs_entities:
        lines.append("\n> 未找到任何相关文档，请尝试更换关键词。")
        return "\n".join(lines)

    # 表格头
    lines.append("| 序号 | 标题 | 类型 | 文档 Token |")
    lines.append("|:---:|---|:---:|---|")

    for idx, doc in enumerate(docs_entities, start=1):
        docs_token = doc.get("docs_token", "")
        docs_type = doc.get("docs_type", "")
        title = doc.get("title", "（无标题）").strip() or "（无标题）"
        link = build_feishu_link(docs_type, docs_token)
        type_label = TYPE_LABELS.get(docs_type, docs_type)

        lines.append(f"| {idx} | [{title}]({link}) | {type_label} | `{docs_token}` |")

    lines.append("")
    if has_more:
        lines.append("> 💡 还有更多结果，可通过增大 `--offset` 参数获取后续内容（注意 offset + count < 200）。")
    else:
        lines.append("> ✅ 已返回全部结果。")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="飞书云文档搜索工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 search.py --token "u-xxxx" --key "项目周报"
  python3 search.py --token "u-xxxx" --key "需求" --count 20 --types "doc,sheet"
  python3 search.py --token "u-xxxx" --key "OKR" --offset 10 --owners "ou_abc,ou_def"
        """,
    )
    parser.add_argument("--token", required=True, help="飞书 user_access_token（不含 Bearer 前缀）")
    parser.add_argument("--key", required=True, help="搜索关键词")
    parser.add_argument("--count", type=int, default=10, help="返回文档数量，范围 [1, 50]，默认 10")
    parser.add_argument("--offset", type=int, default=0, help="翻页偏移量，默认 0，offset + count < 200")
    parser.add_argument(
        "--types",
        default="",
        help="文件类型过滤，逗号分隔，可选值：doc,sheet,slides,bitable,mindnote,file。留空则搜全部",
    )
    parser.add_argument(
        "--owners",
        default="",
        help="文件所有者 Open ID，逗号分隔，如 ou_abc123,ou_def456。留空则不过滤",
    )
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="以原始 JSON 格式输出（供程序解析用），默认输出 Markdown",
    )

    args = parser.parse_args()

    # 参数校验
    if not (0 < args.count <= 50):
        print("❌ 错误：--count 必须在 1 到 50 之间", file=sys.stderr)
        sys.exit(1)
    if args.offset < 0:
        print("❌ 错误：--offset 不能为负数", file=sys.stderr)
        sys.exit(1)
    if args.offset + args.count >= 200:
        print("❌ 错误：offset + count 必须小于 200", file=sys.stderr)
        sys.exit(1)

    # 解析可选列表参数
    docs_types = [t.strip() for t in args.types.split(",") if t.strip()] or None
    owner_ids = [o.strip() for o in args.owners.split(",") if o.strip()] or None

    # 调用 API
    result = search_docs(
        token=args.token,
        search_key=args.key,
        count=args.count,
        offset=args.offset,
        docs_types=docs_types,
        owner_ids=owner_ids,
    )

    # 输出
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_results(result, args.key))


if __name__ == "__main__":
    main()
