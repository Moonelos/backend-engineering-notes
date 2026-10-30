# HTTP Requests & FastAPI Parameter Mapping

<!-- length-justification: This is the canonical FastAPI request-mapping reference; path, query, header, cookie, body, form, and file inputs remain together so precedence and OpenAPI behavior can be compared at one endpoint boundary. -->

> **Who this is for**: Python engineers who know basic HTTP and want to predict exactly where FastAPI obtains each endpoint argument.

This guide explains **how HTTP requests work** and **how FastAPI maps request data into function arguments**.

> **Key insight**: FastAPI's function signature is a request contract: the parameter declaration determines both runtime extraction and the generated OpenAPI description.

For protocol-neutral HTTP semantics, resource design, caching, compatibility, and operations, start with the **[RESTful API Deep Dive](../../apis/restful/README.md)**. This chapter focuses on FastAPI's parameter mapping.

---

## Trace one request into one signature

Start with the mapping before the method and status-code reference:

```http
POST /users/42/items?notify=true HTTP/1.1
X-Request-ID: req-7
Content-Type: application/json

{"name":"keyboard"}
```

Save this complete example as `mapping.py` in the environment from the
[quick start](README.md#quick-start-one-route-and-one-owned-http-client):

```python
from typing import Annotated

from fastapi import FastAPI, Header
from fastapi.testclient import TestClient
from pydantic import BaseModel

app = FastAPI()

class ItemIn(BaseModel):
    name: str

@app.post("/users/{user_id}/items")
def create_item(
    user_id: int,
    item: ItemIn,
    x_request_id: Annotated[str, Header()],
    notify: bool = False,
):
    return {"user_id": user_id, "name": item.name, "notify": notify,
            "request_id": x_request_id}

if __name__ == "__main__":
    with TestClient(app) as client:
        response = client.post("/users/42/items?notify=true",
                               headers={"X-Request-ID": "req-7"},
                               json={"name": "keyboard"})
        assert response.status_code == 200
        assert response.json() == {"user_id": 42, "name": "keyboard",
                                   "notify": True, "request_id": "req-7"}
        assert client.post("/users/42/items", json={"name": "keyboard"}).status_code == 422
        print(response.status_code, response.json())
```

FastAPI maps `42` from the path to `user_id`, `true` from the query string to `notify`, the JSON
object to `item`, and the hyphenated header to `x_request_id`. The response is
`{"user_id":42,"name":"keyboard","notify":true,"request_id":"req-7"}`. A missing required header
or non-integer path value produces `422` before the function runs.

---

## Part 0: Endpoint Structure & Conventions

### HTTP Method Semantics

| Method   | Purpose                                  | Request body?                      | Idempotent? |
|----------|------------------------------------------|------------------------------------|-------------|
| `GET`    | Retrieve a resource representation        | Avoid; no generally defined meaning | Yes         |
| `POST`   | Submit data for processing; may create, search, calculate, or trigger an action | Yes | Not by default |
| `PUT`    | Replace or create the target resource     | Yes                                | Yes         |
| `PATCH`  | Apply a partial modification              | Yes                                | Not guaranteed |
| `DELETE` | Remove the target resource association    | Avoid; no generally defined meaning | Yes         |

Idempotent means that repeating the same request has the same intended server-side effect as sending it once. The response can still differ; for example, the first `DELETE` might return `204`, while a repeated one might return `404`.

`PATCH` is commonly treated as non-idempotent because a patch document can express instructions like "append this item." It can be designed to be idempotent, especially when it sets fields to explicit values and uses conditional requests such as `If-Match`.

> **POST mental model:** `POST` does not mean "create only." It means "send this payload to the server and let the target resource process it according to its own semantics." A `POST` can absolutely return data. Common legitimate uses beyond creation:
>
> ```
> POST /search          → complex query too large or sensitive for a URL
> POST /reports/run     → trigger a calculation and return results
> POST /recommendations → send context, get back personalized data
> ```
>
> Use `POST` for reads when the query body is complex, URL length would be excessive, or you want to avoid exposing parameters in logs and browser history.

### URL Naming Conventions

```
/users                  → collection of users
/users/{user_id}        → specific user
/users/{user_id}/orders → orders belonging to a user
```

- For resource-oriented APIs, use **plural nouns** for collections (`/users`, `/orders`)
- Use **kebab-case** for multi-word segments (`/payment-methods`)
- Prefer **no verbs** in the path — the HTTP method already expresses the action
- If an operation truly is not resource-shaped, make that exception obvious and document it

### Status Code Conventions

| Code | Meaning                   | Typical use                              |
|------|---------------------------|------------------------------------------|
| 200  | OK                        | Successful GET, PUT, PATCH               |
| 201  | Created                   | Successful POST that created a resource  |
| 202  | Accepted                  | Accepted for async/background processing |
| 204  | No Content                | Successful DELETE/update with no body    |
| 400  | Bad Request               | Malformed syntax or generic client error |
| 401  | Unauthorized              | Missing or invalid credentials           |
| 403  | Forbidden                 | Authenticated but not permitted          |
| 404  | Not Found                 | Resource does not exist                  |
| 422  | Unprocessable Entity      | FastAPI's default for validation errors  |
| 500  | Internal Server Error     | Unhandled server-side failure            |

`401 Unauthorized` is the historical status phrase, but in application terms it usually means "not authenticated." Use `403 Forbidden` when the user is authenticated but lacks permission.

### FastAPI Decorator Syntax

```python
from fastapi import FastAPI, status
from pydantic import BaseModel

app = FastAPI()

class ItemOut(BaseModel):
    id: int
    name: str

@app.post(
    "/users/{user_id}/items",
    response_model=ItemOut,
    status_code=status.HTTP_201_CREATED,
    summary="Create an item for a user",
    tags=["items"],
)
def create_item(user_id: int):  # Other parameters omitted from this signature excerpt
    ...
```

Key decorator fields:

- `response_model` — Pydantic model that filters, documents, and validates the response
- `status_code` — default HTTP status code returned on success
- `summary` / `description` — show up in the auto-generated OpenAPI docs
- `tags` — group endpoints in the docs UI

---

## Part 1: The HTTP Request

Every HTTP request is made up of four distinct parts:

| Part          | Where it lives                    | Purpose                                      |
|---------------|-----------------------------------|----------------------------------------------|
| Method + Path | First line of the request         | What action to take and on which resource    |
| Query string  | After `?` in the URL              | Modifiers — filters, pagination, sort order  |
| Headers       | Lines before the blank line       | Metadata — auth tokens, content type, caching |
| Body          | After the blank line              | Payload — structured data sent to the server |

### Annotated Example

```
POST /users/42/orders?notify=true HTTP/1.1     ← method + path + query string
Host: api.example.com                          ← header: target host
Authorization: Bearer eyJhbGci...             ← header: auth token
Content-Type: application/json                 ← header: body format
Accept: application/json                       ← header: expected response format
Cookie: session_id=abc123; theme=dark          ← header: cookies sent back to the server
                                               ← blank line separates headers from body
{                                              ↓ body: structured JSON payload
  "item_id": 7,
  "quantity": 3
}
```

Cookies travel as an ordinary header (`Cookie:`), but FastAPI gives them their own parameter source — see [Part 5](#5-cookies) — because they're set and scoped differently from other headers (via `Set-Cookie` on a prior response, with domain/path/expiry rules).

Each part maps to a different FastAPI parameter source, covered in the sections below.

---

## 1. Path Parameters

### What They Are

Parts of the URL that **identify a specific resource**.

```
/users/42/products/7
```

- `42` → `user_id`
- `7` → `product_id`

### Characteristics

- **Required** — must be present
- Change *which* resource you're requesting
- No default values

### FastAPI Syntax

```python
@app.get("/users/{user_id}/products/{product_id}")
def endpoint(user_id: int, product_id: int):
    ...
```

### Mapping

```
/users/42/products/7
→ user_id=42, product_id=7
```

---

## 2. Query Parameters

### What They Are

Extra information that modifies **how** you want the resource.

```
?page=2&limit=20
```

### Characteristics

- Optional (usually)
- Typically have default values
- Used for filtering, pagination, sorting

### FastAPI Syntax

```python
@app.get("/items")
def endpoint(page: int = 1, limit: int = 20):
    ...
```

### Mapping

```
GET /items?page=2
→ page=2, limit=20
```

---

## 3. Headers

### What They Are

**Metadata** about the request — not business data.

```
Authorization: Bearer xxx
Content-Type: application/json
User-Agent: Chrome
```

### Characteristics

- Do not identify resources
- Accompany every request
- Used for auth tokens, content negotiation, caching

### FastAPI Syntax

```python
from typing import Annotated
from fastapi import Header

@app.get("/secure")
def endpoint(authorization: Annotated[str, Header()]):
    ...
```

You can use `alias` for non-Pythonic header names:

```python
def endpoint(token: Annotated[str, Header(alias="X-Custom-Token")]):
    ...
```

> **`Header()` is not dependency injection.** It is a *parameter-source marker* — it tells FastAPI "read this value from the request headers," the same way `Query()`, `Path()`, `Cookie()`, `Body()`, `Form()`, and `File()` mark where a value comes from. All of these are resolved from the incoming request every time. `Depends()` is a different mechanism: it runs a callable (often to build a shared resource like a DB session or the current user) and injects its return value. A parameter can even combine both ideas — a dependency function can itself declare `Header()`/`Cookie()` parameters — but `Header()` alone never triggers dependency resolution. See [02_dependency_injection.md](02_dependency_injection.md) for how `Depends()` actually works.

---

## 4. Request Body

### What It Is

The **payload** of the request — structured data sent to the server.

```json
{
  "name": "Keyboard",
  "price": 100
}
```

### Characteristics

- Used in `POST`, `PUT`, `PATCH`
- For large or structured data
- Avoid in `GET` requests; GET request content has no generally defined HTTP semantics

### FastAPI Syntax

```python
from pydantic import BaseModel

class ProductCreate(BaseModel):
    name: str
    price: float

@app.post("/products")
def endpoint(product: ProductCreate):
    ...
```

### Beyond JSON: Other Body Encodings

`Content-Type` is just a label on whatever bytes follow the blank line — JSON and forms are the two encodings FastAPI parses for you automatically. Anything else, you read the raw body yourself and decode it. This matters whenever you're integrating with something that doesn't speak JSON: legacy SOAP/XML systems, binary sensor data, gRPC/protobuf services, or a client that streams a raw file as the entire body instead of wrapping it in `multipart/form-data`.

To get the raw, unparsed body, drop the `BaseModel`/`Form` parameter and take the `Request` object instead:

```python
from fastapi import Request

@app.post("/raw")
async def endpoint(request: Request):
    raw_bytes: bytes = await request.body()
    ...
```

Once you have `raw_bytes`, decoding is on you — FastAPI does not know or care what's inside.

#### `application/octet-stream` — arbitrary binary

```
POST /sensors/42/readings HTTP/1.1
Host: api.example.com
Content-Type: application/octet-stream
Content-Length: 8

<8 raw bytes, e.g. a packed struct>
```

```python
import struct
from fastapi import Request

@app.post("/sensors/{sensor_id}/readings")
async def ingest_reading(sensor_id: int, request: Request):
    body = await request.body()
    temperature, humidity = struct.unpack(">ff", body)  # big-endian, two 4-byte floats
    return {"sensor_id": sensor_id, "temperature": temperature, "humidity": humidity}
```

No structure is implied by the content type itself — `octet-stream` just means "bytes, interpret them yourself." Document the exact byte layout somewhere, since nothing in the request enforces it.

#### `text/plain` — unstructured text

```
POST /logs HTTP/1.1
Host: api.example.com
Content-Type: text/plain
Content-Length: 27

build failed: exit code 1
```

```python
from fastapi import Request

@app.post("/logs")
async def ingest_log(request: Request):
    body = await request.body()
    line = body.decode("utf-8")
    return {"received_chars": len(line)}
```

#### `application/xml` — legacy/enterprise integrations

FastAPI has no built-in XML support; you parse the body with the standard library or a package like `lxml`.

```
POST /orders HTTP/1.1
Host: api.example.com
Content-Type: application/xml
Content-Length: 78

<order><item_id>7</item_id><quantity>3</quantity></order>
```

```python
from xml.etree import ElementTree
from fastapi import Request

@app.post("/orders")
async def create_order_from_xml(request: Request):
    body = await request.body()
    root = ElementTree.fromstring(body)
    item_id = int(root.findtext("item_id"))
    quantity = int(root.findtext("quantity"))
    return {"item_id": item_id, "quantity": quantity}
```

Python's documented `xml.etree.ElementTree` implementation does not expand external entities, so
this exact parser is not an XML external entity (XXE) path. Untrusted XML can still consume
excessive CPU or memory, and other libraries or parser configurations have different entity
behavior. Bound body size and parsing resources; use `defusedxml` when you want a hardened,
library-independent boundary for XML you did not generate.

#### `application/x-protobuf` / gRPC — binary structured data

Used when you need compact, schema-enforced binary payloads (internal service-to-service calls, high-throughput pipelines) instead of JSON's text overhead. Requires a compiled `.proto` schema; FastAPI itself is protocol-agnostic here.

```
POST /events HTTP/1.1
Host: api.example.com
Content-Type: application/x-protobuf
Content-Length: 23

<23 raw protobuf-encoded bytes>
```

```python
from fastapi import Request
from myapp.generated import event_pb2  # compiled from event.proto

@app.post("/events")
async def ingest_event(request: Request):
    body = await request.body()
    event = event_pb2.Event()
    event.ParseFromString(body)
    return {"event_id": event.id, "type": event.type}
```

For a full gRPC service (as opposed to a single protobuf-over-HTTP endpoint), use `grpc.aio` instead of FastAPI's HTTP routing — gRPC has its own transport (HTTP/2 streaming, generated stubs) that doesn't map onto `@app.post`.

> **When to reach for raw body parsing vs. a model:** if the format has a native Python parser (JSON, form-urlencoded), let FastAPI/Pydantic handle it — you get validation, docs, and error responses for free. Drop to `Request.body()` only when the encoding is something FastAPI doesn't know about; you lose automatic validation and OpenAPI schema generation for that endpoint, so validate the decoded structure yourself before using it.

---

## 5. Cookies

### What They Are

Small pieces of data **stored by the browser or client cookie jar** and sent back with matching requests.

```
Cookie: session_id=abc123; theme=dark
```

### Characteristics

- Sent automatically by browsers when the domain, path, security, and SameSite rules match
- Can also be managed manually by non-browser API clients
- Used for browser sessions, user preferences, and sometimes tracking
- Scoped by domain and path; can expire with `Max-Age` or `Expires`
- Security flags matter: `HttpOnly`, `Secure`, and `SameSite`

### FastAPI Syntax

```python
from typing import Annotated
from fastapi import Cookie

@app.get("/profile")
def get_profile(session_id: Annotated[str | None, Cookie()] = None):
    ...
```

Required cookie:

```python
def endpoint(session_id: Annotated[str, Cookie()]):
    ...
```

> Prefer `Authorization` headers for API-to-API auth. Cookies shine for browser sessions, but session cookies usually need CSRF protection.

---

## 6. Form Data

### What It Is

Data submitted as a **URL-encoded or multipart form** — the encoding used by HTML `<form>` elements.

```
POST /login HTTP/1.1
Host: api.example.com
Content-Type: application/x-www-form-urlencoded
Content-Length: 30

username=alice&password=secret
```

### Characteristics

- Not JSON — individual form fields arrive as strings/files, then FastAPI/Pydantic can coerce types
- Cannot mix `Form` fields and a JSON body in the same endpoint
- `Content-Type` must be `application/x-www-form-urlencoded` or `multipart/form-data`

### FastAPI Syntax

```python
from typing import Annotated
from fastapi import Form

@app.post("/login")
def login(username: Annotated[str, Form()], password: Annotated[str, Form()]):
    ...
```

Install dependency if not present:

```bash
pip install python-multipart
```

Modern FastAPI also supports Pydantic models for form fields:

```python
from typing import Annotated
from fastapi import Form
from pydantic import BaseModel

class LoginForm(BaseModel):
    username: str
    password: str

@app.post("/login")
def login(data: Annotated[LoginForm, Form()]):
    ...
```

---

## 7. File Uploads

### What They Are

Binary files sent as part of a `multipart/form-data` request.

### Characteristics

- FastAPI `File` parameters expect `multipart/form-data` encoding
- Can be combined with `Form` fields in the same endpoint
- Cannot be combined with a JSON body

### Two ways to receive files

| Type         | Description                                    |
|--------------|------------------------------------------------|
| `bytes`      | Entire file loaded into memory at once         |
| `UploadFile` | Spooled file-like object; async reads, metadata |

Prefer `UploadFile` for anything beyond tiny files.

### Request Example

`multipart/form-data` splits the body into parts, each separated by a `boundary` string declared in the `Content-Type` header. Every part gets its own small header block (`Content-Disposition`, optionally its own `Content-Type`) followed by its raw content — this is how a single body carries a file's binary bytes alongside plain text fields without either corrupting the other.

```
POST /upload HTTP/1.1
Host: api.example.com
Content-Type: multipart/form-data; boundary=----WebKitBoundaryAbc123
Content-Length: 218

------WebKitBoundaryAbc123
Content-Disposition: form-data; name="file"; filename="photo.jpg"
Content-Type: image/jpeg

<binary JPEG bytes>
------WebKitBoundaryAbc123--
```

### FastAPI Syntax

```python
from typing import Annotated
from fastapi import File, UploadFile

@app.post("/upload")
async def upload_file(file: Annotated[UploadFile, File()]):
    contents = await file.read()
    return {"filename": file.filename, "size": len(contents)}
```

`UploadFile` attributes: `.filename`, `.content_type`, `.size`, `.headers`, `.file` (a `SpooledTemporaryFile`). Async methods include `.read()`, `.write()`, `.seek()`, and `.close()`.

### Mixed file + form fields

```python
@app.post("/upload-with-meta")
async def upload_with_meta(
    file: Annotated[UploadFile, File()],
    description: Annotated[str, Form()],
):
    ...
```

### Multiple files

```python
from typing import Annotated

@app.post("/upload-many")
async def upload_many(files: Annotated[list[UploadFile], File()]):
    return [f.filename for f in files]
```

---

## Part 2: FastAPI Parameter Resolution

FastAPI inspects the route and signature together. These are constraints, not a rule that
an arbitrary marker can override every other declaration:

1. `Depends(...)` declares a callable dependency; special types such as `Request` expose framework objects.
2. A request-data parameter matching a route placeholder is a required path parameter.
   `Query()` on that same name is a contradictory declaration and fails during route registration.
3. For other request-data parameters, explicit `Header`, `Cookie`, `Body`, `Query`, `Form`, or
   `File` annotations select their source, subject to supported type/source combinations.
4. Without an explicit source, a Pydantic model is a body; ordinary scalar values are query parameters.
   A default makes an inferred query parameter optional. It does not relocate a path parameter.

These rules apply to:

- Endpoint functions
- Dependency functions
- Nested dependencies

---

## The Resolution Rules

### Rule 1: No Default → Path or Query

```python
def endpoint(x: int):
    ...
```

- If `{x}` exists in the route path → **path parameter**
- Otherwise → **query parameter** (required)

### Rule 2: A default does not change a route placeholder

```python
def endpoint(x: int = 1):
    ...
```

- With no `{x}` in the route: optional query parameter with default `1`.
- With `{x}` in the route: required path parameter; omitting the segment does not select the default.
  Do not write path defaults: they misleadingly suggest a request can omit the segment.

### Rule 3: Pydantic Model → Body

```python
def endpoint(data: MyModel):
    ...
```

- Treated as **request body**
- FastAPI parses JSON into the model

### Rule 4: Explicit Source Annotations

```python
from fastapi import Header, Cookie, Body, Query, Path

def endpoint(
    user_id: int = Path(...),
    page: int = Query(1),
    token: str = Header(...),
    session: str = Cookie(...),
    payload: dict = Body(...),
):
    ...
```

Explicit annotations select a supported source; they cannot turn a route placeholder into a query parameter.

Current FastAPI docs prefer `typing.Annotated` for these annotations. The older default-value style shown in the quick reference still works and is common in existing codebases.

---

## Quick Reference Table

| Signature                  | Source          | Required |
| -------------------------- | --------------- | -------- |
| `x: int` (in path)         | Path parameter  | Yes      |
| `x: int` (not in path)     | Query parameter | Yes      |
| `x: int = 1` (not in path) | Query parameter | No       |
| `x: Model`                 | Request body    | Yes      |
| `x: str = Header(...)`     | Header          | Yes      |
| `x: str = Header(None)`    | Header          | No       |
| `x: str = Cookie(...)`     | Cookie          | Yes      |
| `x: str = Cookie(None)`    | Cookie          | No       |
| `x: str = Form(...)`       | Form field      | Yes      |
| `x: UploadFile = File(...)` | File upload    | Yes      |
| `x: str = Query(...)`      | Query parameter | Yes      |
| `x: int = Path(...)`       | Path parameter  | Yes      |

---

## Multiple Body Parameters

When you have multiple Pydantic models:

```python
class User(BaseModel):
    name: str

class Item(BaseModel):
    title: str

@app.post("/create")
def endpoint(user: User, item: Item):
    ...
```

FastAPI expects:

```json
{
  "user": {"name": "Alice"},
  "item": {"title": "Laptop"}
}
```

To embed a single model under a key, use `Body(embed=True)`:

```python
def endpoint(user: User = Body(embed=True)):
    ...
```

Expected:

```json
{
  "user": {"name": "Alice"}
}
```

---

## Mixing Parameter Types

A single endpoint can use all parameter types:

```python
@app.put("/users/{user_id}/items/{item_id}")
def update_item(
    user_id: int,                          # path
    item_id: int,                          # path
    item: Item,                            # body
    authorization: str = Header(...),      # header
    q: Optional[str] = None,               # query (optional)
):
    ...
```

Non-default arguments must come before defaulted ones (a general Python rule), so place `q` last.

FastAPI correctly routes each parameter based on the rules above.

---

## Key Takeaway

Resolve a parameter's source with the route constraint first:

1. A name in the route placeholder binds a required path value. A contradictory Query declaration is rejected; a Python default does not move the name into the query.
2. Otherwise, an explicit supported source marker (`Query`, `Header`, `Cookie`, `Body`, `Form`, `File`) selects that source.
3. Without a marker, a Pydantic model is a body input; an ordinary scalar is normally query input.
4. A default controls requiredness where that source permits it. `Depends` declares a callable whose own parameters follow these rules.

The function declaration determines extraction and schema, while request validation decides whether the actual value satisfies it.

## Version-sensitive request boundaries

Checked 2026-10-30 against FastAPI 0.162.0. Since 0.132.0, strict JSON Content-Type checking is enabled by default: send `application/json` (or a compatible JSON media type) for JSON bodies. A body containing JSON bytes with missing or `text/plain` Content-Type is not automatically accepted as a JSON model. This matters for browser request security, not merely documentation; prefer fixing clients over globally disabling the policy. [Strict Content-Type checking](https://fastapi.tiangolo.com/advanced/strict-content-type/).

Recent migrations change copyable parameter declarations:

| Version | Changed contract | Migration check |
|---|---|---|
| 0.155.0 | Arbitrary extra keyword arguments to parameter helpers are rejected | Replace `Query(custom="x")` with `Query(json_schema_extra={"custom": "x"})` |
| 0.160.0 | Parameter-model `extra` applies to all fields submitted in that location, including sibling/dependency fields | A query model with `extra="forbid"` can reject `trace` even when another dependency declares it; consolidate the location contract or choose an explicit extra policy |
| 0.162.0 | Omitted boolean form fields use declared defaults or missing-field errors | Declare `enabled: Annotated[bool, Form()] = False` for an unchecked checkbox; a required boolean is still required |

These changes are documented in the [FastAPI release notes](https://fastapi.tiangolo.com/release-notes/). The executable [runtime contract tests](./examples/test_runtime_contracts.py) cover path conflicts, strict JSON headers, sibling query fields and omitted forms. Run with `python -m pytest -q fundamentals/fastapi/examples/test_runtime_contracts.py` from the root after installing the pinned FastAPI quickstart environment plus `pytest` and `python-multipart`.

## Check your understanding

Route placeholders determine path binding; explicit compatible source markers then disambiguate input. Defaults describe requiredness within a supported source.

**Prediction:** For /items/{item_id}, does item_id: int = 5 become an optional query parameter?

<details><summary>Answer</summary>
No. The matching route name binds the required path value. A non-route scalar named limit with that default would normally be query.
</details>

**Diagnosis:** Can Query override a matching path-placeholder name?

<details><summary>Answer</summary>
No. The contradictory declaration is rejected; it does not relocate the route value.
</details>
