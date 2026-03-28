#!/usr/bin/env python3
"""
获取飞书自建应用 tenant_access_token
API 文档：https://open.feishu.cn/document/server-docs/authentication-management/access-token/tenant_access_token_internal

用法示例：
    # 从 config.json 读取凭证（推荐）
    python3 get_token.py

    # 直接指定凭证（优先级高于 config.json）
    python3 get_token.py --app-id "cli_xxx" --app-secret "xxxxx"

    # 只输出 token 字符串（适合管道或嵌入 shell 脚本）
    python3 get_token.py --plain

注意：
    tenant_access_token 代表"应用"身份，有效期最长 2 小时。
    搜索云文档 API 需要 user_access_token（代表用户身份）才能返回该用户可见的文档。
    若你使用 tenant_access_token 调用搜索接口，搜索结果为空或受限是正常现象。
    如需以用户身份搜索，请通过 OAuth 2.0 流程获取 user_access_token。
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error

# 配置文件路径（与本脚本同目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

# 飞书获取 tenant_access_token 的接口
API_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"


def load_config() -> dict:
    """从 config.json 读取 app_id 和 app_secret。"""
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_tenant_access_token(app_id: str, app_secret: str) -> dict:
    """
    调用飞书接口获取 tenant_access_token。

    Returns:
        包含 tenant_access_token、expire、code、msg 的字典。
    """
    payload = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    headers = {"Content-Type": "application/json; charset=utf-8"}

    req = urllib.request.Request(API_URL, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            return json.loads(error_body)
        except json.JSONDecodeError:
            return {"code": e.code, "msg": f"HTTP Error {e.code}: {error_body}"}
    except urllib.error.URLError as e:
        return {"code": -1, "msg": f"Network error: {e.reason}"}
    except Exception as e:
        return {"code": -1, "msg": f"Unexpected error: {str(e)}"}


def main():
    parser = argparse.ArgumentParser(
        description="获取飞书自建应用 tenant_access_token",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 get_token.py                            # 从 config.json 读取凭证
  python3 get_token.py --app-id cli_x --app-secret yyy  # 直接传入凭证
  python3 get_token.py --plain                    # 只输出 token 字符串
        """,
    )
    parser.add_argument("--app-id", help="飞书应用 App ID（优先于 config.json）")
    parser.add_argument("--app-secret", help="飞书应用 App Secret（优先于 config.json）")
    parser.add_argument(
        "--plain",
        action="store_true",
        help="只输出 token 字符串，不输出其他信息（便于脚本间传递）",
    )
    args = parser.parse_args()

    # 加载配置，CLI 参数优先
    config = load_config()
    app_id = args.app_id or config.get("app_id", "")
    app_secret = args.app_secret or config.get("app_secret", "")

    # 检查占位符是否被替换
    if not app_id or app_id.startswith("cli_your_app_id"):
        print("❌ 错误：未配置有效的 app_id。", file=sys.stderr)
        print(f"   请编辑 {CONFIG_PATH} 填入真实的 app_id 和 app_secret。", file=sys.stderr)
        sys.exit(1)
    if not app_secret or app_secret == "your_app_secret_here":
        print("❌ 错误：未配置有效的 app_secret。", file=sys.stderr)
        print(f"   请编辑 {CONFIG_PATH} 填入真实的 app_id 和 app_secret。", file=sys.stderr)
        sys.exit(1)

    result = get_tenant_access_token(app_id, app_secret)

    if result.get("code", -1) != 0:
        if args.plain:
            print("", file=sys.stderr)  # plain 模式下 stderr 输出错误
        print(f"❌ 获取 token 失败", file=sys.stderr)
        print(f"   错误码：{result.get('code')}", file=sys.stderr)
        print(f"   错误信息：{result.get('msg')}", file=sys.stderr)
        sys.exit(1)

    token = result["tenant_access_token"]
    expire = result.get("expire", 7200)

    if args.plain:
        # 只输出 token，方便直接传给 search.py
        print(token)
    else:
        print(f"✅ 获取成功！")
        print(f"   tenant_access_token: {token}")
        print(f"   有效期：{expire} 秒（约 {expire // 60} 分钟）")
        print()
        print("⚠️  注意：tenant_access_token 代表「应用」身份。")
        print("   搜索云文档接口建议使用 user_access_token（代表用户身份）。")
        print("   若搜索结果为空，请确认使用的是 user_access_token。")
        print()
        print("可将此 token 传给 search.py：")
        print(f'   python3 ./search.py --token "{token}" --key "关键词"')


if __name__ == "__main__":
    main()
