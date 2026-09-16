# fundamentals/README.md (37 lines)
ORDERING: role reference/navigation; n/a; payoff n/a; lines 9–29 provide roles, outcomes, milestone, stop point, and continuation.
EXPLANATION: n/a; teach-back n/a (missing: none); this is a path index.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The index gives a usable first-time sequence and explicit Docker/shell prerequisites.

# fundamentals/01_first_event_round_trip.md (91 lines)
ORDERING: role implementation; PASS; payoff 31/91; lines 7–27 are the bounded setup and round trip itself, with exact success/failure evidence at lines 29–34.
EXPLANATION: PASS; teach-back PASS (missing: none); lines 38–66 distinguish retained broker state from consumer position, and lines 70–85 supply first failures and the disposable-only boundary.
Summary: 0 critical, 0 high, 1 med, 0 low

FIX-MED: Line 26 uses deprecated `--property` formatter options. Exact Kafka 4.3.1 execution succeeded but warned twice that `--property` will be removed and `--formatter-property` should be used. Replace both options and reproduce the displayed output.

# fundamentals/02_log_topics_partitions_and_offsets.md (93 lines)
ORDERING: role foundation; PASS; payoff 17/93; a named partition/offset/group-position transition precedes the abstraction.
EXPLANATION: FAIL; teach-back PASS (missing: none after the full note); the full prose explains retained logs, actors, partition ordering, cleanup, lag, and the out-of-range failure, but the opening depends on an ungrounded group concept.
Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: Lines 13 and 16 use `group billing-v1` and “this group” before a no-prior-Kafka reader learns whether that position belongs to a process, topic, or logical subscription; the first gloss arrives at line 25 and the owner is note 04. Add a short first-use definition beside line 13 without moving the full rebalance lesson forward.

# fundamentals/03_partitioning_keys_and_ordering.md (81 lines)
ORDERING: role deep dive; PASS; payoff 9/81; a bad-key failure motivates routing and ordering immediately.
EXPLANATION: PASS; teach-back PASS (missing: none); lines 13–30 map serialized key bytes and partitioner to placement, while lines 34–77 demonstrate invariant choice, skew, partition expansion, verification, and the global-order boundary.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The note carries key selection through a concrete failure, routing trace, compatibility check, expansion hazard, and skew trade-off.

# fundamentals/04_consumer_groups_offsets_and_rebalancing.md (87 lines)
ORDERING: role deep dive; PASS; payoff 15/87; the three-partition/four-consumer trace makes the scaling constraint visible before protocol depth.
EXPLANATION: FAIL; teach-back FAIL (missing: assignment/checkpoint actor and an idempotency bridge); assignment and duplicate traces exist, but coordination remains passive and the safety prescription is unexplained.
Summary: 0 critical, 2 high, 1 med, 0 low

FIX-HIGH: Lines 19–34 never identify the group coordinator as the actor managing membership/assignment and committed offsets. Introduce it in plain language and map one join/leave event to assignment state and the stored checkpoint.

FIX-HIGH: Line 41 says effects need idempotency without explaining how the duplicate-charge trace changes. Add the local bridge: a retried effect reuses a stable operation/event identity and the effect store/provider returns the prior result rather than applying it twice; retain the link to the full reliability owner.

FIX-MED: Lines 52–57 delegate a `group.protocol=consumer` rollout check to `operations/05`, which contains no such check. Add a minimal effective-config/assignment carrier and the online/offline migration boundary, or link to a real owner. Apache Kafka documents that the consumer protocol is GA but not the 4.3 client default and disables several classic client settings: https://kafka.apache.org/43/operations/consumer-rebalance-protocol/ (checked 2026-09-16).

# fundamentals/05_replication_leaders_and_kraft.md (78 lines)
ORDERING: role deep dive; PASS; payoff 9/78; one acknowledged record produces two failure outcomes before mechanism detail.
EXPLANATION: FAIL; teach-back FAIL (missing: correct acknowledgment and safe-election transitions); the KRaft metadata/data-plane distinction is clear, but the central durability transition is incorrect and the 4.3 election model is stale.
Summary: 0 critical, 2 high, 0 med, 0 low

FIX-HIGH: Lines 7–9 and 30–37 conflate the `min.insync.replicas` admission floor with what `acks=all` waits for. Kafka 4.3 waits for every current ISR member; `min.insync.replicas` rejects the write when the ISR is too small. Add `ISR={1,2,3}, minISR=2 → wait for 3` versus `ISR={1}, minISR=2 → NotEnoughReplicas/NotEnoughReplicasAfterAppend`. Sources: https://kafka.apache.org/43/configuration/topic-configs/ and https://kafka.apache.org/43/generated/producer_config.html (checked 2026-09-16).

FIX-HIGH: Lines 15–26 present ISR as the only safe-leadership category, but Eligible Leader Replicas are enabled by default on new clusters from Kafka 4.1 and election order is ISR then unfenced ELR. Add an ISR-empty/ELR-present trace and retain unclean last-known-leader election as the lossy contrast. Source: https://kafka.apache.org/43/operations/eligible-leader-replicas/ (checked 2026-09-16).
