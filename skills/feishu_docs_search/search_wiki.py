#!/usr/bin/env python3
"""
飞书 Wiki 知识库搜索脚本
API 文档：https://open.feishu.cn/document/server-docs/docs/wiki-v2/search_wiki

与 search_docs.py 的区别：
    - search_docs.py：搜索「我的空间」中的云文档（旧版接口）
    - search_wiki.py ：搜索用户有权访问的 Wiki 知识库节点（新版接口）

分页方式：
    Wiki 搜索使用「page_token 游标翻页」而非 offset，
    首次搜索不传 page_token，后续翻页传上次返回的 page_token。

用法示例：
    # 基本搜索
    python3 search_wiki.py --token "eyJ..." --key "项目周报"

    # 指定知识空间 ID
    python3 search_wiki.py --token "eyJ..." --key "周报" --space-id "7307457194084925443"

    # 控制每页返回数量
    python3 search_wiki.py --token "eyJ..." --key "周报" --page-size 20

    # 翻页（使用上次返回的 page_token）
    python3 search_wiki.py --token "eyJ..." --key "周报" --page-token "xxx"

    # 只输出原始 JSON（供程序解析）
    python3 search_wiki.py --token "eyJ..." --key "周报" --json-output
"""

import argparse
import json
import sys
import urllib.parse
import urllib.request
import urllib.error

# Wiki 搜索 API 地址
API_BASE_URL = "https://open.feishu.cn/open-apis/wiki/v2/nodes/search"

# obj_type 数字 → 文件类型名称
OBJ_TYPE_NAMES = {
    1:  ("doc",      "📄 文档"),
    2:  ("sheet",    "📊 电子表格"),
    3:  ("bitable",  "🗃️ 多维表格"),
    4:  ("mindnote", "🧠 思维笔记"),
    5:  ("file",     "📎 文件"),
    6:  ("slide",    "📑 幻灯片（已废弃）"),
    7:  ("wiki",     "📚 Wiki"),
    8:  ("docx",     "📄 文档"),
    9:  ("folder",   "📁 文件夹"),
    10: ("catalog",  "📂 目录"),
    11: ("slides",   "📑 幻灯片"),
}


def search_wiki(token: str, query: str, page_size: int = 20,
                page_token: str = "", space_id: str = "", node_id: str = "") -> dict:
    """
    调用飞书 Wiki 搜索 API。

    Args:
        token: user_access_token（不含 Bearer 前缀）
        query: 搜索关键词（不超过 50 个字符）
        page_size: 每页返回数量，范围 (0, 50]，默认 20
        page_token: 翻页游标，首次调用留空
        space_id: 知识空间 ID，为空则搜索全部
        node_id: 节点 ID（配合 space_id 使用），为空则搜索全部

    Returns:
        API 响应的完整 JSON 字典
    """
    # 查询参数（page_token 和 page_size 放在 URL query string）
    params = {"page_size": page_size}
    if page_token:
        params["page_token"] = page_token
    url = API_BASE_URL + "?" + urllib.parse.urlencode(params)

    # 请求体
    body_data = {"query": query}
    if space_id:
        body_data["space_id"] = space_id
    if node_id:
        body_data["node_id"] = node_id

    body = json.dumps(body_data).encode("utf-8")

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            return json.loads(error_body)
        except json.JSONDecodeError:
            return {"code": e.code, "msg": f"HTTP Error {e.code}: {error_body}", "data": None}
    except urllib.error.URLError as e:
        return {"code": -1, "msg": f"Network error: {e.reason}", "data": None}
    except Exception as e:
        return {"code": -1, "msg": f"Unexpected error: {str(e)}", "data": None}


def format_results(result: dict, query: str) -> str:
    """将 API 响应格式化为 Markdown 字符串。"""
    code = result.get("code", -1)
    msg = result.get("msg", "unknown error")

    if code != 0:
        return (
            f"## ❌ Wiki 搜索失败\n\n"
            f"- **错误码**：`{code}`\n"
            f"- **错误信息**：{msg}\n\n"
            f"请参考[飞书服务端错误码说明](https://open.feishu.cn/document/ukTMukTMukTM/ugjM14COyUjL4ITN)排查问题。"
        )

    data = result.get("data", {}) or {}
    items = data.get("items") or []
    has_more = data.get("has_more", False)
    next_page_token = data.get("page_token", "")

    lines = [
        f"## 📚 Wiki 搜索结果：`{query}`\n",
        f"本次返回 **{len(items)}** 个节点。\n",
    ]

    if not items:
        lines.append("\n> 未找到任何相关 Wiki 节点，请尝试更换关键词。")
        return "\n".join(lines)

    lines.append("| 序号 | 标题 | 类型 | 直达链接 |")
    lines.append("|:---:|---|:---:|---|")

    for idx, item in enumerate(items, start=1):
        title = (item.get("title") or "（无标题）").strip() or "（无标题）"
        url = item.get("url", "")
        obj_type = item.get("obj_type", 0)
        _, type_label = OBJ_TYPE_NAMES.get(obj_type, (str(obj_type), str(obj_type)))

        if url:
            title_cell = f"[{title}]({url})"
        else:
            title_cell = title

        lines.append(f"| {idx} | {title_cell} | {type_label} | `{item.get('node_id', '')}` |")

    lines.append("")
    if has_more:
        lines.append(
            f"> 💡 还有更多结果，用以下命令获取下一页：\n"
            f"> ```\n"
            f"> --page-token \"{next_page_token}\"\n"
            f"> ```"
        )
    else:
        lines.append("> ✅ 已返回全部结果。")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="飞书 Wiki 知识库搜索工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 search_wiki.py --token "eyJ..." --key "项目周报"
  python3 search_wiki.py --token "eyJ..." --key "周报" --space-id "7307457194084925443"
  python3 search_wiki.py --token "eyJ..." --key "周报" --page-token "上次返回的token"
        """,
    )
    parser.add_argument("--token", required=True, help="飞书 user_access_token（不含 Bearer 前缀）")
    parser.add_argument("--key", required=True, help="搜索关键词（不超过 50 个字符）")
    parser.add_argument(
        "--page-size", type=int, default=20,
        help="每页返回数量，范围 (0, 50]，默认 20"
    )
    parser.add_argument(
        "--page-token", default="",
        help="翻页游标，首次搜索不填，填上次返回的 page_token 获取下一页"
    )
    parser.add_argument(
        "--space-id", default="",
        help="知识空间 ID，为空则搜索全部有权访问的知识空间"
    )
    parser.add_argument(
        "--node-id", default="",
        help="节点 ID（需配合 --space-id 使用），限定在该节点及其子节点内搜索"
    )
    parser.add_argument(
        "--json-output", action="store_true",
        help="输出原始 JSON（供程序解析用），默认输出 Markdown 表格"
    )
    args = parser.parse_args()

    # 参数校验
    if len(args.key) > 50:
        print("❌ 错误：搜索关键词不能超过 50 个字符", file=sys.stderr)
        sys.exit(1)
    if not (0 < args.page_size <= 50):
        print("❌ 错误：--page-size 必须在 1 到 50 之间", file=sys.stderr)
        sys.exit(1)
    if args.node_id and not args.space_id:
        print("❌ 错误：使用 --node-id 时必须同时指定 --space-id", file=sys.stderr)
        sys.exit(1)

    result = search_wiki(
        token=args.token,
        query=args.key,
        page_size=args.page_size,
        page_token=args.page_token,
        space_id=args.space_id,
        node_id=args.node_id,
    )

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(format_results(result, args.key))


if __name__ == "__main__":
    main()
