"""Build reviewable Cognito replacement requests. No writes happen in these helpers."""
from copy import deepcopy


def _request_fields(client, operation, described):
    supported = client.meta.service_model.operation_model(operation).input_shape.members
    return {key: deepcopy(value) for key, value in described.items() if key in supported}


def client_update_request(client, pool_id, client_id, **changes):
    described = client.describe_user_pool_client(
        UserPoolId=pool_id, ClientId=client_id
    )["UserPoolClient"]
    request = _request_fields(client, "UpdateUserPoolClient", described)
    request.update(UserPoolId=pool_id, ClientId=client_id)
    request.update(deepcopy(changes))
    return request


def pool_trigger_update_request(client, pool_id, **triggers):
    described = client.describe_user_pool(UserPoolId=pool_id)["UserPool"]
    request = _request_fields(client, "UpdateUserPool", described)
    request.update(UserPoolId=pool_id, PoolName=described["Name"])
    request["LambdaConfig"] = {**request.get("LambdaConfig", {}), **triggers}
    return request
