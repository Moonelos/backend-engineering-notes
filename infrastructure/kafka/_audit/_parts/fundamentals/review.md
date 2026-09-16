# Fundamentals package review — 2026-09-16

Scope: `infrastructure/kafka/fundamentals/README.md` and teaching notes `01`–`05` only. The root Kafka contract sets Kafka 4.3.x, Python 3.11+, backend engineers who have not operated Kafka, Docker and a shell for this first path, and no prior Kafka knowledge (`infrastructure/kafka/README.md:3-6,47-67,101-105`; `fundamentals/README.md:33-36`). Findings below concern only the assigned fundamentals files. Cross-topic observations are candidates for the collection-wide report owner, not duplicate findings.

## Per-note review

### `fundamentals/README.md` (37 lines)

ORDERING: role index/learning-path map; n/a; payoff n/a. Lines 9-15 map every note to a role and outcome, lines 21-26 state the entry-two milestone and progression, and lines 28-29 provide a stop point and continuation.

EXPLANATION: n/a; teach-back n/a (missing: n/a). This file is navigation rather than a canonical mechanism owner.

Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The index gives a usable first-time sequence, declared milestone, prerequisites, and stop point in 37 lines (`fundamentals/README.md:9-36`).

### `fundamentals/01_first_event_round_trip.md` (91 lines)

ORDERING: role implementation; PASS; payoff spans lines 5-31 and is complete by 31/91 (34.1%). The apparently long payoff distance is not a buried baseline: lines 7-27 are the bounded two-command setup and publish/consume path itself, and lines 29-31 give the exact result and first startup failure. Production deferrals immediately follow at lines 33-34.

EXPLANATION: PASS; teach-back PASS (missing: none). Problem: queue-shaped deletion intuition (`01:40-42`). Owned state: retained record versus separately tracked consumer position (`01:42`). Actors: producer, broker log, and consumer (`01:44-50`). Transition/result: publish to `orders` partition 0 offset 0, consume it, and retain it (`01:46-52`). Misconception boundary: consuming advances a reader rather than transferring/removing the record (`01:40-42,65-66`). First failure: ephemeral storage and advertised-listener mismatch with observable symptoms (`01:70-77`).

Summary: 0 critical, 0 high, 1 med, 0 low

FIX-MED: The copyable Kafka 4.3.1 consumer command uses deprecated `--property` options at line 26. Exact execution succeeded, but Kafka printed `Option --property is deprecated and will be removed in a future version. Use --formatter-property instead.` twice (initial consume and replay). Replace both formatting arguments with the supported `--formatter-property` form and reproduce the displayed output, so the version-pinned first command does not teach a soon-to-be-removed CLI form.

### `fundamentals/02_log_topics_partitions_and_offsets.md` (93 lines)

ORDERING: role foundation; PASS; payoff spans lines 5-17 and is complete by 17/93 (18.3%). Named partitions, offsets, a group position, the commit action, and retained result precede taxonomy and deeper cleanup/lag material.

EXPLANATION: FAIL; teach-back PASS (missing: none after the full note). Problem: destructive-read semantics would make independent readers race (`02:21-25`). Owned state: the append-only log and each group's independent position (`02:23-25`). Actors: producers append, retention removes, and consumer groups hold positions (`02:23-25`). Transition/result: billing processes offset 0, commits next offset 1, while the record remains (`02:7-17`). Misconception boundary: queue-like reads do not delete (`02:27-28`). First failure: retention deletes the resume position and invokes reset behavior (`02:80-84`). The local first-use defect below prevents a clean explanation verdict despite the eventual teach-back evidence.

Summary: 0 critical, 1 high, 0 med, 0 low

FIX-HIGH: The opening trace uses `group billing-v1` and “this group” at lines 13 and 16 before a no-prior-Kafka reader is told what a consumer group is; its first grounding arrives only at line 25, and full group mechanics are deferred to note 04. Because the opening's commit meaning depends on knowing whether the position belongs to a process, a topic, or a logical subscription, add a short first-use gloss beside line 13 (for example, a named logical subscription whose members share a saved position), without pulling rebalance details forward.

### `fundamentals/03_partitioning_keys_and_ordering.md` (81 lines)

ORDERING: role deep dive; PASS; payoff spans lines 5-9 and is complete by 9/81 (11.1%). The motivating failure—two events for one order complete in the wrong business order because they were routed to different partitions—arrives before the hash/routing mechanism and operational caveats.

EXPLANATION: PASS; teach-back PASS (missing: none). Problem: related events on independently consumed partitions can complete out of order (`03:5-9`). Decision: serialized key bytes and the client's partitioner choose placement (`03:15,27-30`). Actor: the producer selects/serializes the key (`03:15-16`). Transition/result: `ord-42` events hash to partition 2 and receive offsets 17-19 (`03:18-22`). Misconception boundary: the key is not decorative metadata, and displayed strings alone do not determine placement (`03:24-30`). First failure/trade-off: a hot entity overloads one partition, while splitting the key weakens ordering (`03:40-42`).

Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The note carries key selection through a concrete failure, routing trace, compatibility check, expansion hazard, skew trade-off, and “do not require global order” boundary (`03:5-77`).

### `fundamentals/04_consumer_groups_offsets_and_rebalancing.md` (87 lines)

ORDERING: role deep dive; PASS; payoff spans lines 5-15 and is complete by 15/87 (17.2%). The partition-to-consumer assignment and idle fourth member make the scaling constraint visible before offset, rebalance, polling, and protocol detail. The newer protocol appears after the classic baseline rather than before it (`04:45-57`).

EXPLANATION: FAIL; teach-back FAIL (missing: assignment/checkpoint actor). Problem and state are present: a group divides partitions and owns committed recovery positions (`04:19-26`). Transitions/results are concrete: a fourth member is idle (`04:5-15`) and offset 8 is processed twice across a crash/rebalance (`04:30-41`). Misconception and first failures are also present (`04:41,47-50,76-79`). However, the note never identifies the group coordinator—or another explicit Kafka actor—as the component that manages membership/assignment and stores/serves committed offsets; “membership changes cause partition assignment to change” at lines 30-34 leaves the central coordinating actor implicit.

Summary: 0 critical, 2 high, 1 med, 0 low

FIX-HIGH: The canonical group deep dive omits the actor that owns the coordination decision. Lines 19-34 describe shared `group.id`, committed offsets, and assignment changes only in passive voice, so a reader cannot explain who observes membership, computes/communicates assignments, or handles offset commits. Introduce the group coordinator in plain language and map one join/leave event to assignment state plus the stored checkpoint; keep protocol-specific implementation detail in the later subsection.

FIX-HIGH: Line 41 prescribes “consumer effects need idempotency” without grounding idempotency for the declared no-Kafka-knowledge audience or showing how it changes the duplicate-charge trace at lines 36-39. The later reliability course may own the full implementation, but this note needs the inline causal bridge: the repeated attempt must reuse a stable operation/event identity so the external system returns the prior result instead of applying the effect twice, followed by a link to the canonical implementation owner.

FIX-MED: Lines 52-57 tell the reader that `group.protocol=consumer` moves policy to the broker and delegates the “rollout check” to `operations/05_configuration_and_topic_administration.md`, but that linked owner contains no `group.protocol`, consumer-protocol, migration, or rebalance rollout check. The Apache 4.3 protocol guide also says the protocol is not the client default, identifies settings/APIs that stop applying, and supplies distinct online/offline upgrade constraints. Point to an actual owner (or narrow the deferral) and give a minimal effective-config/assignment carrier so “effective settings” is observable rather than an unsupported instruction. Source checked 2026-09-16: <https://kafka.apache.org/43/operations/consumer-rebalance-protocol/>.

### `fundamentals/05_replication_leaders_and_kraft.md` (78 lines)

ORDERING: role deep dive; PASS; payoff spans lines 5-9 and is complete by 9/78 (11.5%). A single acknowledged offset produces different loss outcomes under one versus three replicas before leader/follower, ISR, settings, and KRaft detail.

EXPLANATION: FAIL; teach-back FAIL (missing: correct acknowledgment and safe-election transitions). Problem, actors, planes, misconception, and first failure are otherwise visible (`05:5-26,36-37,41-52`). The central three-setting explanation at lines 30-37 says `acks=all` “makes the producer wait for” the `min.insync.replicas` rule. In Kafka 4.3, `acks=all` waits for every replica currently in the ISR; `min.insync.replicas` is the admission floor (including the leader) below which the broker rejects the write. Thus the reader cannot correctly predict a three-member ISR with `min.insync.replicas=2`: all three, not merely two, must acknowledge. Lines 15-26 also leave ELR out of the 4.3 safe-election model, so the reader cannot predict an ISR-empty/ELR-present election.

Summary: 0 critical, 2 high, 0 med, 0 low

FIX-HIGH: Correct lines 7-9 and 30-37 to separate three decisions: replication factor is desired copies; `min.insync.replicas` is the minimum ISR size that admits an `acks=all` write; and `acks=all` waits for the full current ISR. Add the contrasting RF=3 cases `ISR={1,2,3}, minISR=2 → wait for 3` and `ISR={1}, minISR=2 → reject`, including the actual `NotEnoughReplicas`/`NotEnoughReplicasAfterAppend` symptom. Apache Kafka 4.3 states both behaviors explicitly. Sources checked 2026-09-16: <https://kafka.apache.org/43/configuration/topic-configs/> and <https://kafka.apache.org/43/generated/producer_config.html>.

FIX-HIGH: The 4.3.x safe-leadership model at lines 15-26 is stale by omission. Line 16 presents ISR membership as what makes a replica eligible for safe leadership, and line 25 says the controller chooses an “eligible follower,” but Kafka 4.3 also has Eligible Leader Replicas (ELR): ELR is enabled by default on new clusters from 4.1, and safe election order is ISR first, then an unfenced ELR. A reader using this note to decide which broker failures remain available can therefore wrongly predict no safe election when ISR is empty but ELR is populated. Add the ISR-empty/ELR-present transition and explain that strict `min.insync.replicas` high-watermark behavior is what can make a replica outside the current ISR safe; keep unclean last-known-leader election as the explicitly lossy contrast. Source checked 2026-09-16: <https://kafka.apache.org/43/operations/eligible-leader-replicas/>.

## Candidate coverage classifications

These are inputs for the collection-wide coverage owner, not canonical coverage findings.

| Mechanism | Candidate owner | Required | Achieved | Teach-back / note |
|---|---|---:|---:|---|
| Disposable one-broker event round trip | `01` | demonstrated | operationalized | PASS for the local/disposable claim: exact execution, success/failure signals, cleanup, and production boundary; CLI deprecation remains local. |
| Retained record versus consumer position | `01`/`02` (with `02` canonical) | demonstrated | demonstrated | PASS; replay and named offset trace establish the separation. |
| Topic/partition/offset identity and ordering boundary | `02` | demonstrated | demonstrated | PASS; two-partition trace and contrast show non-global offsets/order. |
| Retention versus compaction | `02` | demonstrated | demonstrated | PASS for conceptual use: named compaction trace and suitability boundary; operational configuration belongs later. |
| Consumer lag meaning | `02` | explained | explained | Formula, consequence, and complementary age signal are present, but no numeric changed-input trace. |
| Key-to-partition routing and per-entity order | `03` | demonstrated | demonstrated | PASS; concrete hash/partition/offset trace and bad-key contrast. |
| Cross-client partitioner compatibility | `03` | explained | explained | Fixture procedure and mismatch consequence exist; no composed multi-client artifact. |
| Partition expansion/key movement | `03` | explained | explained | The 6-to-12 change and mitigation are causal but do not show an actual before/after placement. |
| Group subscription, assignment, and committed position | `04` | demonstrated | demonstrated, explanation incomplete | Traces carry assignment and recovery, but teach-back lacks the coordinator actor. |
| Rebalance duplicate window | `04` | demonstrated | demonstrated | Offset-8 crash trace and duplicate consequence are concrete; idempotency bridge is unexplained. |
| Consumer protocol (`group.protocol=consumer`) | `04` | explained | defined | Version/status and broad purpose are stated, but effective settings, changed assignment interaction, migration constraints, and a valid owner are absent. |
| Leader/follower replication, ISR, and safe election | `05` | demonstrated | explained, stale for 4.3 | The three-broker trace carries ordinary replication, but the safe-election model omits default-on-new-cluster ELR and cannot predict an ISR-empty/ELR-present election. |
| `replication.factor` + `min.insync.replicas` + `acks=all` contract | `05` | demonstrated | defined, materially incorrect | The central transition conflates the ISR admission floor with the acknowledgers waited on. |
| KRaft metadata quorum versus partition data | `05` | explained | explained | Plane ownership and contrasting losses are clear; no runnable failure claim is made. |

RELATED (currency confirmed): Note 05's statement that Kafka 4.0 was the first ZooKeeper-free major release is current and supported by the linked Apache release announcement, checked 2026-09-16: <https://kafka.apache.org/blog/2025/03/18/apache-kafka-4.0.0-release-announcement/>.

## Reader-path dependency observations

- The fundamentals path meets its declared execution and understanding milestone: entry 1 produces/consumes the record (`01:5-31`), and entry 2 explains retained storage plus `(topic, partition, offset)` (`02:5-28,71-76`).
- Earliest local dependency friction: entry 2's opening uses a consumer group before grounding it (`02:13-16`); the full owner is entry 4. The local first-use repair above is enough—reordering the full deep dive before the storage model would worsen the path.
- Entry 4 correctly surfaces the duplicate-effect problem but depends on idempotency, whose implementation is in the later reliability path. A one-sentence bridge is needed locally; the full implementation should remain later.
- The root “Explore Kafka with a runnable record” path lists fundamentals 01-04 and then application design (`infrastructure/kafka/README.md:54-58`), while the section path says hardening the model includes replication (`fundamentals/README.md:24-26`) and the root section outcome promises tracing through replication (`infrastructure/kafka/README.md:35-38`). The collection-wide reader-path owner should reconcile whether note 05 is part of that named path; no duplicate local severity is assigned here.

### Transfer probes from assigned material

1. After `02`, change from one to two consumer groups reading the same partition. Expected reasoning: both groups can read offset 0 because records are retained and each group owns an independent position (`02:16-28`). Verdict: PASS.
2. After `03`, double partitions from 6 to 12 while retaining key `ord-42`. Expected reasoning: the current-count partitioner may choose a different future partition, old records do not move, so lifetime order across the topic is not guaranteed (`03:48-55`). Verdict: PASS.
3. After `04`, crash after the external effect but before the offset commit. Expected reasoning: a new owner rereads the last committed offset and retries the effect (`04:25-41`). The note predicts the duplicate, but explaining the safe idempotency boundary needs an unstated premise. Verdict: FAIL for the remediation choice; cross-reference the local idempotency finding.
4. After `05`, use RF=3, ISR size 3, `min.insync.replicas=2`, `acks=all`. The note's “wait for that rule” wording supports the wrong answer (two acknowledgments), while Kafka requires all three current ISR acknowledgments. Verdict: FAIL; cross-reference the local acknowledgment-contract finding.
5. After `05`, let the ISR become empty while the controller still has an unfenced ELR on a new Kafka 4.3 cluster. The note provides no premise for predicting the safe ISR-then-ELR election order and instead makes ISR the only explained safe-leadership category (`05:15-26`). Verdict: FAIL; cross-reference the local stale safe-election finding.

## Executable-claim inventory

Environment: macOS workspace host; Docker client/server `29.6.2`; image `apache/kafka:4.3.1` pulled by digest `sha256:77e3df9054047a88b520d0cc46e16696d3b22022e1d580aeccd2632df6532837`; checked 2026-09-16. No external credentials or remote mutation were used.

### `01:10-15` — start broker and create topic

Claim: runnable/copyable setup.

Status: VERIFIED.

Command (exactly lines 11-15):

```bash
docker run --rm --name kafka-notes -p 9092:9092 -d apache/kafka:4.3.1
docker exec kafka-notes /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server localhost:9092 \
  --create --topic orders --partitions 1 --replication-factor 1
```

Observed: overall exit 0; detached container started, the admin client briefly logged connection-refused startup warnings, then printed `Created topic orders.` This agrees with the note's startup-failure diagnostic at lines 29-31 and did not prevent success.

### `01:19-27` — publish and consume one event

Claim: runnable end-to-end record path.

Status: VERIFIED.

Command (exactly lines 20-26):

```bash
printf '%s\n' '{"event_id":"evt-101","type":"order.created","order_id":"ord-42"}' | \
  docker exec -i kafka-notes /opt/kafka/bin/kafka-console-producer.sh \
    --bootstrap-server localhost:9092 --topic orders

docker exec kafka-notes /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic orders --from-beginning \
  --max-messages 1 --property print.partition=true --property print.offset=true
```

Observed: exit 0; `Partition:0 Offset:0 {"event_id":"evt-101","type":"order.created","order_id":"ord-42"}` and `Processed a total of 1 messages`. Kafka also printed the `--property` deprecation warning recorded in the local `FIX-MED` finding.

### `01:30` — startup diagnostic

Claim: conditional runnable diagnostic.

Status: NOT-RUN.

Command: `docker logs kafka-notes`.

Observed: the specified failure condition (“no broker is available”) did not persist; running the failure branch would not test its claimed cause. The setup output itself did show transient connection warnings before topic creation succeeded.

### `01:40-42` — replay with a new console consumer

Claim: runnable changed-condition verification using the consumer command at lines 24-26 again.

Status: VERIFIED.

Command (exactly lines 24-26, rerun after the first process exited):

```bash
docker exec kafka-notes /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic orders --from-beginning \
  --max-messages 1 --property print.partition=true --property print.offset=true
```

Observed: exit 0; the same partition 0, offset 0 JSON record was returned, followed by `Processed a total of 1 messages`; the deprecation warning repeated.

### `01:87` — cleanup and absence check

Claim: runnable cleanup with success signal.

Status: VERIFIED.

Command: exact documented commands `docker stop kafka-notes` and `docker ps`; additional audit confirmation: `docker ps -a --filter name='^/kafka-notes$' --format '{{.Names}} {{.Status}}'`.

Observed: stop exit 0; exact `docker ps` did not list `kafka-notes`; scoped all-container output was empty. Because the original run used `--rm`, no stopped container remained.

### `03:27-30` — cross-client placement fixture

Claim: integration verification procedure.

Status: NOT-RUN.

Command: n/a; the note does not name client languages, client versions, serializers, partitioners, topic partition count, or an inspection command.

Observed: This is a valid design instruction with an explicit expected equality/mismatch signal, but it is not reproducible exactly as displayed. Treat it as non-runnable prose unless a canonical client note supplies the composed fixture.

### `04:68-69` — assignment inspection and controlled restart

Claim: integration/failure verification procedure.

Status: NOT-RUN.

Command: n/a; no cluster topology, group members, workload/effect probe, inspection command, timeout, or “bounded handoff” threshold is supplied.

Observed: The conceptual success criterion is useful, but this block makes no exactly reproducible executable claim in the assigned environment.

### `05:58-60` — describe replication and stop a broker

Claim: integration/failure verification procedure.

Status: NOT-RUN.

Command: n/a; the assigned runnable setup is deliberately one broker/RF=1 and cannot perform the three-replica failover described here. No multi-broker fixture, exact describe/stop/read commands, or timing bounds are supplied.

Observed: Not run because reproducing it would require an unspecified multi-broker environment. This is not evidence the conceptual claim is false.

No executable claims occur in `fundamentals/README.md` or `02`; their diagrams, formula, compaction trace, and teach-back signal are conceptual artifacts rather than commands. Other diagrams in `03`–`05` are likewise explanatory traces, not runnable claims.

## Files, checks, sources, and unresolved items

Files read in full:

- `.agents/skills/note-reviewer/SKILL.md`
- all six required references: `how-we-write-notes.md`, `curriculum-research.md`, `learning-curve-and-explanation-audit.md`, `example-selection.md`, `coverage-and-execution-audit.md`, `audit-reports.md`
- delegation reference: `.agents/skills/note-reviewer/references/delegation.md`
- `infrastructure/kafka/README.md`
- all six assigned fundamentals Markdown files
- linked rollout owner `infrastructure/kafka/operations/05_configuration_and_topic_administration.md`

Checks run:

- `wc -l` for every assigned file (physical line counts reported above).
- Exact Docker setup, produce/consume, replay, cleanup, and `docker ps` checks described in the executable inventory.
- Searched the claimed operations owner for `group.protocol`, consumer protocol, and rebalance material; none occurs.
- Confirmed sampled local continuation/owner targets exist (`operations/README.md`, operations note 05, ecosystem share-groups note, application-design README and Python-client note).
- Checked version-sensitive claims against Apache Kafka primary documentation dated above.

Primary sources inspected (all checked 2026-09-16):

- Kafka 4.3 quickstart: <https://kafka.apache.org/quickstart/>
- Kafka 4.3 consumer rebalance protocol: <https://kafka.apache.org/43/operations/consumer-rebalance-protocol/>
- Kafka 4.3 producer configuration (`acks`): <https://kafka.apache.org/43/generated/producer_config.html>
- Kafka 4.3 topic configuration (`min.insync.replicas`, unclean election): <https://kafka.apache.org/43/configuration/topic-configs/>
- Kafka 4.3 Eligible Leader Replicas: <https://kafka.apache.org/43/operations/eligible-leader-replicas/>
- Kafka 4.0 release announcement: <https://kafka.apache.org/blog/2025/03/18/apache-kafka-4.0.0-release-announcement/>

Unresolved / collection-owner decisions:

- The local review treats Kafka 4.3 ELR as a stale safe-election defect in note 05 because that deep dive promises failure availability/durability; the collection owner still needs to decide where later operational configuration and diagnosis live.
- Decide whether the root exploration path intentionally omits replication note 05 despite the root/section outcomes.
- The unbounded integration checks in notes 03-05 were not converted into local defects unless they block the note's conceptual role; the global examples owner should keep their `NOT-RUN` statuses distinct from broken commands.
