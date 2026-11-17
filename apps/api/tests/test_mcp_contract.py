# 文件用途：严格契约、版本白名单与恶意结果校验，不启动服务。
from types import SimpleNamespace

import pytest
from devflow.code.mcp_client import validate_discovery
from devflow.code.mcp_contract import SERVER_NAME, SERVER_VERSION, tools, validate_result
from devflow.core.errors import DomainError
from jsonschema import Draft202012Validator


def test_only_three_tools_and_schemas_are_valid():
    values = tools()
    assert {item.name for item in values} == {"repo_tree", "repo_read", "repo_search"}
    for tool in values:
        assert tool.input_schema["additionalProperties"] is False
        assert tool.annotations.read_only_hint is True
        Draft202012Validator.check_schema(tool.output_schema)


@pytest.mark.parametrize("change", ["name", "version", "schema", "missing", "extra"])
def test_discovery_rejects_wrong_server_or_schema(change):
    server = SimpleNamespace(
        server_info=SimpleNamespace(name=SERVER_NAME, version=SERVER_VERSION),
        protocol_version="2026-07-28",
    )
    values = tools()
    if change in {"name", "version"}:
        setattr(server.server_info, change, "unexpected")
    elif change == "schema":
        values[0].input_schema = {}
    elif change == "missing":
        values.pop()
    else:
        values.append(values[0].model_copy(update={"name": "execute"}))
    with pytest.raises(DomainError) as error:
        validate_discovery(server, values)
    assert error.value.code == "mcp_contract_mismatch"


@pytest.mark.parametrize(
    "value,is_error",
    [
        ({"ok": True, "data": None, "error": None}, False),
        (
            {
                "ok": False,
                "data": None,
                "error": {"code": "x", "message": "x", "status": 403},
                "extra": "x",
            },
            True,
        ),
        ({"ok": True, "data": {"repo_id": "x"}, "error": None}, False),
    ],
)
def test_bad_result_is_not_success(value, is_error):
    with pytest.raises(DomainError) as error:
        validate_result("repo_read", value, is_error)
    assert error.value.code == "mcp_result_invalid"


def test_business_failure_preserves_code():
    with pytest.raises(DomainError) as error:
        validate_result(
            "repo_read",
            {
                "ok": False,
                "data": None,
                "error": {"status": 403, "code": "code_commit_denied", "message": "越界"},
            },
            True,
        )
    assert error.value.code == "code_commit_denied"
