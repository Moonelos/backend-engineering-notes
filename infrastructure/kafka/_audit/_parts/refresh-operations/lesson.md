# LQ-O01 — Security policy as an observed lifecycle
Files: operations/01_security_and_multitenancy.md
LESSON: FAIL
Reader: Programmer after the application and reliability paths, learning to apply and verify Kafka client security; generic distributed-security expertise is not assumed.
Evidence: Development map: TLS/SASL/ACL separation at 7–9 is defined; client identity, SCRAM and CA at 15–37 have explained artifacts; ACL principal/action/resource at 39–63 has a useful decision carrier but an overstated group-binding claim; rotation at 17 is prescribed without its credential states; trust boundaries at 65–66 are stated; positive/negative success at 68–70 is expected rather than assembled; hard isolation at 81–82 is a recommendation without a contrasting tenant scenario.
Reasoning burden: The reader can inspect the intended ACL mapping, but must invent how the client, broker, admin inputs and observations form one verified policy, then how that policy survives credential replacement. The isolation boundary also needs one explained threat/constraint rather than another list of security nouns.
Visual support: Use a principal→request→resource→decision table, with topic fetch and group join as separate rows. A before/during/after credential table can show which identity is valid and authorized without displaying secret values.
Structure: REWRITE; preserve the safe client and ACL artifacts, develop their operational sequence and mark later isolation/rotation responsibilities explicitly.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: coverage.audit.md, Security and multitenancy, owns this incomplete operational teaching; operations.audit.md O-ACL owns the distinct false conditional-permission claim. No duplicate lesson severity.
Proposed sequence: A named unauthorized action and its consequence → server/identity assumptions → verified client connection → resource grants → allowed and denied requests with observed outcomes → rotate one identity while preserving least privilege → decide whether shared resources meet the tenant's isolation requirement.
Content mapping: Keep 19–57 and interpret them through one walkthrough; develop 15–17 into a later rotation stage; attach 59–70 to actual policy observations; retain 77–82 as a worked isolation comparison. Detailed platform provisioning may be a named prerequisite, but its required inputs must be bounded here.
Example development: orders-api writes orders while a stolen orders-api credential attempts payments; billing-worker reads orders but cannot join fraud-v1. Introduce orders-api-next with equivalent narrow grants, verify its canary, move the service, revoke old identity and prove old requests fail. Then compare a tenant requiring independent keys or failure domains with one needing only per-resource authorization.
Rewrite sample: A successful TLS connection tells orders-api that its encrypted connection reached a trusted broker. It does not answer whether orders-api should write payment events. Test the next decision separately: publish to orders.events.v1 using the service identity, then attempt payments.events.v1 using that same identity. The second request must fail authorization. For billing, topic reads and group operations are two different checks: permission to fetch orders does not itself grant permission to join fraud-v1. Keeping those observations separate tells us which boundary failed when a negative test unexpectedly succeeds.
Acceptance task: Given a working encrypted connection and successful order publish but an unexpectedly successful payment publish, identify the failed boundary and the next evidence to inspect. During rotation, explain why revoking the old identity before a successful new-identity canary creates an avoidable outage.

# LQ-O02 — A measured capacity envelope
Files: operations/02_capacity_planning_and_performance.md
LESSON: PASS
Reader: Programmer who knows partitions, groups and replication, choosing an initial load-test envelope rather than a universal capacity formula.
Evidence: Development map: bytes×retention×replicas at 7–9 supplies a concrete storage baseline; measured per-partition limits at 13–26 produce competing steady-state and recovery partition counts; live ingress plus backlog draining is explained rather than hidden in the formula; network, headroom and disk-utilization calculations at 28–32 continue the same workload; broker-loss and skew invalidations at 34–37 explain when the estimate stops applying; tuning at 43–45 is a short optional overview, not an unsupported command to pick particular settings; success and hot-key limits at 50–66 close the decision loop.
Reasoning burden: The reader can follow why five partitions satisfy steady state but not the recovery deadline, and which measurements could invalidate fifteen. This is a genuine developed decision lesson despite being short.
Visual support: The measured-input table and successive arithmetic sufficiently expose the bottleneck change; a broker diagram would not improve the central reasoning.
Structure: KEEP; preserve the continuous envelope and explicit load-test assumptions.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: The note teaches the promised estimate and its limits. It does not claim that the arithmetic replaces a failure/load test.

# LQ-O03 — From an alert to an explained incident decision
Files: operations/03_observability_and_incident_response.md
LESSON: FAIL
Reader: Engineer with Kafka fundamentals, building alerts and choosing a justified first response rather than merely copying metric names.
Evidence: Development map: possible lag causes at 7–9 and triage tree at 15–21 are enumerated; alert YAML at 32–62 is a concrete carrier; conjunctive lag/age decision and missing-series suppression are explained at 64–68; replica/disk delay is explained at 70–73; injected-handler success at 75–77 is an unperformed procedure without setup; coordinator/controller detection appears only at 9/20; 86–89 gives sensible aggregation/paging boundaries. There is no complete incident with observed values and a changed condition selecting another response.
Reasoning burden: A novice can restate that lag has many causes but must invent the diagnostic episode that distinguishes a handler bottleneck, skew, rebalance churn and control-plane failure. The collection promises implemented detection as well as broad awareness.
Visual support: Add a timed observation table: partition, arrival/processing rates, age, lag, membership, ISR and hypothesis. Change one condition and interpret why the next action changes. The existing triage tree is a route through questions, not evidence answering them.
Structure: REWRITE; organize around one bounded incident and its contrasting diagnosis, keeping the existing alert artifacts as tools in that story.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: coverage.audit.md, Observability and incident response, owns insufficient diagnosis/verification depth and missing control-plane branches. The editorial plan below develops that same defect without another severity.
Proposed sequence: Define the event freshness objective → observe one breached partition → compare arrival and handler rates → evaluate the sample alert → inject and verify a bounded failure → recover and observe clearance → contrast a missing metric and a coordinator/controller incident.
Content mapping: Keep 27–73 but place the YAML after the first observed case; turn 7–21 from a checklist into a developed sequence; implement the stated absent-series branch; retain 84–89 as derived boundaries; add the promised coordinator/controller branch here rather than assuming the replication chapter supplies a runbook.
Example development: billing P2 receives 100 records/s but completes 60 while other partitions are healthy. Keep arrivals constant and show growing backlog/age. Then make processing recover while repeated membership changes interrupt work; explain why adding workers alone is no longer the first hypothesis. Finally remove the age series and show that a joined alert stops producing a result instead of becoming healthy.
Rewrite sample: P2 receives 100 records each second and billing finishes only 60. Its backlog therefore grows by about 40 records per second while the oldest unfinished event becomes older. The alert identifies a consequence, not yet its cause. Compare handler latency and dependency errors before adding consumers: if one database call now takes five times longer, another worker may only add more pressure to the same dependency. If handler time is unchanged but assignments repeatedly move, investigate membership and polling instead. The same rising lag can lead to different actions because the intermediate observations differ.
Acceptance task: Present two partitions with equal lag but different age, arrival rate and membership history; require a justified first investigation and an observation that would falsify it. Then remove the age series and explain why separate missing-data detection is necessary.

# LQ-O04 — Upgrade state and regional recovery are different transitions
Files: operations/04_deployment_upgrades_and_disaster_recovery.md
LESSON: FAIL
Reader: Engineer planning the cluster lifecycle; no prior knowledge of Kafka binary/feature-version transitions is assumed.
Evidence: Development map: RTO/RPO are named at 7–9 and later demonstrated at 30–46; provider/customer ownership at 15–16 is a usable bounded division; upgrade paths/features at 18–20 are only a checklist; asynchronous regional copies, saved progress and repeated effects at 26–46 form a developed trace; failback at 48–51 states a bounded coordination sequence; restored ancillary state at 65–67 is explained as a failure risk. The good recovery trace cannot supply the absent upgrade model advertised in the section README.
Reasoning burden: The learner must infer the distinct binary version, finalized feature state, mixed-version interval and rollback boundary. Adding “check release notes” cannot teach those relationships; an upgrade is not the same state transition as regional failover.
Visual support: Retain the regional timeline; add a separate before/during/after upgrade state table showing node binaries, finalized feature levels, health gates and which rollback remains permitted. Keep regional source/destination record coordinates explicitly labeled rather than implying that every mirroring tool preserves numeric offsets.
Structure: REWRITE; retain the regional lesson and develop a clearly separate upgrade sequence within the same lifecycle chapter or an explicitly named dedicated continuation.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: coverage.audit.md, Upgrades and regional disaster recovery, owns the missing upgrade capability; no second severity for the same missing teaching.
Proposed sequence: Who owns each lifecycle action → common distinction between stored data and control state → supported version-specific upgrade stages and abort gates → independent regional loss/replay scenario → controlled failback and verified recovery objectives.
Content mapping: Keep 24–59 as the strong regional unit; expand 18–20 into a real staged upgrade unit instead of padding each checklist noun; retain 63–69 as the consequence of missing recovery inputs. A split is optional only if the upgrade procedure becomes a separately usable operational responsibility.
Example development: In a pinned supported version transition, record binaries and feature state before restart, after one node, after all nodes and before finalization. Introduce a health regression during the mixed-version stage and explain the stop/rollback decision. Only after that compare the existing eu-primary/eu-replica regional story; do not reuse RPO as an upgrade validation metric.
Rewrite sample: Restarting a broker with a new binary and enabling the cluster's new features are different steps. During the rolling restart, some nodes may run the old binary while others run the new one, so the supported transition must keep them interoperable. Record the finalized feature state before beginning. After replacing one node, check the defined replication and client-health gates before replacing the next. If those gates fail, stop the rollout; do not advance feature levels in the hope that this repairs the symptoms. Finalization changes the state the cluster has agreed to use and can close downgrade options, so its exact version-specific boundary must be explicit in the runbook.
Acceptance task: Given all nodes on the new binary but old finalized feature levels and a newly failing client, explain why automatic finalization is not the next troubleshooting step. Identify the evidence and release-specific restrictions needed before rollback, then distinguish this case from missing regional records after failover.

# LQ-O05 — Reversible configuration versus state-moving operations
Files: operations/05_configuration_and_topic_administration.md
LESSON: FAIL
Reader: Operator who can authenticate an admin client and must change application-owned resources with defensible verification and rollback evidence.
Evidence: Development map: creation at 7–26 has commands and expected policy; precedence at 32–49 is developed through 7-day override versus 30-day inheritance; retention change at 55–67 supplies explicit forward and rollback values; update-mode distinction at 69–72 is a bounded source check; expansion, reassignment, quotas and deletion at 78–83 are one-line behaviors with distinct consequences; drift/canary evidence at 85–90 is prescribed; reassignment throttling at 96–97 adds another action without a plan artifact; incompatible-topic migration at 102–104 names dual publication/backfill and cutover without their state transitions. The final scope is substantially wider than a retention lookup.
Reasoning burden: The well-developed override example can misleadingly make the later operations look like similar scalar changes. The reader has to invent which operations move data, preserve old placement, create a second history, or destroy recovery inputs—and how success/rollback evidence differs.
Visual support: Keep the override before/after trace. Add an operation-state table distinguishing scalar effective values, replica placement, keyed routing and deleted namespaces. For reassignment, show old/new replica sets and copy progress; for migration, show old/new topic writers/readers and the cutover checkpoint.
Structure: REWRITE; preserve the retention lesson as the entry case, then deliberately contrast state-moving/destructive operations with their own compact worked procedures or real named owners.
Summary: 0 critical, 0 high, 0 med, 0 low

RELATED: coverage.audit.md, Topic and configuration administration, owns incomplete administration procedures. This lesson plan is the editorial repair for that same finding, not a duplicate severity.
Proposed sequence: Observe current effective state → change and restore a scalar setting → contrast an irreversible placement change → trace reassignment to completion → test a bounded quota → explain deletion/recovery preconditions → choose a new-topic migration when compatibility requires it.
Content mapping: Keep 5–72; turn 76–104 into contrasted operations rather than four bullets and two warnings. Maintain the existing canonical administration owner; add subprocedures here or explicitly identify developed destinations. Preserve warnings about internal topics and irreversible actions beside the relevant procedure.
Example development: Retain seven→fourteen→seven days as the reversible case. Change partition count and show that removing an override cannot return old keyed placement. Move one replica from broker 2 to broker 4 and show the catch-up state before completion. Apply a quota to one canary identity and observe its throttle before broad rollout. For deletion, identify the separate restore source before acting.
Rewrite sample: Restoring `retention.ms=604800000` puts the old seven-day policy back because we recorded that explicit value. Adding partitions is a different kind of change. The topic now has more ordered logs, and producers may place future keys differently; there is no symmetric “remove those partitions” rollback. The review therefore needs more than an old scalar value. It needs the affected key-placement assumption, the consumer compatibility check and a migration plan if the old ordering domain must be preserved. A successful admin response proves the command was accepted, not that the application's ordering contract survived.
Acceptance task: Given a successful retention increase and a successful partition expansion, identify why their rollback evidence differs. For an in-progress replica reassignment, distinguish command acceptance from completion and explain why a throttle below incoming traffic can prevent catch-up.

# LQ-O00 — Operations navigation
Files: operations/README.md
LESSON: n/a
Reader: Engineer selecting the operations route and ownership boundary.
Evidence: Lines 9–20 map outcomes and the managed-provider stop/continuation point; they do not themselves teach procedures.
Reasoning burden: Navigation is direct; linked chapters must earn the listed outcomes.
Visual support: The role/outcome table is sufficient for this index.
Structure: KEEP; retain the learning promise while repairing its owners.
Summary: 0 critical, 0 high, 0 med, 0 low

NO-ACTION: No index-only defect requires a new finding.
