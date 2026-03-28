#!/usr/bin/env python3
"""
可选步骤：刷新 user_access_token
API 端点：POST https://open.feishu.cn/open-apis/authen/v2/oauth/token
遵循 OAuth 2.0 标准（RFC 6749），grant_type=refresh_token

说明：
    - user_access_token 有效期约 2 小时，过期后需要刷新
    - 刷新后会同时返回新的 user_access_token 和新的 refresh_token
    - ⚠️ refresh_token 是一次性的！刷新成功后旧的 refresh_token 立即失效，
      新的 refresh_token 会自动覆盖写入 token_cache.json
    - refresh_token 有效期较长（通常 30 天），若过期则需重新走 get_oauth_code.py 全流程

前提条件：
    - 已运行过 get_user_token.py，本地存在 token_cache.json
    - 若需要 refresh_token，获取授权码时 scope 须包含 offline_access（本 Skill 默认已包含）

用法示例：
    # 自动从 token_cache.json 读取 refresh_token 刷新
    python3 refresh_token.py

    # 手动指定 refresh_token
    python3 refresh_token.py --refresh-token "xxxx"

    # 只输出新的 user_access_token（便于直接传给 search.py）
    python3 refresh_token.py --plain
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

# 脚本同目录的配置/缓存文件路径
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")
CACHE_PATH = os.path.join(SCRIPT_DIR, "token_cache.json")

# 飞书 OAuth token 端点（与获取 token 共用同一接口）
TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_token_cache() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {}
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_token_cache(data: dict):
    """将刷新后的 token 写回 token_cache.json（覆盖旧值）。"""
    cache = {
        "_comment": "飞书 user_access_token 缓存，由 get_user_token.py / refresh_token.py 自动生成，请勿手动编辑。",
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


def do_refresh(app_id: str, app_secret: str, refresh_token: str) -> dict:
    """
    调用飞书接口刷新 user_access_token。

    Returns:
        API 响应字典，成功时含 access_token、refresh_token、expires_in 等字段。
    """
    payload = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": app_id,
        "client_secret": app_secret,
    }).encode("utf-8")

    headers = {"Content-Type": "application/json; charset=utf-8"}
    req = urllib.request.Request(TOKEN_URL, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        try:
            return json.loads(error_body)
        except json.JSONDecodeError:
            return {"error": f"HTTP {e.code}", "error_description": error_body}
    except urllib.error.URLError as e:
        return {"error": "network_error", "error_description": str(e.reason)}
    except Exception as e:
        return {"error": "unexpected", "error_description": str(e)}


def check_token_status(cache: dict) -> tuple[bool, int]:
    """
    检查缓存的 token 是否过期。

    Returns:
        (is_expired: bool, seconds_remaining: int)
    """
    expires_at = cache.get("expires_at", 0)
    now = int(time.time())
    remaining = expires_at - now
    return remaining <= 0, remaining


def main():
    parser = argparse.ArgumentParser(
        description="刷新飞书 user_access_token（可选步骤）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python3 refresh_token.py                       # 自动从缓存读取
  python3 refresh_token.py --refresh-token "xxx" # 手动指定
  python3 refresh_token.py --plain               # 只输出新 token
  python3 refresh_token.py --check               # 只检查当前 token 剩余有效期
        """,
    )
    parser.add_argument(
        "--refresh-token",
        default="",
        help="手动指定 refresh_token（不填则自动从 token_cache.json 读取）",
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="只输出新的 user_access_token 字符串",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="只检查当前 token 剩余有效期，不执行刷新",
    )
    args = parser.parse_args()

    # 读取应用凭证
    config = load_config()
    app_id = config.get("app_id", "")
    app_secret = config.get("app_secret", "")

    if not app_id or app_id.startswith("cli_your_app_id"):
        print("❌ 错误：未配置有效的 app_id。", file=sys.stderr)
        sys.exit(1)

    # 读取缓存
    cache = load_token_cache()

    # --check 模式：只显示当前 token 状态
    if args.check:
        if not cache:
            print("❌ 未找到 token_cache.json，请先运行 get_user_token.py 获取 token。")
            sys.exit(1)
        is_expired, remaining = check_token_status(cache)
        token_preview = cache.get("user_access_token", "")[:20] + "..."
        if is_expired:
            print(f"⚠️  user_access_token 已过期")
            print(f"   token（前20位）: {token_preview}")
            print(f"   建议立即运行：python3 ./refresh_token.py")
        else:
            hours, rem = divmod(remaining, 3600)
            minutes = rem // 60
            print(f"✅ user_access_token 仍有效")
            print(f"   剩余有效期：{hours} 小时 {minutes} 分钟（{remaining} 秒）")
            print(f"   token（前20位）: {token_preview}")
        return

    # 确定要使用的 refresh_token
    refresh_tok = args.refresh_token or cache.get("refresh_token", "")

    if not refresh_tok:
        print("❌ 未找到 refresh_token。", file=sys.stderr)
        print("   请先运行 get_oauth_code.py + get_user_token.py 完成初次授权。", file=sys.stderr)
        print(f"   或通过 --refresh-token 手动传入。", file=sys.stderr)
        sys.exit(1)

    if not args.plain:
        # 先提示当前 token 状态
        if cache:
            is_expired, remaining = check_token_status(cache)
            if not is_expired:
                hours, rem = divmod(remaining, 3600)
                minutes = rem // 60
                print(f"ℹ️  当前 token 剩余有效期：{hours} 小时 {minutes} 分钟")
        print("🔄 正在刷新 user_access_token...")

    result = do_refresh(app_id, app_secret, refresh_tok)

    # 错误处理
    if "error" in result or "access_token" not in result:
        error_code = result.get("error", "unknown")
        error_desc = result.get("error_description", str(result))
        print(f"❌ 刷新失败", file=sys.stderr)
        print(f"   错误：{error_code}", file=sys.stderr)
        print(f"   描述：{error_desc}", file=sys.stderr)
        if "invalid_grant" in str(error_code) or "refresh" in str(error_desc).lower():
            print("   💡 refresh_token 已过期或已被使用，请重新运行完整授权流程：", file=sys.stderr)
            print("      python3 ./get_oauth_code.py && python3 ./get_user_token.py --code <code>", file=sys.stderr)
        sys.exit(1)

    # 成功：保存新 token
    new_cache = save_token_cache(result)
    new_token = new_cache["user_access_token"]
    new_refresh = new_cache["refresh_token"]
    expires_in = new_cache["expires_in"]

    if args.plain:
        print(new_token)
        return

    print()
    print("✅ 刷新成功！")
    print(f"   新 user_access_token : {new_token[:40]}...")
    print(f"   有效期               : {expires_in} 秒（约 {expires_in // 3600} 小时）")
    print(f"   新 refresh_token     : {new_refresh[:20]}...（已自动更新至缓存）")
    print()
    print(f"💾 已覆盖写入：{CACHE_PATH}")
    print()
    print("⚠️  旧的 refresh_token 现已失效，请勿再使用。")
    print()
    print("现在可以继续搜索：")
    print(f'   python3 ./search.py --token "{new_token}" --key "关键词"')


if __name__ == "__main__":
    main()
