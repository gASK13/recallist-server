import importlib.util
import os
from pathlib import Path


os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")


def _load_authorizer_module():
    repo_root = Path(__file__).resolve().parents[1]
    module_path = repo_root / "lambda_authorizer" / "main.py"
    spec = importlib.util.spec_from_file_location("lambda_authorizer_main", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_lookup_user_id_by_api_key_returns_first_match(monkeypatch):
    module = _load_authorizer_module()

    class _Table:
        def query(self, **_kwargs):
            return {"Items": [{"user_id": "u-1"}, {"user_id": "u-2"}]}

    monkeypatch.setattr(module, "api_keys_table", _Table())
    assert module._lookup_user_id_by_api_key("key") == "u-1"


def test_handler_denies_without_api_key():
    module = _load_authorizer_module()
    result = module.handler({"headers": {}}, None)
    assert result == {"isAuthorized": False}


def test_handler_allows_with_valid_api_key(monkeypatch):
    module = _load_authorizer_module()
    monkeypatch.setattr(module, "_lookup_user_id_by_api_key", lambda _api_key: "user-42")

    result = module.handler({"headers": {"X-API-KEY": "abc"}}, None)

    assert result["isAuthorized"] is True
    assert result["context"]["user_id"] == "user-42"
    assert result["context"]["auth_type"] == "x-api-key"


def test_handler_denies_when_lookup_fails(monkeypatch):
    module = _load_authorizer_module()
    monkeypatch.setattr(module, "_lookup_user_id_by_api_key", lambda _api_key: None)

    result = module.handler({"headers": {"x-api-key": "abc"}}, None)
    assert result == {"isAuthorized": False}
