"""AWS request shape and preservation checks; botocore Stubber prevents network."""
import boto3
from botocore.stub import Stubber
from pathlib import Path
import re

from config_updates import client_update_request, pool_trigger_update_request


def cognito():
    return boto3.client("cognito-idp", region_name="us-east-1",
                        aws_access_key_id="fixture", aws_secret_access_key="fixture")


def test_rotation_preserves_client_profile_and_removes_legacy_flow():
    client = cognito()
    existing = {"UserPoolId": "us-east-1_FIXTURE", "ClientId": "fixtureclient",
                "ClientName": "web", "CallbackURLs": ["https://app.example.com/callback"],
                "AllowedOAuthFlows": ["code"], "AllowedOAuthScopes": ["openid", "myapi/read"],
                "AllowedOAuthFlowsUserPoolClient": True, "AccessTokenValidity": 15,
                "ExplicitAuthFlows": ["ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
                "ClientSecret": "fixturesecretvalueatleast24chars"}
    expected = {key: value for key, value in existing.items() if key != "ClientSecret"}
    expected.update(ExplicitAuthFlows=["ALLOW_USER_SRP_AUTH"],
                    RefreshTokenRotation={"Feature": "ENABLED", "RetryGracePeriodSeconds": 10})
    with Stubber(client) as stub:
        stub.add_response("describe_user_pool_client", {"UserPoolClient": existing},
                          {"UserPoolId": "us-east-1_FIXTURE", "ClientId": "fixtureclient"})
        request = client_update_request(client, "us-east-1_FIXTURE", "fixtureclient")
        request["ExplicitAuthFlows"] = [f for f in request["ExplicitAuthFlows"] if f != "ALLOW_REFRESH_TOKEN_AUTH"]
        request["RefreshTokenRotation"] = {"Feature": "ENABLED", "RetryGracePeriodSeconds": 10}
        stub.add_response("update_user_pool_client", {}, expected)
        client.update_user_pool_client(**request)
        stub.assert_no_pending_responses()


def test_exact_pool_creation_request_shapes(monkeypatch):
    client = cognito()
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    note = Path(__file__).parents[1] / "user-pool.md"
    fence = re.findall(r"```python\n(.*?)\n```", note.read_text(), re.S)[0]
    pool = {"Id": "us-east-1_FIXTURE", "Name": "myapp-users", "Status": "Enabled"}
    with Stubber(client) as stub:
        stub.add_response("create_user_pool", {"UserPool": pool})
        stub.add_response("set_user_pool_mfa_config", {}, {
            "UserPoolId": pool["Id"], "MfaConfiguration": "OPTIONAL",
            "SoftwareTokenMfaConfiguration": {"Enabled": True},
        })
        stub.add_response("describe_user_pool", {"UserPool": pool}, {"UserPoolId": pool["Id"]})
        exec(compile(fence, str(note), "exec"), {})
        stub.assert_no_pending_responses()


def test_post_confirmation_skips_password_reset_and_initializes_conditionally():
    note = Path(__file__).parents[1] / "user-pool.md"
    fence = next(block for block in re.findall(r"```python\n(.*?)\n```", note.read_text(), re.S)
                 if "def initialize_profile(" in block)
    namespace = {}
    exec(compile(fence, str(note), "exec"), namespace)
    calls = []

    class Table:
        def update_item(self, **request):
            calls.append(request)

    event = {"triggerSource": "PostConfirmation_ConfirmForgotPassword",
             "request": {"userAttributes": {"sub": "u1", "email": "fixture@example.test"}}}
    namespace["initialize_profile"](event, Table())
    assert calls == []
    event["triggerSource"] = "PostConfirmation_ConfirmSignUp"
    namespace["initialize_profile"](event, Table())
    assert calls[0]["Key"] == {"userId": "u1"}
    assert "#tier = if_not_exists(#tier, :free)" in calls[0]["UpdateExpression"]
    assert "#created = if_not_exists(#created, :now)" in calls[0]["UpdateExpression"]


def test_pool_trigger_preserves_password_policy_and_existing_trigger():
    client = cognito()
    pool = {"Id": "us-east-1_FIXTURE", "Name": "users", "Status": "Enabled",
            "Policies": {"PasswordPolicy": {"MinimumLength": 12}},
            "LambdaConfig": {"PreSignUp": "arn:aws:lambda:us-east-1:123456789012:function:pre"}}
    post = "arn:aws:lambda:us-east-1:123456789012:function:post"
    expected = {"UserPoolId": pool["Id"], "PoolName": pool["Name"], "Policies": pool["Policies"],
                "LambdaConfig": {**pool["LambdaConfig"], "PostConfirmation": post}}
    with Stubber(client) as stub:
        stub.add_response("describe_user_pool", {"UserPool": pool}, {"UserPoolId": pool["Id"]})
        request = pool_trigger_update_request(client, pool["Id"], PostConfirmation=post)
        stub.add_response("update_user_pool", {}, expected)
        client.update_user_pool(**request)
        stub.assert_no_pending_responses()
