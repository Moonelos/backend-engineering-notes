# Cognito Tokens — Deep Dive

> **Who this is for**: API engineers deciding which Cognito token kind an endpoint should accept and
> how to validate it.

> **Key insight**: Token shape does not establish intended use; the verifier must bind token type and
> audience to the endpoint.

> JWT structure, JWKS, and generic validation are covered in [auth/jwt.md](../jwt.md). This file covers what's Cognito-specific: the three token types, their claims, Cognito validation code, and revocation.

---

After a successful login, Cognito returns three tokens. Two (IdToken and AccessToken) are JWTs. The third (RefreshToken) is an encrypted opaque blob only Cognito can read.

---

## The Three Tokens

### IdToken — "Who is this user?"

Contains user identity information for the OIDC client. It is not an API authorization credential.

```json
{
  "sub": "a1b2c3d4-1234-5678-abcd-ef0123456789",
  "email": "jane@example.com",
  "email_verified": true,
  "name": "Jane Doe",
  "cognito:username": "jane@example.com",
  "cognito:groups": ["admins", "premium"],
  "custom:department": "engineering",
  "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_POOLID",
  "aud": "your-client-id",
  "token_use": "id",
  "auth_time": 1700000000,
  "iat": 1700000000,
  "exp": 1700003600
}
```

Key claims:
- `sub` — the user's permanent UUID. **Always use this as your user's primary key.** Email can change, `sub` never does.
- `email`, `name`, etc. — standard user attributes
- `cognito:groups` — which groups the user is in
- `custom:*` — your custom attributes
- `aud` — must match your `client_id`
- `token_use` — must be `"id"`
- `exp` — expiry timestamp (Unix)

### AccessToken — "What can this user do?"

Used to authorize API calls. Less about identity, more about permissions and scopes.

```json
{
  "sub": "a1b2c3d4-1234-5678-abcd-ef0123456789",
  "cognito:groups": ["admins", "premium"],
  "scope": "openid email profile",
  "client_id": "your-client-id",
  "username": "jane@example.com",
  "iss": "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_POOLID",
  "token_use": "access",
  "auth_time": 1700000000,
  "iat": 1700000000,
  "exp": 1700003600,
  "jti": "unique-token-id"
}
```

Key differences from IdToken:
- Has `scope` instead of user attributes
- `client_id` identifies the app client. An `aud` claim appears only when an OAuth **user** authorization request explicitly uses `resource=<URL>`. Registering `myapi/read` does not itself add an audience. M2M client-credentials grants and SDK user authentication do not support resource binding.
- `token_use` is `"access"`
- It is still a readable bearer credential and potentially sensitive: `username`, group affiliation,
  and customized claims can be personally identifiable information (PII). Classify and redact it as
  sensitive even when email/name are absent.

**Which token should your API validate?**
- Use **AccessToken** to authorize API calls — that's its purpose
- Obtain profile data through a trusted lookup or an explicitly isolated identity endpoint. Do not
  let an ID token cross an API authorization boundary merely because it contains convenient fields.

### RefreshToken — "Get me new tokens"

An encrypted, opaque string (not a JWT). Only Cognito can read it. Your app stores it and uses it to silently get new Access/Id tokens when they expire.

```python
response = cognito_client.initiate_auth(
    ClientId=client_id,
    AuthFlow='REFRESH_TOKEN_AUTH',
    AuthParameters={'REFRESH_TOKEN': stored_refresh_token},
)

new_tokens = response['AuthenticationResult']
# new_tokens['AccessToken'], new_tokens['IdToken']
# By default a new RefreshToken is NOT issued — the same one keeps working until it
# expires or is revoked. If you opt into refresh token rotation (see below), a fresh
# RefreshToken comes back on each refresh and the old one is invalidated.
```

---

## Default Token Lifetimes

| Token | Default | Min | Max | Configurable per App Client |
|-------|---------|-----|-----|----------------------------|
| AccessToken | 1 hour | 5 min | 24 hours | Yes |
| IdToken | 1 hour | 5 min | 24 hours | Yes |
| RefreshToken | 30 days | 1 hour | 10 years | Yes |

Set lifetimes on creation, or preserve the existing configuration on updates. Cognito's update
operation resets omitted fields to defaults; a three-field patch can remove callback URLs or flows.
The helper below is a real [local module](examples/config_updates.py), copied beside your script:

```python
from config_updates import client_update_request

request = client_update_request(
    cognito_client, pool_id, client_id,
    AccessTokenValidity=15, IdTokenValidity=15, RefreshTokenValidity=7,
    TokenValidityUnits={"AccessToken": "minutes", "IdToken": "minutes", "RefreshToken": "days"},
)
# Review the redacted before/after configuration, then apply under one admin writer.
cognito_client.update_user_pool_client(**request)
```

The helper reads `DescribeUserPoolClient` and copies only fields accepted by the installed SDK's
update schema. It excludes returned secrets and timestamps. Nested changes replace the specified
nested object, so supply its complete intended value. Pin a current SDK, retain configuration in
infrastructure as code, serialize administrators, and describe again after applying: this API has
no compare-and-swap protection against concurrent updates. See [AWS update semantics](https://docs.aws.amazon.com/cognito-user-identity-pools/latest/APIReference/API_UpdateUserPoolClient.html).

---

## Token Validation (In Your API)

**Never trust a JWT without validating its signature.** Anyone can create a JWT — the signature is what proves Cognito issued it.

### One policy for one issuance profile

Cognito signs with RSA keys published at the **configured issuer's** JWKS URL. The classic issuer is
`https://cognito-idp.<region>.amazonaws.com/<pool_id>`. Updated multi-Region issuers use a different
prefix; never synthesize the accepted issuer from an unverified token. Pin the deployed value and
fetch `<issuer>/.well-known/jwks.json` with bounded timeouts and caching.

| Issuance profile | Required API checks after RS256 signature, issuer, timestamps |
|---|---|
| M2M custom scope, no resource binding | `token_use=access`, exact allowed `client_id`, required custom scope; this lesson rejects unexpected `aud` |
| OAuth user code flow with `resource=https://api.example.com` | Same access checks plus exact `aud=https://api.example.com` |
| SDK user login | Access token normally has `aws.cognito.signin.user.admin`, not `myapi/read`; it does not satisfy the custom-scope API policy |
| ID token | Separate OIDC identity handler validates client audience, type, and transaction nonce; never accepted by the API policy |

`client_id` is a Cognito-specific app binding, not a generic replacement for OAuth resource
audience. Custom scopes must remain distinct across resources when using the unbound M2M profile.
[The Cognito resource-binding contract](https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-user-pools-define-resource-servers.html#cognito-user-pools-resource-servers-resource-binding)
explains why `aud="myapi"` would reject the very M2M token this path issues.

### Python validation

The canonical implementation is [access_policy.py](examples/access_policy.py); it is used by the
[practical guide](oauth-jwt-guide.md). It requires the claim set, pins `RS256`, verifies issuer and
freshness, rejects ID tokens/wrong clients, and distinguishes missing scope (403) from invalid
authentication (401). Its `resource_audience=None` is an explicit **unbound Cognito M2M profile**, not
a general instruction to disable audience validation.

```python
from access_policy import AccessPolicy, create_app, jwks_key_resolver

ISSUER = "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_EXAMPLE"
policy = AccessPolicy(
    issuer=ISSUER,
    client_id="configured-service-client-id",
    required_scopes=frozenset({"myapi/read"}),
)
app = create_app(policy, jwks_key_resolver(ISSUER))
```

For the bound user branch, configure its separate user client ID and
`resource_audience="https://api.example.com"`. Do not accept both token types by catching an
audience failure and retrying without validation. [PyJWT](https://pyjwt.readthedocs.io/en/stable/api.html)
validates required claims only when `options["require"]` names them; checking expiry when present
is insufficient if `exp` can be omitted.

Run the negative-fixture tests using the command in the practical guide. They generate real RSA
signatures locally and exercise the HTTP dependency; they do not contact AWS or test live JWKS
rotation. Production should coalesce/cache unknown-key refreshes and limit request rate, record
rejection categories without tokens, and distinguish key-service outage (503) from invalid
credentials. Scope success is only a coarse grant: the business handler still checks tenant and
object permissions.

---

## API Gateway Integration (Skip Manual Validation)

If your API runs behind API Gateway, you can configure a **Cognito User Pool Authorizer** and API Gateway validates the token for you — no code needed.

```python
apigw = boto3.client('apigateway')

# Create authorizer
response = apigw.create_authorizer(
    restApiId='your-api-id',
    name='CognitoAuthorizer',
    type='COGNITO_USER_POOLS',
    providerARNs=[f'arn:aws:cognito-idp:{REGION}:{ACCOUNT_ID}:userpool/{POOL_ID}'],
    identitySource='method.request.header.Authorization',
)

# Bind an access-token scope to the protected method. Without authorizationScopes,
# API Gateway can treat the token as identity authentication rather than scope authorization.
apigw.put_method(
    restApiId='your-api-id',
    resourceId='your-resource-id',
    httpMethod='GET',
    authorizationType='COGNITO_USER_POOLS',
    authorizerId=response['id'],
    authorizationScopes=['myapi/read'],
)

# API Gateway will:
# 1. Extract the token from the Authorization header
# 2. Validate it against the User Pool
# 3. Pass claims to your Lambda as event['requestContext']['authorizer']['claims']
# 4. Return 401 automatically if invalid
```

Lambda receives:
```python
def handler(event, context):
    claims = event['requestContext']['authorizer']['claims']
    user_sub = claims['sub']
    scopes   = set(claims.get('scope', '').split())
    assert 'myapi/read' in scopes
    groups   = claims.get('cognito:groups', '').split(',')
```

---

## Token Revocation

Revocation at Cognito and acceptance by an offline API verifier are different state machines.
`RevokeToken` revokes one refresh-token family and its derived tokens at Cognito. It does **not**
log out every independent session. `GlobalSignOut` (or the administrator equivalent) covers the
user's sessions. A resource server that only verifies a JWT signature cannot discover either event.
[AWS revocation documentation](https://docs.aws.amazon.com/cognito/latest/developerguide/token-revocation.html).

```mermaid
sequenceDiagram
    participant App
    participant Cognito
    participant API as Offline JWT API
    App->>Cognito: RevokeToken for session A refresh token
    Cognito->>Cognito: Revoke A family; session B remains separate
    App->>Cognito: Refresh session A
    Cognito-->>App: Reject
    App->>API: Previously issued A access token before exp
    API-->>App: Signature still verifies unless local revocation policy rejects
```

The last arrow is the operational gap. Choose a bounded access-token lifetime or make the API check
a revocation/session-version store on each relevant request. Define the store's outage behavior and
retention through token expiry; deleting a browser cookie alone does not revoke a stolen bearer.

```python
cognito_client.revoke_token(Token=refresh_token, ClientId=client_id)
# Confidential clients also supply ClientSecret=client_secret.
cognito_client.admin_user_global_sign_out(UserPoolId=pool_id, Username=username)
```

Enable revocation without resetting other client settings:

```python
request = client_update_request(cognito_client, pool_id, client_id, EnableTokenRevocation=True)
cognito_client.update_user_pool_client(**request)
```

### Refresh Token Rotation (Opt-In, since April 2025)

By default Cognito reuses the same refresh token until it expires. You can opt into
**rotation** so each refresh returns a brand-new refresh token and invalidates the old
one — a defense against refresh-token replay that lets you safely use longer refresh TTLs.

```python
request = client_update_request(cognito_client, pool_id, client_id)
request["ExplicitAuthFlows"] = [
    flow for flow in request.get("ExplicitAuthFlows", []) if flow != "ALLOW_REFRESH_TOKEN_AUTH"
]
request["RefreshTokenRotation"] = {"Feature": "ENABLED", "RetryGracePeriodSeconds": 10}
cognito_client.update_user_pool_client(**request)

result = cognito_client.get_tokens_from_refresh_token(
    ClientId=client_id, RefreshToken=stored_refresh_token,
    # ClientSecret=client_secret,  # confidential client only
)["AuthenticationResult"]
# Atomically replace stored_refresh_token with result["RefreshToken"] and the new access token.
```

Remove `ALLOW_REFRESH_TOKEN_AUTH` in the same update: it is incompatible with rotation. For OAuth
clients, the token endpoint also supports refresh. Serialize refresh attempts per session; two tabs
must not overwrite a newer replacement token with an older response. A lost response can be retried
within the configured grace interval, but after it expires require reauthentication rather than
looping. [Cognito refresh rotation](https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-using-the-refresh-token.html).

---

## Quick Reference

```
On login:
  IdToken     → validate as an OIDC identity response before using profile attributes
  AccessToken → send in Authorization header to your API
  RefreshToken → store securely, use to get new tokens when AccessToken expires

On every API request:
  Authorization: Bearer <AccessToken>

When AccessToken expires (after 1 hour by default):
  Nonrotating SDK client: REFRESH_TOKEN_AUTH
  Rotating client: GetTokensFromRefreshToken or OAuth refresh grant; persist replacement

When RefreshToken expires (after 30 days by default):
  User must log in again

The only token your API should validate:
  AccessToken; ID tokens never cross this API authorization boundary
```

---

## Related Docs

- [cognito.md](./cognito.md) — Mental model and overview
- [user-pool.md](./user-pool.md) — User pool, app clients, auth flows, boto3


## Retention and transfer

**Recap:** token type, app client, scope, and optional resource audience form one issuance/validation
contract. Revocation changes issuer state; offline verification needs its own freshness policy.

**Check yourself:** will adding the `myapi/read` resource-server scope make a client-credentials
token pass `aud="myapi"` validation?
<details><summary>Answer</summary>No. Scope registration does not imply resource binding. Use the
explicit unbound M2M contract, or a supported user OAuth flow with a URL resource audience.</details>

**Try it:** an administrator revokes session A, but a five-minute-old token still reaches your API.
Decide which observation distinguishes a broken signature validator from missing revocation state.
<details><summary>Answer</summary>Check that the token remains unexpired and has the configured
issuer/profile. Signature verification can correctly succeed. Confirm A's refresh fails at Cognito,
then inspect the API's revocation/version check; session B is not evidence that A revocation failed.</details>
