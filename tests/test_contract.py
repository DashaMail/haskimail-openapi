"""Контрактные тесты: реальные ответы Haskimail API против спецификации.

1. test_recorded_responses — ответы, записанные с живого API 30.10.2026 (через MCP Haskimail).
   Работают офлайн.
2. test_live_* — запросы к https://api.haskimail.ru. Запускаются, только если задан
   HASKIMAIL_RUN_LIVE=1 и ключи HASKIMAIL_SERVER_TOKEN / HASKIMAIL_ACCOUNT_TOKEN.
   Только чтение; отправка — с тестовым ключом HASKIMAIL_API_TEST (письмо не уходит).
"""
import json
import os
from pathlib import Path

import pytest

HERE = Path(__file__).parent
BASE = os.environ.get("HASKIMAIL_BASE_URL", "https://api.haskimail.ru")
SERVER = os.environ.get("HASKIMAIL_SERVER_TOKEN")
ACCOUNT = os.environ.get("HASKIMAIL_ACCOUNT_TOKEN")
LIVE = os.environ.get("HASKIMAIL_RUN_LIVE") == "1"

RECORDED = json.loads((HERE / "fixtures_live_responses.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("key", list(RECORDED))
def test_recorded_responses(checker, key):
    method, path, status = key.split()
    schema = checker.response_schema(method, path, status)
    assert schema is not None, f"{key}: HTTP {status} не описан у операции"
    errs = checker.errors(schema, RECORDED[key])
    assert not errs, "\n".join(errs)


# ----------------------------------------------------------------------------- live
live = pytest.mark.skipif(not LIVE, reason="HASKIMAIL_RUN_LIVE=1 не задан")


def call(method, path, token_header, token, params=None, body=None):
    import requests

    headers = {"Accept": "application/json", token_header: token}
    if body is not None:
        headers["Content-Type"] = "application/json"
    return requests.request(method, BASE + path, headers=headers, params=params, json=body, timeout=30)


def check(checker, method, template, resp):
    schema = checker.response_schema(method, template, resp.status_code)
    assert schema is not None, f"{method} {template}: HTTP {resp.status_code} не описан. Тело: {resp.text[:300]}"
    errs = checker.errors(schema, resp.json())
    assert not errs, f"{method} {template} {resp.status_code}:\n" + "\n".join(errs)
    return resp.json()


SERVER_GETS = [
    ("/message-streams", None), ("/templates", {"count": 5}), ("/webhooks", None),
    ("/messages", {"count": 5}), ("/messages/opens", {"count": 5}), ("/messages/clicks", {"count": 5}),
    ("/messages/inbound", {"count": 5}), ("/bounces", {"count": 5}), ("/deliverystats", None),
    ("/triggers/inboundrules", None), ("/stats", None), ("/stats/sends", None), ("/stats/bounces", None),
    ("/stats/spam", None), ("/stats/opens", None), ("/stats/clicks", None), ("/stats/opens/platforms", None),
    ("/stats/opens/emailclients", None), ("/stats/clicks/browserfamilies", None), ("/stats/clicks/platforms", None),
]


@live
@pytest.mark.skipif(not SERVER, reason="нет HASKIMAIL_SERVER_TOKEN")
@pytest.mark.parametrize("path,params", SERVER_GETS)
def test_live_server_reads(checker, path, params):
    check(checker, "GET", path, call("GET", path, "X-Haskimail-Server-Token", SERVER, params))


@live
@pytest.mark.skipif(not SERVER, reason="нет HASKIMAIL_SERVER_TOKEN")
def test_live_details_by_id(checker):
    h, t = "X-Haskimail-Server-Token", SERVER
    streams = check(checker, "GET", "/message-streams", call("GET", "/message-streams", h, t))["MessageStreams"]
    sid = streams[0]["ID"]
    check(checker, "GET", "/message-streams/{streamid}", call("GET", f"/message-streams/{sid}", h, t))
    check(checker, "GET", "/message-streams/{streamid}/suppressions/dump", call("GET", f"/message-streams/{sid}/suppressions/dump", h, t))
    msgs = check(checker, "GET", "/messages", call("GET", "/messages", h, t, {"count": 1}))["Messages"]
    if msgs:
        mid = msgs[0]["MessageID"]
        check(checker, "GET", "/messages/{messageid}/details", call("GET", f"/messages/{mid}/details", h, t))
        check(checker, "GET", "/messages/opens/{messageid}", call("GET", f"/messages/opens/{mid}", h, t))
        check(checker, "GET", "/messages/clicks/{messageid}", call("GET", f"/messages/clicks/{mid}", h, t))
    # несуществующие объекты: статус и тело ошибки должны быть описаны
    check(checker, "GET", "/message-streams/{streamid}", call("GET", "/message-streams/999999999", h, t))
    check(checker, "GET", "/messages/{messageid}/details", call("GET", "/messages/00000000000000000000000000000000/details", h, t))
    check(checker, "GET", "/templates/{templateIdOrAlias}", call("GET", "/templates/no-such-template-xyz", h, t))
    check(checker, "POST", "/templates/validate", call("POST", "/templates/validate", h, t, body={}))
    check(checker, "POST", "/templates/validate", call("POST", "/templates/validate", h, t, body={"Subject": "Заказ {{n}}", "TestRenderModel": {"{{n}}": 1}}))


@live
@pytest.mark.skipif(not ACCOUNT, reason="нет HASKIMAIL_ACCOUNT_TOKEN")
def test_live_account_reads(checker):
    h, t = "X-Haskimail-Account-Token", ACCOUNT
    servers = check(checker, "GET", "/servers", call("GET", "/servers", h, t))["Servers"]
    check(checker, "GET", "/servers/{serverid}", call("GET", f"/servers/{servers[0]['ID']}", h, t))
    check(checker, "GET", "/servers/{serverid}", call("GET", "/servers/1", h, t))
    domains = check(checker, "GET", "/domains", call("GET", "/domains", h, t))["Domains"]
    if domains:
        check(checker, "GET", "/domains/{domainid}", call("GET", f"/domains/{domains[0]['ID']}", h, t))
    check(checker, "GET", "/domains/{domainid}", call("GET", "/domains/1", h, t))
    # методы, где спецификация разрешает и ключ аккаунта
    for path in ("/messages", "/bounces", "/stats", "/templates", "/message-streams", "/webhooks"):
        check(checker, "GET", path, call("GET", path, h, t, {"count": 1} if path in ("/messages", "/bounces", "/templates") else None))


@live
def test_live_send_in_test_mode(checker):
    """Ключ HASKIMAIL_API_TEST: запрос проверяется, письмо не отправляется."""
    h, t = "X-Haskimail-Server-Token", "HASKIMAIL_API_TEST"
    body = {"From": "test@example.com", "To": "test@example.com", "Subject": "contract test", "TextBody": "x"}
    check(checker, "POST", "/email", call("POST", "/email", h, t, body=body))
    r = call("POST", "/email/batch", h, t, body=[body, {**body, "To": "not-an-email"}])
    check(checker, "POST", "/email/batch", r)
