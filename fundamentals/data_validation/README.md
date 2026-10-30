# Schema evolution

Extend the Pydantic foundation with reader/writer compatibility and persisted-data upgrades.

## Reading path

Start with [Pydantic models](../core_concepts/data_models/pydantic/README.md). Continue here when schemas outlive one process or deployment. The core Pydantic lessons own validation and serialization; FastAPI owns HTTP integration.

## Contents

| Chapter | Outcome |
|---|---|
| [Schema compatibility](01_schema_compatibility.md) | Missing versus null, versioned envelopes, upcasting and mixed deployments. |
