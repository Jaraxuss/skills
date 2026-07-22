#!/usr/bin/env python3
"""Create a customer journey (客户旅程) record into BOSS.

Endpoint: POST https://boss-api.shadow-rpa.net/boss/api/v3/oms/crm/customTravel/create
Authenticates using yingdao-boss-data-hub's internal Boss credentials config.

Usage — CLI:
    python3 skills/yingdao-boss-data-hub/scripts/create_customer_journey.py --payload payload.json
    cat payload.json | python3 skills/yingdao-boss-data-hub/scripts/create_customer_journey.py --stdin

Usage — Python module:
    from create_customer_journey import build_payload, create_customer_journey
    resp = create_customer_journey(build_payload(**fields))
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Import shared auth logic from fetch_clients
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REPO_ROOT = SKILL_DIR.parent.parent

try:
    import requests  # noqa: E402
except ModuleNotFoundError as exc:  # pragma: no cover
    print(
        f"Missing dependency: {exc.name}. Run `pip install -r skills/yingdao-boss-data-hub/scripts/requirements.txt` first.",
        file=sys.stderr,
    )
    sys.exit(1)

from fetch_clients import (
    ApiError,
    SkillConfigError,
    build_session,
    load_json,
    login_to_yingdao_boss,
    DEFAULT_CONFIG_PATH,
)

# ---------------------------------------------------------------------------
# Constants — 只保留抓包铁证的接口层固定字段；业务字段全部走参数
# ---------------------------------------------------------------------------

WRITE_URL = "https://boss-api.shadow-rpa.net/boss/api/v3/oms/crm/customTravel/create"

# 接口层不可变字段
FIXED_TYPE = "customer_follow"  # 记录类型
FIXED_FOLLOWUP_TYPE = "其他"  # 触发 templateData 富文本框的模板条件
FIXED_IS_DRAFT = False  # 正式提交
CONTENT_PREFIX = "<strong>跟进重点总结</strong>："

# 业务枚举（用于入参校验，全部由外部传入，不设默认值）
ALLOWED_OPERATOR_ROLES: tuple[str, ...] = ("客户成功", "技术支持", "其他")
ALLOWED_ROLE_NAMES: tuple[str, ...] = ("customerSuccess", "technicalSupport", "other")
ALLOWED_FOLLOWUP_OBJECTS: tuple[str, ...] = (
    "决策者",
    "项目负责人",
    "业务使用方",
    "影刀内部人员",
    "开发者",
    "采购",
)
ALLOWED_CUSTOMER_STAGES: tuple[str, ...] = (
    "启动期",
    "成长期",
    "续费期",
    "多年客户",
    "流失",
)
ALLOWED_FOLLOWUP_WAYS: tuple[str, ...] = (
    "线上-IM沟通",
    "线上-远程会议",
    "线下-市内外出",
    "线下-跨市出差",
    "线下-客户来访",
)

# templateData.primaryKey 按 operatorRole 映射（抓包实测）
# "其他" 角色的 primaryKey 未抓到，需外部通过 template_primary_key 显式传入
TEMPLATE_PRIMARY_KEY_BY_ROLE: dict[str, str] = {
    "客户成功": "recuHG94PrF0ce",
    "技术支持": "recuHGictTes6J",
}


class JourneyWriteError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def _require_str(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JourneyWriteError(f"{name} is required (non-empty string)")
    return value.strip()


def _require_in(value: str, allowed: tuple[str, ...], name: str) -> str:
    if value not in allowed:
        raise JourneyWriteError(f"{name}={value!r} not in allowed set {allowed}")
    return value


def _require_list_of_str(value: Any, name: str) -> list[str]:
    if not isinstance(value, (list, tuple)) or not value:
        raise JourneyWriteError(f"{name} is required (non-empty list)")
    result: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise JourneyWriteError(f"{name}[{i}] must be a non-empty string")
        result.append(item.strip())
    return result


def _require_subset(
    values: list[str], allowed: tuple[str, ...], name: str
) -> list[str]:
    for v in values:
        if v not in allowed:
            raise JourneyWriteError(
                f"{name} contains {v!r} not in allowed set {allowed}"
            )
    return values


# ---------------------------------------------------------------------------
# Payload builder
# ---------------------------------------------------------------------------


def build_payload(
    *,
    # ── 业务字段（全部必传，无默认值）─────────────────────
    custom_id: int,
    operator_role: str,  # 客户成功 / 技术支持 / 其他
    role_name: str,  # customerSuccess / technicalSupport / other
    follow_up_time: str,  # yyyy-MM-dd
    customer_stage: str,  # 启动期/成长期/续费期/多年客户/流失
    followup_object: list[str],  # 6 选枚举子集
    followup_way: str,  # 5 选枚举
    followup_user_id: list[str],  # 同行人 UUID 数组
    followup_user_name: list[str],  # 同行人姓名数组（与 UUID 同序）
    summary_html: str,  # 跟进重点总结（HTML）
    next_plan: str,  # 下一步计划（纯文本）
    # ── 覆盖项（None 时走默认策略）─────────────────────
    template_primary_key: str | None = None,  # None 时按 operator_role 查内置映射
) -> dict[str, Any]:
    """Assemble the exact JSON body expected by /customTravel/create.

    所有业务字段必传；接口层固定字段（type / followupType / isDraft / content 前缀）
    在函数内部注入，不对外暴露。
    """
    # 基础校验
    if not isinstance(custom_id, int) or custom_id <= 0:
        raise JourneyWriteError("custom_id must be a positive int")

    operator_role = _require_in(
        _require_str(operator_role, "operator_role"),
        ALLOWED_OPERATOR_ROLES,
        "operator_role",
    )
    role_name = _require_in(
        _require_str(role_name, "role_name"), ALLOWED_ROLE_NAMES, "role_name"
    )
    follow_up_time = _require_str(follow_up_time, "follow_up_time")
    customer_stage = _require_in(
        _require_str(customer_stage, "customer_stage"),
        ALLOWED_CUSTOMER_STAGES,
        "customer_stage",
    )

    followup_object = _require_subset(
        _require_list_of_str(followup_object, "followup_object"),
        ALLOWED_FOLLOWUP_OBJECTS,
        "followup_object",
    )
    followup_way = _require_in(
        _require_str(followup_way, "followup_way"),
        ALLOWED_FOLLOWUP_WAYS,
        "followup_way",
    )

    followup_user_id = _require_list_of_str(followup_user_id, "followup_user_id")
    followup_user_name = _require_list_of_str(followup_user_name, "followup_user_name")
    if len(followup_user_id) != len(followup_user_name):
        raise JourneyWriteError(
            "followup_user_id and followup_user_name must be same length and aligned"
        )

    summary_html = _require_str(summary_html, "summary_html")
    next_plan = _require_str(next_plan, "next_plan")

    # primaryKey 解析
    primary_key = template_primary_key or TEMPLATE_PRIMARY_KEY_BY_ROLE.get(
        operator_role
    )
    if not primary_key:
        raise JourneyWriteError(
            f"template_primary_key is required for operator_role={operator_role!r} "
            f"(no built-in mapping). Known roles: {list(TEMPLATE_PRIMARY_KEY_BY_ROLE)}."
        )

    return {
        "customId": int(custom_id),
        "type": FIXED_TYPE,
        "isDraft": FIXED_IS_DRAFT,
        "content": f"{CONTENT_PREFIX}{summary_html}",
        "formData": {
            "operatorRole": operator_role,
            "roleName": role_name,
            "followUpTime": follow_up_time,
            "customerStage": customer_stage,
            "followupObject": list(followup_object),
            "followupType": FIXED_FOLLOWUP_TYPE,
            "followupWay": followup_way,
            "followupUserId": list(followup_user_id),
            "followupUserName": list(followup_user_name),
            "nextPlan": next_plan,
            "templateData": [
                {
                    "primaryKey": primary_key,
                    "fieldName": "跟进重点总结",
                    primary_key: summary_html,
                }
            ],
        },
    }


# ---------------------------------------------------------------------------
# HTTP call
# ---------------------------------------------------------------------------


def create_customer_journey(
    payload: dict[str, Any],
    *,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    """POST payload to customTravel/create. Returns raw response JSON.

    Auth: Uses yingdao-boss-data-hub internal authentication.
    """
    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH
    config = load_json(Path(config_path))
    session = build_session(config)
    
    access_token = login_to_yingdao_boss(session, config)

    headers = {
        "accept": "*/*",
        "authorization": f"Bearer {access_token}",
        "content-type": "application/json",
        "origin": "https://boss.shadow-rpa.net",
        "referer": "https://boss.shadow-rpa.net/",
        "page-route": f"/manage/microApp/boss/oms/customerDetail/{payload.get('customId')}/customer-travel",
    }
    verify = (config.get("ssl_verify") or {}).get("default", True)

    try:
        response = session.post(
            WRITE_URL, headers=headers, json=payload, verify=verify, timeout=60
        )
        response.raise_for_status()
        body = response.json()
    except requests.RequestException as exc:
        raise JourneyWriteError(f"HTTP request failed: {exc}") from exc
    except ValueError as exc:
        raise JourneyWriteError(f"Non-JSON response: {response.text[:500]}") from exc

    code = body.get("code")
    if code not in (200, 0, "200", None) or body.get("success") is False:
        raise JourneyWriteError(
            f"Business error from BOSS: code={code} msg={body.get('msg') or body.get('message')}"
        )

    return body


# Alias for backward compatibility
write_journey = create_customer_journey


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# 与 build_payload 参数对齐（snake_case 白名单）
_BUILD_KWARGS = {
    "custom_id",
    "operator_role",
    "role_name",
    "follow_up_time",
    "customer_stage",
    "followup_object",
    "followup_way",
    "followup_user_id",
    "followup_user_name",
    "summary_html",
    "next_plan",
    "template_primary_key",
}


def _load_payload_from_args(args: argparse.Namespace) -> dict[str, Any]:
    if args.stdin:
        raw = sys.stdin.read()
    elif args.payload:
        raw = Path(args.payload).expanduser().resolve().read_text(encoding="utf-8")
    else:
        raise JourneyWriteError("Provide --payload <file> or --stdin")

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise JourneyWriteError(f"Invalid JSON: {exc}") from exc

    # 已是完整 payload → 原样发送
    if isinstance(obj, dict) and "formData" in obj and "customId" in obj:
        return obj

    # 否则按 build_payload kwargs 组装
    kwargs = {k: v for k, v in obj.items() if k in _BUILD_KWARGS}
    return build_payload(**kwargs)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a customer journey record to BOSS."
    )
    parser.add_argument("--payload", default="", help="Path to JSON payload file.")
    parser.add_argument(
        "--stdin", action="store_true", help="Read JSON payload from stdin."
    )
    parser.add_argument(
        "--config", default="", help="Path to config.local.json override."
    )
    parser.add_argument(
        "--print-enums",
        action="store_true",
        help="Print allowed enum values (roles/objects/stages/ways) as JSON and exit.",
    )
    return parser.parse_args()


def _print_enums() -> None:
    print(
        json.dumps(
            {
                "operator_role": list(ALLOWED_OPERATOR_ROLES),
                "role_name": list(ALLOWED_ROLE_NAMES),
                "followup_object": list(ALLOWED_FOLLOWUP_OBJECTS),
                "customer_stage": list(ALLOWED_CUSTOMER_STAGES),
                "followup_way": list(ALLOWED_FOLLOWUP_WAYS),
                "template_primary_key_by_role": TEMPLATE_PRIMARY_KEY_BY_ROLE,
                "fixed": {
                    "type": FIXED_TYPE,
                    "followupType": FIXED_FOLLOWUP_TYPE,
                    "isDraft": FIXED_IS_DRAFT,
                    "content_prefix": CONTENT_PREFIX,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def _cli_main() -> int:
    args = _parse_args()
    if args.print_enums:
        _print_enums()
        return 0
    try:
        payload = _load_payload_from_args(args)
        response = create_customer_journey(
            payload,
            config_path=args.config or None,
        )
        print(
            json.dumps(
                {"ok": True, "request": payload, "response": response},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except (JourneyWriteError, SkillConfigError, ApiError) as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(_cli_main())
