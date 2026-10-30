# Choose search by the meaning of a match and the cost of freshness

Role: decision guide. Prerequisites: [SQL basics](../../fundamentals/database/01_databases_and_schemas.md)
and [query performance](../../fundamentals/database/11_query_performance.md).
For a document service already using PostgreSQL, begin with its full-text search when lexical
matching meets the product need. Add a separate search engine or vector index for measured relevance,
feature or capacity requirements; each extra index becomes another data copy to update and delete.

## Three queries ask for three different relationships

`retention` asks for words and normalized variants. `retentoin` asks for typo similarity. “How long
do you keep my report?” may require semantic similarity even without the exact word. PostgreSQL
full-text search tokenizes and normalizes words; trigram matching compares small character sequences;
embeddings map meaning into numeric vectors. These are different relevance models, not successive
versions of the same index.

This complete SQL transaction is for a disposable PostgreSQL 15+ database and rolls its objects
back. It demonstrates matching, not performance at scale; it was not executed here without a server.

```sql
BEGIN;
CREATE TEMP TABLE search_demo (tenant_id integer, id integer, body text);
INSERT INTO search_demo VALUES
  (7, 42, 'Reports have a retention period of thirty days.'),
  (8, 43, 'Reports have a retention period of ninety days.');
CREATE INDEX search_demo_words ON search_demo
  USING gin (to_tsvector('english', body));
SELECT id FROM search_demo
WHERE tenant_id = 7
  AND to_tsvector('english', body) @@ plainto_tsquery('english', 'retention');
ROLLBACK;
```

The result should be `42`. `tenant_id = 7` excludes document 43 even though its wording matches.
The query and expression index use the same explicit language configuration. On two rows a sequential
scan is sensible; index existence does not prove an index scan should win. In application code,
bind tenant and search terms as parameters and derive tenant scope from authentication.
[PostgreSQL text-search indexes](https://www.postgresql.org/docs/18/textsearch-tables.html), checked 2026-10-30.

## Decide where the index should live

| Need | Candidate | Added obligation |
|---|---|---|
| Transactionally current lexical search over PostgreSQL rows | PostgreSQL full-text/GIN | Tune language, ranking and write/index cost |
| Typos and substring-like similarity | PostgreSQL `pg_trgm` | Measure selectivity and index size |
| Rich analyzers, facets, large independent search workload | OpenSearch | CDC/outbox feed, mappings, shards, recovery and deletion lag |
| Semantic matching near existing relational metadata | PostgreSQL with pgvector | Embedding version, distance metric, recall/latency evaluation |
| Combined keyword and semantic ranking | Hybrid search in a measured stack | Calibrated score fusion and separate retrieval evals |

An approximate nearest-neighbor index (ANN) trades some recall for speed. A post-filter can remove
unauthorized candidates after the nearest k are selected, leaving fewer than k results even when
more authorized matches exist. Apply supported filters during search and recheck source permissions
before exposing content. Larger k alone is not an access-control strategy.
[OpenSearch filtering](https://docs.opensearch.org/latest/vector-search/filter-search-knn/index/)
and [pgvector filtering/iterative scans](https://github.com/pgvector/pgvector), checked 2026-10-30.

## An external index is a projection with a lag budget

The mutation path explains why a committed database update can temporarily disagree with search:

```mermaid
flowchart LR
    A[Document 42 revision 4 committed] --> B[Outbox event]
    B --> C[Index worker]
    C --> D[Search projection revision 4]
    D --> E[Authorized query results]
```

The worker can lag or repeat an event. Store a source revision and update idempotently so revision 3
cannot overwrite 4. Monitor oldest unapplied event age and indexing failures, not only query latency.
Deletion must immediately block serving through authoritative metadata while physical index cleanup
completes. Rebuild into a new index generation, compare relevance and row/revision coverage, then
switch an alias or application pointer; retain a bounded rollback generation subject to deletion policy.

Before buying more search infrastructure, benchmark representative corpus sizes, tenant filters,
write rates and warm/cold caches. Build labeled queries with expected evidence and measure recall@k,
ranking quality, p95/p99 latency, freshness and storage cost. “Queries are fast” is insufficient when
the best answer is missing or a revoked document is returned. Keep a runbook for stale projections:
check source revision, outbox age and worker errors, replay from a known cursor, and verify a changed
document plus a deleted document before declaring recovery.

## What's changing

Checked 2026-10-30: OpenSearch documents engine-specific efficient filtering and marks nmslib
deprecated. pgvector documents iterative scans for filtered ANN shortfalls. Pin and test the actual
engine/extension version; do not copy a query from a different engine and assume the same recall.
The primary sources above own those feature details. [RAG](../../architecture/llm_systems/03_retrieval_augmented_generation.md)
adds evidence/citation handling after this search decision.

**Decision exercise:** compliance requires a deleted document to stop appearing immediately, while
an external search cluster can lag by a minute. Must every deletion wait synchronously for the cluster?

<details><summary>Answer</summary>

No, if the application can durably tombstone the source immediately and enforce that authoritative
check before returning search content. Physical deletion may then complete asynchronously within its
own verified deadline. If callers can access the cluster directly and bypass that check, the proposed
boundary does not satisfy the requirement.

</details>
