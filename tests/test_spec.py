"""Статические тесты спецификации: валидность, примеры, согласованность."""
import json
import re
from pathlib import Path

import pytest
from openapi_spec_validator import validate

HERE = Path(__file__).parent


def test_spec_is_valid_openapi_31(spec):
    assert spec["openapi"].startswith("3.1")
    validate(spec)


def test_operation_ids_unique_and_camel_case(checker):
    ids = [op["operationId"] for _, _, op in checker.operations()]
    assert len(ids) == len(set(ids)) == 62
    for i in ids:
        assert re.fullmatch(r"[a-z][A-Za-z0-9]+", i), i


def test_every_operation_has_security_tag_docs_and_errors(checker, spec):
    tag_names = {t["name"] for t in spec["tags"]}
    for method, path, op in checker.operations():
        where = f"{method.upper()} {path}"
        assert op.get("security"), where
        assert op["tags"] and set(op["tags"]) <= tag_names, where
        assert op.get("externalDocs", {}).get("url", "").startswith("https://haskimail.ru/developer/"), where
        for code in ("200", "401", "403", "default"):
            assert code in op["responses"], f"{where}: нет ответа {code}"
        if method in ("post", "put", "patch") and "requestBody" in op:
            assert op["requestBody"]["required"] is True, where


def test_account_only_and_server_only_methods(checker):
    for method, path, op in checker.operations():
        keys = {k for req in op["security"] for k in req}
        if path.startswith(("/servers", "/domains")) or path == "/templates/push":
            assert keys == {"accountToken"}, path
        if path.startswith(("/email", "/messages/inbound", "/triggers/inboundrules")) or "/suppressions" in path:
            assert keys == {"serverToken"}, path


def test_webhooks_have_no_api_key_security(spec):
    for name, item in spec["webhooks"].items():
        assert item["post"]["security"] == [], name


def _examples(spec):
    for path, item in spec["paths"].items():
        for method, op in item.items():
            body = op.get("requestBody", {}).get("content", {}).get("application/json")
            if body and "example" in body:
                yield f"{method.upper()} {path} request", body["schema"], body["example"]
            for code, resp in op["responses"].items():
                c = resp.get("content", {}).get("application/json")
                if c and "example" in c:
                    yield f"{method.upper()} {path} {code}", c["schema"], c["example"]
            for prm in op.get("parameters", []):
                if "$ref" in prm:
                    prm = spec["components"]["parameters"][prm["$ref"].split("/")[-1]]
                if "example" in prm:
                    yield f"{method.upper()} {path} ?{prm['name']}", prm["schema"], prm["example"]
    for name, s in spec["components"]["schemas"].items():
        for ex in s.get("examples", []):
            if isinstance(ex, dict):
                yield f"schema {name}", {"$ref": f"#/components/schemas/{name}"}, ex
    for name, item in spec["webhooks"].items():
        c = item["post"]["requestBody"]["content"]["application/json"]
        if "example" in c:
            yield f"webhook {name}", c["schema"], c["example"]


def test_all_examples_match_their_schemas(spec, checker):
    failures, total = [], 0
    for where, schema, example in _examples(spec):
        total += 1
        failures += [f"{where} {e}" for e in checker.errors(schema, example)]
    assert total > 100
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize(
    "schema,instance",
    [
        ("Email", {"From": "a@b.ru", "To": "c@d.ru", "TrackOpens": "yes"}),
        ("Email", {"From": "a@b.ru", "To": "c@d.ru", "Unknown": 1}),
        ("Email", {"To": "c@d.ru"}),
        ("CreateServerRequest", {"Name": "x", "Color": "blue", "InboundSpamThreshold": 7}),
        ("CreateMessageStreamRequest", {"Name": "x", "MessageStreamType": "Inbound"}),
        ("BounceWebhookEvent", {"event": "clicked", "recipient": "a", "message_id": "1", "server_id": 1, "stream_id": "1",
                                "event_time": "2026-01-01 00:00:00", "event_time_utc": "2026-01-01 00:00:00", "secret": "s",
                                "bounce_category": "hrd", "code": "550", "error": "x"}),
    ],
)
def test_schemas_reject_invalid_data(checker, schema, instance):
    """Негативные тесты: схемы действительно ловят ошибки."""
    assert checker.errors({"$ref": f"#/components/schemas/{schema}"}, instance)


def test_response_schemas_tolerate_new_fields(checker):
    """Ответы не должны ломаться, если API добавит поле."""
    for method, path, op in checker.operations():
        schema = checker.response_schema(method, path, 200)
        resolved = checker.resolve(schema)
        if resolved.get("type") == "object" and "properties" in resolved:
            sample = {"__new_field__": 1}
            errs = [e for e in checker.errors(schema, sample) if "__new_field__" in e]
            assert not errs, f"{method.upper()} {path}: {errs}"


def test_parity_with_mcp_tools(spec, checker):
    """Каждый инструмент MCP Haskimail = операция спецификации с теми же параметрами."""
    tools = json.loads((HERE / "fixtures_mcp_tools.json").read_text(encoding="utf-8"))
    assert len(tools) == 62

    def props(s):
        s = checker.resolve(s)
        out = set(s.get("properties", {}))
        for k in ("allOf", "anyOf", "oneOf"):
            for sub in s.get(k, []):
                out |= props(sub)
        if s.get("type") == "array":
            out |= props(s["items"])
        return out

    seen = set()
    for t in tools:
        op = spec["paths"].get(t["path"], {}).get(t["method"].lower())
        assert op, f"нет операции {t['method']} {t['path']}"
        seen.add((t["method"].lower(), t["path"]))
        names = {checker.resolve(p)["name"] for p in op.get("parameters", [])}
        if "requestBody" in op:
            names |= props(op["requestBody"]["content"]["application/json"]["schema"])
        missing = set(t["params"]) - names
        assert not missing, f"{t['method']} {t['path']}: нет параметров {missing}"
    assert seen == {(m, p) for m, p, _ in checker.operations()}
