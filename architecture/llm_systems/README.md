# LLM systems

Build a bounded document-extraction workflow from a provider boundary through evidence retrieval and measured releases.

## Reading path

Read the existing HTTPX and LLM-testing lessons linked in chapter 01. Run the offline script in 01, then 02; continue to retrieval only if the product needs external evidence. Stop after 02 for bounded extraction; complete 04–05 before a production release.

## Contents

| Chapter | Outcome |
|---|---|
| [Provider boundaries](01_provider_abstraction.md) | Normalize complete, refused and incomplete outcomes; run the offline boundary example. |
| [Prompts and schemas](02_prompt_and_schema_design.md) | Version instructions, validate evidence and preserve reader compatibility. |
| [Authorized retrieval](03_retrieval_augmented_generation.md) | Ingest revisions, retrieve evidence, cite it and enforce deletion. |
| [Evals and regression](04_evals_and_regression.md) | Run a local slice gate; design holdout and canary decisions. |
| [Safety, cost and telemetry](05_safety_cost_and_observability.md) | Constrain tools, reserve budgets and diagnose actual attempts. |
