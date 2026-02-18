import asyncio
import os
import sys
from pathlib import Path

import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException
from starlette.requests import Request


REPO_ROOT = Path(__file__).resolve().parents[1]
LAMBDA_DIR = REPO_ROOT / "lambda"
if str(LAMBDA_DIR) not in sys.path:
    sys.path.insert(0, str(LAMBDA_DIR))

# Avoid any boto metadata lookups when boto3 resources are initialized.
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")

import recallist  # noqa: E402


def _build_request(authorizer):
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "aws.event": {"requestContext": {"authorizer": authorizer}},
    }
    return Request(scope)


def test_get_current_user_from_request_authorizer_context():
    request = _build_request({"user_id": "user-123"})
    assert recallist.get_current_user(request) == {"user_id": "user-123"}


def test_get_current_user_from_lambda_authorizer_context():
    request = _build_request({"lambda": {"user_id": "user-456"}})
    assert recallist.get_current_user(request) == {"user_id": "user-456"}


def test_get_current_user_from_jwt_claims():
    request = _build_request({"jwt": {"claims": {"sub": "user-789"}}})
    assert recallist.get_current_user(request) == {"user_id": "user-789"}


def test_get_current_user_raises_when_missing_authorization():
    request = _build_request({})
    with pytest.raises(HTTPException) as exc:
        recallist.get_current_user(request)
    assert exc.value.status_code == 401


def test_to_item_model_prefers_display_item():
    model = recallist._to_item_model(
        {
            "item": "normalized text",
            "display_item": "Display Text",
            "status": "NEW",
            "createdDate": "2024-01-01T00:00:00+00:00",
        }
    )
    assert model.item == "Display Text"


def test_svc_create_item_raises_400_for_blank_text():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(recallist.svc_create_item("user-1", "   "))
    assert exc.value.status_code == 400


def test_svc_create_item_maps_conditional_check_failure_to_409(monkeypatch):
    error = ClientError(
        error_response={"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}},
        operation_name="PutItem",
    )

    def _raise(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(recallist, "put_item_if_absent", _raise)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(recallist.svc_create_item("user-1", "Read book"))

    assert exc.value.status_code == 409


def test_svc_delete_item_raises_404_when_not_deleted(monkeypatch):
    monkeypatch.setattr(recallist, "delete_item", lambda *_args, **_kwargs: False)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(recallist.svc_delete_item("user-1", "item"))
    assert exc.value.status_code == 404
