# Haskimail OpenAPI — тесты

`haskimail-api.openapi.json` — спецификация Haskimail API (OpenAPI 3.1).

## Запуск

```bash
pip install pytest jsonschema referencing openapi-spec-validator requests
pytest -q tests
```

Без ключей тесты работают офлайн, тесты против живого API пропускаются (`49 passed, 23 skipped`).

Проверка на живом API — только чтение. Отправка идёт с тестовым ключом `HASKIMAIL_API_TEST`, письма никуда не уходят.

```bash
HASKIMAIL_RUN_LIVE=1 \
HASKIMAIL_SERVER_TOKEN=... \
HASKIMAIL_ACCOUNT_TOKEN=... \
pytest -q tests
```

Чтобы проверить другую версию файла, укажите её путь: `HASKIMAIL_SPEC=/path/to/spec.json pytest -q tests`.

## Что проверяется

| Файл | Проверки |
|---|---|
| `tests/test_spec.py` | Валидность OpenAPI 3.1. Уникальные operationId в camelCase. У каждого метода есть security, теги, ссылка на документацию и ответы 401/403/default. Какой ключ нужен методу. Вебхуки без API-ключа. Все примеры соответствуют своим схемам. Негативные тесты: схемы отклоняют неверные данные. Ответы допускают новые поля. Каждый из 62 инструментов MCP Haskimail совпадает с операцией спецификации. |
| `tests/test_contract.py` | 35 ответов, записанных с живого API 30.10.2026, включая ответы с ошибками 404 и 422. Живые GET-запросы по всем методам чтения, запросы к несуществующим объектам и отправка в тестовом режиме. |

## Линтеры

```bash
npx @redocly/cli@1.25.0 lint haskimail-api.openapi.json --config redocly.yaml
npx @stoplight/spectral-cli@6.11.1 lint haskimail-api.openapi.json -r .spectral.yaml
```

В `redocly.yaml` выключено правило `no-ambiguous-paths`. Пути `/messages/{messageid}/details` и `/messages/opens/{messageid}` — так устроено само API.
