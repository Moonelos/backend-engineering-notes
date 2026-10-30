# API Styles and Selection

> **Who this is for**: Engineers choosing an integration style after learning the contract model in [API Fundamentals](01_api_fundamentals.md).

> **Key insight**: Choose an API style from interaction shape, ownership, and failure semantics; payload syntax is a secondary consequence.

---

## 1️⃣ Compare the Right Things

REST, SOAP, GraphQL, gRPC, WebSocket, and webhooks solve overlapping but different problems.

| Choice | What it is | Normal interaction | Strongest fit |
|--------|------------|--------------------|---------------|
| REST | Architectural style commonly realized with HTTP | Request-response | Resource-oriented public and internal APIs |
| SOAP | XML messaging protocol with a large standards ecosystem | Request-response or messaging | Existing Web Services Description Language (WSDL) contracts and WS-* Web Services standards |
| GraphQL | Typed query language and execution model | Request-response; subscriptions possible | Client-selected data across a connected domain graph |
| gRPC | RPC framework commonly using Protocol Buffers (Protobuf), a schema language and compact binary message format, over HTTP/2 | Unary and streaming RPCs | Typed service-to-service calls in controlled environments |
| WebSocket | Persistent, full-duplex message protocol | Bidirectional messages | Frequent low-latency updates in both directions |
| Webhook | Provider-to-consumer HTTP callback pattern | Asynchronous event notification | Cross-organization event delivery without persistent connections |

The choices can coexist. A product might expose REST publicly, use gRPC internally, notify partners through webhooks, and power collaboration through WebSockets.

---

## 2️⃣ Decision Matrix

| Requirement | Default choice | Why | Check before committing |
|-------------|----------------|-----|-------------------------|
| Broad browser, mobile, CLI, and partner compatibility | REST over HTTPS | Universal tooling, HTTP semantics, cache support | Does the domain fit resources and standard methods? |
| Each screen needs a different projection of a connected data graph | GraphQL | Consumer selects fields and nested relations | Can the team control query cost and resolver performance? |
| Low-latency calls between owned services in several languages | gRPC | Generated types, compact messages, streaming, deadlines | Do proxies, debuggers, and clients support the stack? |
| Frequent two-way interactive messages | WebSocket | One persistent duplex channel | Can you own reconnection, message contracts, backpressure, and fleet state? |
| Notify another system after an event | Webhook | Receiver needs only an HTTPS endpoint | Can both sides handle duplicates, delay, signatures, retries, and replay? |
| Formal XML contracts, intermediaries, or required WS-Security features | SOAP | Mature standards and enterprise tooling | Is this a real constraint or only organizational habit? |
| Infrequent one-way browser updates | Server-Sent Events (SSE), a one-way HTTP event stream, or polling | Simpler than a duplex socket | Does the client ever need to send on the same channel? |

> **Rule**: Choose the simplest mechanism that satisfies the interaction. Persistent connections and flexible query engines have real operational cost.

---

## 3️⃣ Strengths and Trade-offs

### RESTful HTTP

REST fits a resource-oriented boundary whose consumers already understand HTTP. That earns broad
tooling and cache support; poor resource modeling instead produces inconsistent RPC-shaped URLs.

✅ Human-readable, broadly supported, gateway-friendly, and able to use standardized caching and conditional requests.

⚠️ A poorly modeled REST API becomes inconsistent RPC disguised as URLs. Multiple round trips or fixed representations can be awkward for complex UI aggregation.

### SOAP

SOAP earns its weight when an integration must honor formal XML contracts, intermediaries, or a
specific enterprise Web Services profile. Without that requirement, its standards and tooling add
complexity without a matching interoperability benefit.

✅ Precise XML contracts, formal faults, extensible headers, and established standards for some enterprise requirements.

⚠️ Verbose messages, complex tooling, and WS-* profiles add weight. Starting a greenfield SOAP API without a concrete interoperability requirement is rarely the simplest choice.

### GraphQL

GraphQL fits when clients genuinely need different projections of connected data. That flexibility
moves query cost, field authorization, and data-loader behavior into the server's execution layer.
**Schema introspection** lets a client query which types and fields the schema exposes, powering
strong tooling but not replacing authorization.

✅ One typed graph lets consumers request the exact connected shape they need. Schema introspection and client tooling are strong.

One order lookup followed by one separate item lookup for each returned order is the **N+1 access
pattern**: one parent query plus N child queries. A resolver can create that shape invisibly unless
the server batches or preloads the child access.

⚠️ Field-level authorization, query cost, caching, N+1 access, and compatibility move into the
GraphQL execution layer. Client-selected fields do not make expensive joins free.

### gRPC

gRPC fits controlled service boundaries where teams can distribute generated clients and operate
HTTP/2. Its efficient wire format and typed stubs come with a schema-release and specialized-tooling
workflow.

✅ Code generation, compact binary payloads, four RPC streaming modes, deadlines, metadata, and standardized status codes work well for service calls.

⚠️ Binary debugging and browser support require different tooling. Generated clients and strict schema discipline are part of the workflow.

### WebSocket

WebSocket fits sustained bidirectional interaction. A long-lived channel avoids repeated request
setup, but the application must now own reconnect, replay, flow control, and fleet connection state.

✅ Low-overhead, full-duplex delivery after connection establishment.

⚠️ The protocol supplies a channel, not event schemas, acknowledgements, resumption, authorization rules, or backpressure policy. Long-lived connections also change deployment and capacity planning.

### Webhooks

Webhooks fit cross-organization notification because the producer can call an ordinary HTTPS
endpoint without maintaining a connection. Receiver outages and ambiguous network outcomes make
durable retries, signatures, and consumer idempotency part of the design.

✅ Cross-system push without polling or a permanent connection.

⚠️ The receiver may be unavailable, slow, compromised, or duplicated. Producers need durable delivery state; consumers need verification and idempotency.

---

## 4️⃣ A Practical Selection Flow

```text
Does another system only need notification after an event?
├── yes → webhook (plus a read API for reconciliation)
└── no
    │
    ├── Need frequent messages initiated by both sides?
    │   └── yes → WebSocket
    │
    ├── Owned service-to-service clients, generated types, streaming?
    │   └── yes → gRPC
    │
    ├── Consumer must select a graph-shaped response dynamically?
    │   └── yes → GraphQL
    │
    ├── Required WSDL / WS-* enterprise interoperability?
    │   └── yes → SOAP
    │
    └── default → RESTful HTTP
```

This is a starting point, not a scoring algorithm. Network policy, team expertise, ecosystem constraints, existing consumers, and operational tooling can outweigh technical preference.

---

## 5️⃣ Worked Architecture: Order Platform

```text
browser/mobile ──REST/GraphQL──> API edge
                                  │
                                  ├──gRPC──> inventory service
                                  ├──gRPC──> pricing service
                                  └──REST──> payment provider

API edge ──WebSocket──> browser order-status screen
order service ──webhook──> merchant fulfillment system
legacy ERP <──SOAP──> integration adapter
```

Why each boundary differs:

- Public clients favor accessible HTTP tooling and explicit compatibility.
- Owned internal services benefit from generated gRPC clients and deadlines.
- The status screen needs timely server pushes and also sends client acknowledgements.
- Merchants cannot hold inbound connections to the platform, so the platform calls their webhook endpoints.
- The existing ERP contract already requires WSDL and SOAP; an adapter contains that complexity.

Trying to standardize every arrow on one technology would make at least one boundary worse.

---

## 6️⃣ Common Selection Mistakes

| Mistake | Why it fails | Better question |
|---------|--------------|-----------------|
| “GraphQL removes over-fetching, so use it everywhere” | Runtime cost and authorization become query-dependent | Do consumers truly need arbitrary projections? |
| “WebSockets are faster HTTP” | They introduce connection state and recovery work | Is frequent bidirectional push required? |
| “gRPC is always faster” | End-to-end latency may be database or dependency bound | Is serialization/transport material, and can every hop support it? |
| “Webhooks guarantee real-time delivery” | Delivery is delayed by outages, retries, and queues | What staleness and reconciliation guarantees are required? |
| “JSON endpoints are REST” | JSON says nothing about REST constraints or HTTP semantics | Does the interface model resources and use a uniform, self-descriptive interface? |
| “Internal APIs can break freely” | Independent deployments and hidden consumers create coupling | How will old and new versions overlap during rollout? |

---

## References

- [REST architectural style](https://ics.uci.edu/~fielding/pubs/dissertation/rest_arch_style.htm)
- [GraphQL specification](https://spec.graphql.org/)
- [gRPC core concepts](https://grpc.io/docs/what-is-grpc/core-concepts/)
- [The WebSocket Protocol — RFC 6455](https://www.rfc-editor.org/rfc/rfc6455)
- [SOAP 1.2 Messaging Framework](https://www.w3.org/TR/soap12-part1/)

---


## Recap

- Choose the interaction direction and ownership before selecting a protocol.
- Client diversity favors accessible contracts; controlled peers can benefit from generated RPC.
- A persistent bidirectional channel also needs application reliability and security.

## Check yourself

**The order-status browser only receives occasional server updates and never sends application messages on that channel. Is WebSocket still the default?**

<details><summary>Reasoned answer</summary>

No. SSE or polling meets the one-way requirement with less connection-protocol machinery; the two-way premise in the platform example no longer holds.

</details>

**A mobile client is often offline. Does choosing WebSocket deliver all missed events?**

<details><summary>Reasoned answer</summary>

No. A live connection is only a transport. Retained events, a cursor or a snapshot API provide recovery.

</details>

**Next**: [API Contracts and Lifecycle](03_api_contracts_and_lifecycle.md)
