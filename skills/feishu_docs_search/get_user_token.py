#!/usr/bin/env python3
"""
第四步：用授权码换取飞书 user_access_token (及 refresh_token)
API 端点：POST https://open.feishu.cn/open-apis/authen/v2/oauth/token
遵循 OAuth 2.0 标准（RFC 6749）

用法示例：
    python3 get_user_token.py --code "fJGmB73FyF..."
    python3 get_user_token.py --code "xxx" --plain   # 只输出 user_access_token 字符串

输出：
    - 默认将 user_access_token 和 refresh_token 同时写入 token_cache.json 供后续脚本复用
    - --plain 模式只打印 token 字符串

注意：
    code 只能使用一次，且有效期约 5 分钟，请在获取后立即运行。
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

# 配置文件路径（与本脚本同目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
CACHE_PATH = os.path.join(SCRIPT_DIR, "token_cache.json")

# 飞书 OAuth token 端点
TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"


def load_config() -> dict:
    """从 config.json 读取 app_id 和 app_secret。"""
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_token_cache(data: dict):
    """将 token 信息缓存到本地 token_cache.json，便于后续脚本直接读取复用。"""
    cache = {
        "_comment": "飞书 user_access_token 缓存，由 get_user_token.py 自动生成，请勿手动编辑。",
        "user_access_token": data.get("access_token", ""),
        "refresh_token": data.get("refresh_token", ""),
        "token_type": data.get("token_type", "Bearer"),
        "expires_in": data.get("expires_in", 0),
        "refresh_expires_in": data.get("refresh_expires_in", 0),
        "scope": data.get("scope", ""),
        "saved_at": int(time.time()),
        "expires_at": int(time.time()) + data.get("expires_in", 0),
    }
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    return cache


def exchange_code_for_token(app_id: str, app_secret: str, code: str, redirect_uri: str) -> dict:
    """
    用授权码换取 user_access_token。

    Args:
        app_id: 应用 App ID
        app_secret: 应用 App Secret
        code: 上一步获取的 OAuth 授权码
        redirect_uri: 与授权时完全一致的回调地址

    Returns:
        API 响应的完整 JSON 字典
    """
    payload = json.dumps({
        "grant_type": "authorization_code",
        "code": code,
        "client_id": app_id,
        "client_secret": app_secret,
        "redirect_uri": redirect_uri,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json; charset=utf-8",
    }

    req = urllib.request.Request(TOKEN_URL, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            return json.loads(error_body)
        except json.JSONDecodeError:
            return {"code": e.code, "error": f"HTTP Error {e.code}: {error_body}"}
    except urllib.error.URLError as e:
        return {"code": -1, "error": f"Network error: {e.reason}"}
    except Exception as e:
        return {"code": -1, "error": f"Unexpected error: {str(e)}"}


def main():
    parser = argparse.ArgumentParser(
        description="用 OAuth 授权码换取飞书 user_access_token（第四步）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 get_user_token.py --code "fJGmB73FyF14A76b8accCfGCJ2CBCc13"
  python3 get_user_token.py --code "xxx" --plain   # 只输出 token
        """,
    )
    parser.add_argument("--code", required=True, help="第三步获取的 OAuth 授权码")
    parser.add_argument(
        "--redirect-uri",
        default="http://localhost:9527/callback",
        help="授权时使用的回调地址，必须与 get_oauth_code.py 中一致，默认 http://localhost:9527/callback",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="只输出 user_access_token 字符串（便于传给 search.py）",
    )
    args = parser.parse_args()

    # 读取应用凭证
    config = load_config()
    app_id = config.get("app_id", "")
    app_secret = config.get("app_secret", "")

    if not app_id or app_id.startswith("cli_your_app_id"):
        print("❌ 错误：未配置有效的 app_id。", file=sys.stderr)
        print(f"   请编辑 {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)
    if not app_secret or app_secret == "your_app_secret_here":
        print("❌ 错误：未配置有效的 app_secret。", file=sys.stderr)
        sys.exit(1)

    if not args.plain:
        print("🔄 正在用授权码换取 user_access_token...")

    result = exchange_code_for_token(app_id, app_secret, args.code, args.redirect_uri)

    # 飞书 v2 OAuth token 端点，成功时无 code 字段，直接有 access_token
    # 失败时有 error 或 error_description 字段
    if "error" in result or "access_token" not in result:
        error_code = result.get("error", result.get("code", "unknown"))
        error_desc = result.get("error_description", result.get("msg", str(result)))
        if args.plain:
            print(f"error", file=sys.stderr)
        print(f"❌ 获取失败", file=sys.stderr)
        print(f"   错误：{error_code}", file=sys.stderr)
        print(f"   描述：{error_desc}", file=sys.stderr)
        if "invalid_grant" in str(error_code) or "code" in str(error_desc).lower():
            print("   💡 提示：code 已过期或已被使用，请重新运行 get_oauth_code.py 获取新的 code。", file=sys.stderr)
        sys.exit(1)

    # 成功 —— 缓存并输出
    cache = save_token_cache(result)
    token = cache["user_access_token"]
    refresh_token = cache["refresh_token"]
    expires_in = cache["expires_in"]
    refresh_expires_in = cache.get("refresh_expires_in", 0)

    if args.plain:
        print(token)
        return

    print()
    print("✅ user_access_token 获取成功！")
    print(f"   user_access_token : {token}")
    print(f"   有效期             : {expires_in} 秒（约 {expires_in // 3600} 小时）")
    if refresh_token:
        print(f"   refresh_token     : {refresh_token}")
        print(f"   refresh 有效期    : {refresh_expires_in} 秒（约 {refresh_expires_in // 86400} 天）")
    print()
    print(f"💾 已缓存至：{CACHE_PATH}")
    print()
    print("现在可以用此 token 搜索飞书云文档：")
    print(f'   python3 ./search.py --token "{token}" --key "关键词"')
    print()
    if refresh_token:
        print("如需刷新 token（在过期前）：")
        print(f'   python3 ./refresh_token.py   # 自动从 token_cache.json 读取 refresh_token')


if __name__ == "__main__":
    main()
