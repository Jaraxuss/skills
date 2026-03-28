#!/usr/bin/env python3
"""
第三步：获取飞书 OAuth 授权码 (code)
API 文档：https://open.feishu.cn/document/authentication-management/access-token/obtain-oauth-code

工作原理：
    1. 在本地启动一个临时 HTTP 服务器（默认监听 http://localhost:9527/callback）
    2. 用浏览器自动打开飞书 OAuth 授权页面
    3. 用户在浏览器中点击「同意授权」
    4. 飞书将浏览器重定向到本地回调地址，携带 code 参数
    5. 本地服务器捕获 code，打印到终端，服务器自动关闭

前提条件：
    - config.json 中已填入 app_id 和 app_secret
    - 在飞书开放平台「安全设置」→「重定向 URL」中添加：http://localhost:9527/callback
      （只需配置一次，开发环境用）

用法示例：
    python3 get_oauth_code.py
    python3 get_oauth_code.py --port 8080
    python3 get_oauth_code.py --scope "search:docs:read offline_access"
    python3 get_oauth_code.py --plain   # 只输出 code 字符串
"""

import argparse
import hashlib
import json
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

# 配置文件路径（与本脚本同目录）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")

# 飞书 OAuth 授权页地址
AUTHORIZE_URL = "https://accounts.feishu.cn/open-apis/authen/v1/authorize"

# 默认权限（搜索云文档所需）
DEFAULT_SCOPE = "search:docs:read"

# 用于在线程间传递结果
_result = {"code": None, "error": None, "state": None}
_server_instance = None


def load_config() -> dict:
    """从 config.json 读取应用凭证。"""
    if not os.path.exists(CONFIG_PATH):
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_auth_url(app_id: str, redirect_uri: str, scope: str, state: str) -> str:
    """构造飞书 OAuth 授权页 URL。"""
    params = {
        "client_id": app_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state,
        "prompt": "consent",
    }
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode(params)


def make_callback_handler(expected_state: str, plain: bool):
    """工厂函数：创建一个绑定了 state 校验的回调处理器。"""

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            global _server_instance

            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            code = params.get("code", [None])[0]
            error = params.get("error", [None])[0]
            returned_state = params.get("state", [None])[0]

            # 校验 state，防止 CSRF
            if returned_state != expected_state:
                _result["error"] = f"state 不匹配！期望 {expected_state}，收到 {returned_state}"
                self._respond_html("❌ 安全校验失败", "state 参数不匹配，请重新运行脚本。", success=False)
            elif error:
                _result["error"] = error
                self._respond_html("❌ 授权被拒绝", f"用户拒绝了授权：{error}", success=False)
            else:
                _result["code"] = code
                _result["state"] = returned_state
                self._respond_html(
                    "✅ 授权成功！",
                    "授权码已获取，请返回终端查看。<br>你可以关闭此标签页。",
                    success=True,
                )

            # 在独立线程中关闭服务器，避免阻塞当前响应
            threading.Thread(target=_server_instance.shutdown, daemon=True).start()

        def _respond_html(self, title: str, body: str, success: bool):
            color = "#2d8a4e" if success else "#c0392b"
            html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>{title}</title>
<style>
  body {{font-family: -apple-system, sans-serif; display:flex; align-items:center;
        justify-content:center; height:100vh; margin:0; background:#f5f5f5;}}
  .card {{background:white; border-radius:12px; padding:40px 60px; text-align:center;
          box-shadow:0 4px 20px rgba(0,0,0,0.1);}}
  h1 {{color:{color}; margin-bottom:12px;}}
  p {{color:#666;}}
</style>
</head>
<body><div class="card"><h1>{title}</h1><p>{body}</p></div></body>
</html>"""
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))

        def log_message(self, format, *args):
            # 屏蔽默认的 HTTP 访问日志
            pass

    return CallbackHandler


def get_oauth_code(app_id: str, port: int, scope: str, plain: bool) -> str | None:
    """
    启动本地回调服务器，打开浏览器获取 OAuth code。

    Returns:
        成功返回 code 字符串，失败返回 None。
    """
    global _server_instance

    redirect_uri = f"http://localhost:{port}/callback"

    # 生成随机 state（防 CSRF）
    state = secrets.token_urlsafe(16)

    auth_url = build_auth_url(app_id, redirect_uri, scope, state)

    # 启动本地 HTTP 服务器
    handler = make_callback_handler(state, plain)
    try:
        server = HTTPServer(("localhost", port), handler)
    except OSError as e:
        print(f"❌ 无法在端口 {port} 启动本地服务器：{e}", file=sys.stderr)
        print(f"   请用 --port 指定其他端口，或检查该端口是否已被占用。", file=sys.stderr)
        return None

    _server_instance = server

    if not plain:
        print(f"🌐 正在浏览器中打开飞书授权页面...")
        print(f"   如果浏览器未自动打开，请手动访问以下地址：")
        print(f"   {auth_url}")
        print()
        print(f"⏳ 等待用户在浏览器中完成授权（本地监听 {redirect_uri}）...")

    # 用独立线程打开浏览器，避免阻塞服务器
    threading.Timer(0.5, lambda: webbrowser.open(auth_url)).start()

    # 阻塞等待回调（serve_forever 直到 shutdown() 被调用）
    server.serve_forever()

    return _result.get("code")


def main():
    parser = argparse.ArgumentParser(
        description="获取飞书 OAuth 授权码 (step 3 of user_access_token flow)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
前提：在飞书开放平台「安全设置」→「重定向 URL」中添加 http://localhost:9527/callback

示例：
  python3 get_oauth_code.py
  python3 get_oauth_code.py --port 8080
  python3 get_oauth_code.py --scope "search:docs:read offline_access"
  python3 get_oauth_code.py --plain   # 只输出 code，便于传给下一步脚本
        """,
    )
    parser.add_argument(
        "--port", type=int, default=9527, help="本地回调监听端口，默认 9527"
    )
    parser.add_argument(
        "--scope",
        default=DEFAULT_SCOPE,
        help=f'请求的权限范围（空格分隔），默认："{DEFAULT_SCOPE}"',
    )
    parser.add_argument(
        "--plain",
        action="store_true",
        help="只输出 code 字符串（便于传给 get_user_token.py）",
    )
    args = parser.parse_args()

    # 读取配置
    config = load_config()
    app_id = config.get("app_id", "")

    if not app_id or app_id.startswith("cli_your_app_id"):
        print("❌ 错误：未配置有效的 app_id。", file=sys.stderr)
        print(f"   请编辑 {CONFIG_PATH} 填入真实凭证。", file=sys.stderr)
        sys.exit(1)

    redirect_uri = f"http://localhost:{args.port}/callback"

    if not args.plain:
        print("=" * 60)
        print("  飞书 OAuth 授权码获取工具")
        print("=" * 60)
        print(f"  App ID    : {app_id}")
        print(f"  回调地址   : {redirect_uri}")
        print(f"  请求权限   : {args.scope}")
        print()
        print("⚠️  确保以下地址已在飞书开放平台「安全设置」中配置为重定向 URL：")
        print(f"   {redirect_uri}")
        print()

    code = get_oauth_code(
        app_id=app_id,
        port=args.port,
        scope=args.scope,
        plain=args.plain,
    )

    if _result.get("error"):
        print(f"❌ 授权失败：{_result['error']}", file=sys.stderr)
        sys.exit(1)

    if not code:
        print("❌ 未获取到授权码，请重试。", file=sys.stderr)
        sys.exit(1)

    if args.plain:
        print(code)
    else:
        print()
        print("✅ 授权码获取成功！")
        print(f"   code: {code}")
        print()
        print("下一步：将此 code 传给第四步脚本获取 user_access_token：")
        print(f'   python3 ./get_user_token.py --code "{code}"')
        print()
        print("⚠️  注意：code 只能使用一次，且有效期极短（约 5 分钟），请立即执行下一步。")


if __name__ == "__main__":
    main()
