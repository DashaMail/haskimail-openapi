import json
import os
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

HERE = Path(__file__).parent
SPEC_PATH = Path(os.environ.get("HASKIMAIL_SPEC", HERE.parent / "haskimail-api.openapi.json"))


@pytest.fixture(scope="session")
def spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


class SchemaChecker:
    """Проверяет данные по схеме из спецификации, разрешая $ref на #/components/..."""

    def __init__(self, spec):
        self.spec = spec
        self.registry = Registry().with_resource(
            "urn:spec", Resource.from_contents(spec, default_specification=DRAFT202012)
        )

    def resolve(self, node):
        while isinstance(node, dict) and "$ref" in node:
            target = self.spec
            for part in node["$ref"][2:].split("/"):
                target = target[part]
            node = target
        return node

    def errors(self, schema, instance):
        rewritten = json.loads(json.dumps(schema).replace('"#/components', '"urn:spec#/components'))
        v = Draft202012Validator(rewritten, registry=self.registry, format_checker=Draft202012Validator.FORMAT_CHECKER)
        return [f"{list(e.absolute_path)}: {e.message[:200]}" for e in v.iter_errors(instance)]

    def response_schema(self, method, path, status):
        op = self.spec["paths"][path][method.lower()]
        resp = op["responses"].get(str(status))
        if resp is None:
            return None
        return self.resolve(resp)["content"]["application/json"]["schema"]

    def operations(self):
        for path, item in self.spec["paths"].items():
            for method, op in item.items():
                yield method, path, op


@pytest.fixture(scope="session")
def checker(spec):
    return SchemaChecker(spec)
