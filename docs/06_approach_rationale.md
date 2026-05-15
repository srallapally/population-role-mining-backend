# Role Mining — Approach Rationale

This document explains why the pipeline is designed the way it is, specifically why user-similarity clustering was chosen over Association Rule Mining (ARM), where the approach excels, and where it falls short. It is intended for engineers and data scientists who want to understand the algorithmic trade-offs, not just the implementation.

---

## The Fundamental Question Determines the Answer

Role mining asks: **"which users belong together?"** That is a user-partitioning problem. The natural formulation is to start from users and cluster them directly.

ARM answers a different question: **"which entitlements co-occur?"** That is useful for finding access patterns, but it does not directly tell you who belongs in each role or how coherent the membership is. ARM produces rules — "users who have A and B often also have C" — not roles. Translating rules into roles requires significant post-processing that is fragile and opaque.

Starting from the right question produces cleaner answers.

---

## ARM's Structural Weaknesses

**1. ARM scales exponentially with entitlement count.**

ARM enumerates combinations. With hundreds of entitlements post noise-filter, the combinatorial space is enormous. ARM addresses this by raising the minimum support threshold, which kills rare-but-legitimate combinations. A team of 30 people in a 10,000-person population has a support of 0.3% — ARM needs an extremely low threshold to find it, which also floods the output with spurious rules.

User-similarity clustering operates on pairwise user comparisons. At 10,000 users that is 50 million pairs — large but tractable via sparse matrix multiplication. The computation does not explode with entitlement count.

**2. ARM conflates co-occurrence with role membership.**

A set of 5 entitlements that frequently co-occur might be held by 3 different user groups for 3 different reasons. ARM proposes one role containing all 5 entitlements. User-clustering finds the 3 communities and discovers that each holds a slightly different subset — producing 3 roles that match how access is actually used.

**3. ARM has no notion of cohesion.**

ARM can tell you that a combination of entitlements is frequent. It cannot tell you that User X has 14 extra entitlements nobody else in their peer group holds, or that User Y is missing 3 entitlements that 95% of their peers have. User-clustering computes per-user deviation from the detected role profile directly, producing the under-provisioning and over-provisioning scores that governance analysts actually need.

**4. ARM buries access drift rather than surfacing it.**

In populations where users have accumulated entitlements over time, ARM silently absorbs the noise. A user with 5 core Data Analyst entitlements and 50 accumulated extras contributes to the support count of every itemset containing those 50 entitlements. ARM sees all 55 entitlements as signal. The result is that individual access accumulation inflates the support of entitlement combinations that are not real roles — they are artefacts of one person's access history. ARM produces spurious rules from this noise and has no mechanism to distinguish "this combination appears because 30 analysts all have it" from "this combination appears because one analyst accumulated it over 10 years."

User-clustering surfaces the same underlying reality — access drift exists — but as an explicit, per-user, per-entitlement finding. Every community member's deviation from the role profile is measured, decomposed into under-provisioning and over-provisioning, and reported with the specific entitlements involved. The analyst knows exactly which users have excess access and exactly what that excess is. ARM produces no equivalent signal: the dirty access inflates rule support, increases rule count, and makes output harder to interpret, with no indication of which rules are genuine role patterns and which are noise from accumulated individual access.

**5. ARM does not handle the universal entitlement problem.**

In most populations, a handful of entitlements are held by nearly everyone — VPN, email, basic portal access. ARM includes these in every frequent itemset, producing rules like "email AND VPN AND SalesforceAdmin." The universal entitlements add no discriminating information but inflate every rule and dominate the similarity signal.

The user-clustering pipeline strips universal entitlements in a dedicated step before any clustering runs. The residual matrix passed to community detection contains only the access that differentiates users. This is a form of feature selection that ARM does not perform.

---

## Why User-Clustering Produces Better Roles

**Direct answer to the right question.** Clustering users directly produces role membership as a first-class output. Each community is a set of users, and the role is derived from what those users share. There is no translation step.

**Cohesion is measurable.** Mean pairwise Jaccard within a community is a direct quality score for the role. A cohesion of 0.8 means community members share 80% of their combined residual access on average. This is interpretable and actionable — an analyst can decide whether a low-cohesion role is worth promoting.

**Outlier detection falls out naturally.** Once a community is defined, any member whose access deviates significantly from the community profile is an outlier. The deviation can be measured precisely and decomposed into under-provisioning (missing role entitlements) and over-provisioning (holding extra entitlements outside the role). ARM has no equivalent — it produces patterns, not memberships, so there is no baseline to deviate from.

**Universal stripping is a critical enabler.** Without removing universal entitlements before clustering, every user looks similar to every other user because they all share the same dominant entitlements. The similarity signal is overwhelmed by noise. Stripping universals first means the clustering algorithm operates on the access that genuinely differentiates functional profiles. This step is what makes the community detection meaningful.

---

## Where User-Clustering Falls Short

**The Jaccard penalty on large entitlement sets.**

Jaccard similarity is sensitive to entitlement set size. A user who holds all 5 core entitlements of a "Data Analyst" role plus 50 entitlements from other functional roles has Jaccard ≈ 0.09 with pure Data Analysts (`5/55`), even though they fully satisfy the role. The algorithm treats them as dissimilar because of the union denominator.

This means the pipeline discovers roles for users whose access is dominated by a single functional profile. Users who span multiple functional roles will either cluster with whichever role they overlap most, appear as singletons, or be flagged as outliers. The pipeline does not decompose multi-role users.

**High singleton rates in heterogeneous populations.**

In populations with highly individualised access — like Epic Link staff, who are configured per-site and per-application — most users do not share enough residual access with anyone else to form communities. A 71% singleton rate (observed in the Ambulatory Informatics / Epic Link run) means the pipeline found structure for only 29% of the population. This is a real governance signal — the population genuinely lacks role-like structure — but it limits how much actionable output the pipeline can produce.

**Single community membership per user.**

Leiden assigns each user to exactly one community. A user whose access genuinely spans two functional roles can only belong to one candidate role. This is inherent to single-membership community detection, not a fixable bug.

---

## Real-World Observation: Roles With Excess Member Access

When running the pipeline against real enterprise identity data, a consistent pattern emerges: the majority of members within detected candidate roles carry significant extra access — residual entitlements that are outside the role's defining set. In one observed run on a population of 358 identities, a detected community of 201 members showed 50–80% of members flagged as over-provisioned, with individual members holding 20–60 extra entitlements beyond the 20 role-defining ones.

**Why this happens.**

This is not a pipeline defect. It is a direct reflection of the access landscape. The pipeline works correctly:

1. Birthright entitlements (held by ≥ 90% of the population) are stripped before clustering. The clustering operates only on residual access.
2. Within the residual, Leiden finds communities — groups of users who are more similar to each other than to the rest of the population.
3. Within each community, the role-defining entitlements are those held by ≥ 80% of community members. Everything else held by community members is extra access.

The extra access exists because users accumulate entitlements over time. When someone changes teams, takes on additional responsibilities, or covers for a colleague, they are granted access that is never revoked. Over years, individuals build up access profiles that are a superset of any single role. The pipeline's similarity metric (Jaccard) groups these users together because they share a meaningful core — but they each bring their own accumulated extras with them.

The result is large, medium-confidence communities where the role core is real but the membership is noisy. The over-provisioning scores are not artefacts — they are the primary governance finding. These are exactly the users whose access needs review.

**Why ARM does not avoid this problem.**

Access drift affects ARM too — it just manifests differently. ARM has no membership concept, so it cannot flag individual users as over-provisioned. Instead, the accumulated extras inflate the support counts of spurious entitlement combinations, producing additional rules that look like real patterns but are artefacts of individual access histories. The analyst receives more rules, not a cleaner signal. There is no way to distinguish a rule backed by 30 analysts who all need the same access from a rule backed by one analyst who accumulated access over 10 years. The problem is present in both approaches; user-clustering makes it visible and actionable, ARM absorbs it silently into rule frequencies.

**Why the similarity threshold matters.**

At the default threshold of 30% Jaccard similarity, two users need only share 30% of their residual entitlements to be connected by an edge in the similarity graph. In a population with access drift, 30% overlap is easy to achieve even between users with meaningfully different job functions. The result is a large, loosely connected graph where Leiden finds broad communities.

Raising the threshold to 50–60% forces edges only between users who share the majority of their residual access. This breaks large loose communities into smaller, tighter ones with higher confidence scores and less per-member extra access. The trade-off is more singletons — users whose access is too individualised to cluster at all. A high singleton count at an elevated threshold is itself a governance signal: these users' access has drifted so far from any peer group that they cannot be placed into a managed role without first cleaning up their access profile.

**How to interpret the results.**

When reviewing pipeline output on a population with significant access drift:

- **The role-defining entitlements** (≥ coverageThreshold prevalence within the community) represent the genuine functional access this group requires. These are candidates for a managed role's entitlement set.
- **The over-provisioning flags** identify members whose individual access exceeds the role definition. These are candidates for access review and certification — the pipeline has surfaced the specific extra entitlements each member holds.
- **The under-provisioning flags** identify members who do not hold all role-defining entitlements. These may indicate incomplete provisioning or that the user genuinely belongs in a different role.
- **The community confidence score** (mean pairwise Jaccard) indicates how homogeneous the community is. A Medium or Low confidence score in a large community is a signal that the similarity threshold should be raised to break the community into tighter subgroups, or that the population itself needs access cleanup before clean roles can emerge.

**Resolution: threshold tuning.**

The primary lever for tighter roles in populations with access drift is the Access Similarity threshold in the pipeline settings. The recommended approach:

1. Run at the default threshold (30%) to establish a baseline. Examine the confidence scores and over-provisioning rates.
2. If most roles show Medium or Low confidence with high over-provisioning rates, raise the threshold to 50% and re-run. Observe whether communities tighten and confidence scores improve.
3. If singleton counts become very high at 50%, the population has significant access drift. The governance action is to use the over-provisioning reports to clean up access before re-mining, not to lower the threshold.
4. A threshold of 50–60% is typically appropriate for healthcare and enterprise IT populations where role boundaries are well-defined but access accumulation is common.

The pipeline correctly identifies a dirty access landscape. The appropriate response is to treat the over-provisioning output as access review input, clean up the access, and re-run the pipeline on the cleaned population. Lowering the similarity threshold to force communities at the expense of role quality defeats the purpose of the exercise.

---

## The Honest Assessment

For clean, well-scoped populations where most users have a single dominant functional profile, user-clustering produces significantly better roles than ARM — more coherent membership, directly interpretable quality scores, and natural outlier detection.

For populations with many multi-role users or highly individualised access, neither approach works well. ARM would still surface frequent entitlement patterns even if it cannot identify membership, whereas user-clustering produces a high singleton rate and few communities. In these cases the singleton rate itself is a governance finding: the population does not have role-like structure, and access is too individualised to mine into managed roles without first cleaning up the access landscape.

A hybrid would be strongest: use user-clustering to find communities, then use entitlement co-occurrence analysis within each community to validate and refine the role definition. The two-tier entitlement system (role-defining vs common-not-universal) approximates this — it applies prevalence thresholds within each detected community rather than session-wide, which preserves the role signal for small communities that would be invisible to session-wide ARM.

---

## One Algorithmic Correction vs the Original Spec

The original specification described birthright clustering using connected components on a thresholded co-occurrence graph. The POC implements complete-linkage agglomerative clustering instead.

Connected components allow transitivity: entitlement A groups with entitlement C via B, even when `J(holders(A), holders(C))` is below the threshold. This produces over-merged birthright roles and understated `memberCount` values, since the intersection of holder sets across a transitively-merged cluster is smaller than the pairwise thresholds would suggest.

Complete-linkage enforces that every pair within a cluster meets the threshold — not just adjacent pairs. This is the correct semantic for "these entitlements travel together" and produces birthright roles with accurate membership counts. The original spec should be updated to reflect this correction.

---

## What Similarity and Community Mean in This Pipeline

The document uses "similarity" and "community" throughout without grounding them in the actual computation. This section provides that grounding.

**Similarity is a number between 0 and 1 computed from entitlement overlap.**

For any two users A and B, similarity is defined as Jaccard similarity on their entitlement sets:

```
J(A, B) = |A ∩ B| / |A ∪ B|
```

The numerator is the number of entitlements both users hold. The denominator is the total number of distinct entitlements held by either user. A score of 1.0 means both users hold exactly the same entitlements. A score of 0.0 means they share nothing. A score of 0.5 means half of their combined entitlement set is held by both.

This is computed on the **residual** entitlement set — after birthright entitlements (held by ≥ `universalThreshold` of the population) have been stripped. Similarity therefore measures how alike two users are in their non-universal, functionally-differentiating access. Two users who both hold VPN and email but nothing else in common have a residual similarity of 0.0 — the universal access they share has already been accounted for separately in the birthright layer.

**A community is a group of users where internal similarity is higher than would be expected by chance.**

The pipeline builds a graph: each user is a node, and an edge is drawn between two users if their Jaccard similarity meets or exceeds `similarityThreshold` (default 0.30). Users with no edges above the threshold become singletons — they are not placed in any community.

The Leiden algorithm partitions this graph into communities by maximising modularity — a measure of how much more densely connected the nodes within a community are compared to what a random graph with the same degree distribution would produce. A community in the modularity sense is not simply any cluster of connected nodes; it is a subgraph where the internal edge density is meaningfully higher than the baseline. This is what separates a genuine functional peer group from a coincidental overlap.

In practical terms: a community is a set of users who each share at least `similarityThreshold` residual access similarity with at least one other member of the group, and whose collective internal similarity is higher than their similarity to users outside the group. The role produced from that community — specifically the entitlements held by ≥ `coverageThreshold` of its members — is the access profile that distinguishes this group from the rest of the population.

**What this means for interpreting results.**

A high-confidence role (mean pairwise Jaccard ≥ 0.7) means community members share most of their residual access with each other — the role boundary is tight and the membership is coherent. A low-confidence role means members are connected through a chain of pairwise similarities but diverge significantly in their individual access profiles — the community is real in the graph-theoretic sense but the role boundary is loose. In the latter case, raising `similarityThreshold` will either tighten the community into a more coherent subgroup or reveal that the users do not form a genuine role at all.

---

## A Missing Dimension: Identity Attributes Are Not Part of Similarity

The pipeline defines similarity purely on entitlement overlap. Two users with identical department, job code, location, and cost center are not considered similar unless their residual entitlement sets also overlap above the similarity threshold. If they happen to have divergent access profiles — because one was provisioned years ago and accumulated extras, or because provisioning was inconsistent — they will have low Jaccard similarity and may not be connected by an edge at all. They could end up in different communities, or as singletons, despite being organisationally identical.

**Why the pipeline ignores attributes.**

The design choice was deliberate: the pipeline is trying to discover what access people actually have in common, not what access they should have in common based on their job function. Attribute-based grouping tells you what roles *should* exist according to your org structure. Entitlement-based similarity tells you what roles *do* exist according to your access data. The intent was to surface the latter — actual access patterns — rather than confirm the former.

**The problem with that choice.**

In a clean, well-provisioned org, entitlement similarity and attribute similarity are highly correlated. All users with the same job code have roughly the same access, so entitlement similarity and attribute grouping converge on the same answer.

In a real enterprise with access drift — which is the typical case — they diverge. Users with the same job code may have very different residual entitlement sets because of accumulated extras, inconsistent provisioning, or role changes without deprovisioning. The pipeline sees them as dissimilar and places them in different communities or makes them singletons. But from a governance perspective, they are the same role — they just have dirty access.

This means the pipeline can fail to discover roles that organisationally exist, precisely in the populations where governance action is most needed.

**The population filter partially compensates.**

If an analyst filters by a specific attribute value — `JobCode = Physician Assistant` — all users in the session already share that attribute. Within that population, entitlement similarity is the right discriminator for finding sub-groups and surfacing access drift. The problem resurfaces when the analyst uses a broader filter (e.g. a whole department) where multiple job functions are mixed together. In that case, users who share a job code may be scattered across different communities or classified as singletons because their entitlement sets have diverged, even though they are organisationally the same peer group.

**Two approaches that would address this.**

*Option 1 — Hybrid similarity.* Compute similarity as a weighted combination of entitlement Jaccard and attribute Jaccard (one-hot encoded attribute values, Jaccard over attribute-value pairs). A user who shares job code, department, and location with another user gets a similarity boost even if their entitlement sets have diverged due to access drift. The `similarityThreshold` parameter then operates on this blended score, allowing the algorithm to group users who are organisationally similar even when their access profiles have drifted apart.

*Option 2 — Attribute-seeded communities.* Group users by attribute values first (exact match on analyst-selected attributes), then run entitlement similarity analysis within each attribute group. This guarantees that users with the same job function are always considered together, and the entitlement analysis within the group surfaces who is correctly provisioned versus who has drifted. This is closer to how a governance analyst thinks: "show me all the Physician Assistants in Ambulatory Informatics and tell me what access they share."

Option 2 is more interpretable and maps directly to how analysts already think about role design. Option 1 is more powerful for cases where attribute values do not cleanly delineate functional roles — for example, when job code granularity is coarse or inconsistent across business units.

**What this means for production.**

In the current POC, the analyst's population filter is the primary control for ensuring attribute homogeneity. Narrow, attribute-specific filters (a single job code in a single department) produce the most actionable output. Broad filters that mix multiple job functions will produce lower-confidence communities and higher singleton rates, not because the algorithm is failing, but because the input population contains multiple overlapping role profiles that entitlement similarity alone cannot cleanly separate.

This is the most significant algorithmic gap between the current implementation and a production-grade role mining system. It is a candidate for the next iteration after the current POC is validated.

---

## Review of the Production ARM Pipeline

The existing Ping IGA role mining implementation (`mine.py`) takes pre-computed association rules as input — it does not run ARM itself. The actual Apriori or FP-Growth computation happens upstream in a separate training job. This pipeline takes the rule output, filters it by confidence and frequency thresholds, mines candidate roles from the surviving rules, and writes results to Elasticsearch via Spark on Dataproc.

Several structural observations from reviewing the implementation:

**Rules are the input, not entitlements.** `source.prepare_rules` filters `df_rules` by `conf_threshold` and `freq_threshold`. The pipeline never sees raw user-entitlement assignments for role discovery — only pre-computed rules. All ARM limitations (spurious rules from access drift, universal entitlement inflation, no membership baseline) are baked in before this code runs. The quality of the output is entirely determined by the upstream training job.

**No population scoping.** `df_enriched_user` and `df_assignments` are passed in but used only for building index outputs, not for filtering the mining population. There is no analyst-defined population filter — this is an org-wide batch job. Every rule that survives the threshold filters becomes a candidate role regardless of which population it applies to.

**No cohesion scoring.** There is no equivalent of mean pairwise Jaccard on role members. The only quality signals are `conf_threshold` (rule confidence) and `freq_threshold` (rule support). These are rule-level metrics, not role-level membership quality metrics.

**No outlier detection.** The pipeline builds `df_role_assignments` but computes no over-provisioning or under-provisioning scores. A user with 5 role-defining entitlements and 50 accumulated extras is recorded as a role member. The 50 extras are invisible to the pipeline — they do not affect role assignment, they do not appear in any output, and no analyst is told they exist.

**Access drift is invisible.** `df_assignments` is used to build the users index only. There is no step that compares a user's full assignment set against the roles they are placed in. The overprovisioning problem exists in the underlying data; the ARM pipeline simply has no mechanism to see it.

**Final role mapping is a deduplication heuristic.** `_map_mined_to_final` maps newly mined roles back to existing promoted roles using a distance score. This is necessary because ARM produces different rule sets each run — there is no stable role identity across runs. The user-clustering approach avoids this problem: roles have stable UUIDs and can be re-run on the same population without reconciling against prior runs.

**Candidate deduplication is fragile.** `_remove_existing_candidates_from_mined` deduplicates by matching on `entitlements` and `justifications` columns. If the entitlement set or justification string changes by even one token between runs, a previously promoted candidate is not recognised as the same role and a duplicate is written.

---

## Does ARM Do a Better Job Reducing Overprovisioned Access?

No. It does a worse job, for a specific structural reason: ARM cannot detect overprovisioning at all.

The ARM pipeline assigns users to roles based on rule membership. But it never asks what else a user holds that the role does not require. There is no step in the pipeline that compares a user's full entitlement set against their assigned role's entitlement set. The result is that a user with 5 role-defining entitlements and 50 accumulated extras is simply recorded as a role member. The 50 extras are invisible.

The POC detects and quantifies overprovisioning explicitly. For every community member, `overProvisioningScore` is computed — the fraction of the user's residual entitlements that fall outside the role-defining set — and the specific extra entitlements are listed by ID. An analyst reviewing a role can see immediately: this user holds 50 entitlements beyond the role definition, here is the list, here is the percentage. That is directly actionable in an access review or certification campaign.

**Where ARM arguably performs better: role boundary precision.**

ARM produces roles from entitlement co-occurrence patterns across the full org. If a set of entitlements genuinely travels together across thousands of users, ARM finds it cleanly. The role boundary is tight by construction — a role is exactly the frequent itemset, nothing more.

The POC's roles are community boundaries, not entitlement boundaries. A community is a group of users who are similar to each other. The role-defining entitlements are derived from whoever is in the community, which means if the community is loose (low confidence score), the role boundary is loose too.

This advantage is conditional. It only holds when the access landscape is clean (no significant drift), the population is large enough for ARM's support thresholds to be meaningful, and universal entitlements have been pre-filtered (the ARM pipeline does not do this). In a real enterprise with access accumulation — the typical case — ARM's apparent precision is an illusion. The role looks tight because it is defined by entitlement co-occurrence, but the users assigned to it carry significant extra access that the pipeline never surfaces. The overprovisioning exists; ARM just does not see it.

| Capability | ARM pipeline | POC |
|---|---|---|
| Detects overprovisioning | No | Yes — per user, per entitlement |
| Detects underprovisioning | No | Yes — per user, per entitlement |
| Role boundary precision | High in clean landscapes | Depends on similarity threshold |
| Handles access drift | Absorbs it silently | Surfaces it explicitly |
| Population scoping | No — org-wide only | Yes — analyst-defined |
| Confidence / cohesion score | No | Yes — mean pairwise Jaccard |
| Works on small populations | No — needs statistical support | Yes — down to minGroupSize |
| Stable role identity across runs | Yes — via distance mapping heuristic | Not yet — production gap |

ARM does not reduce overprovisioned access — it is blind to it. The POC is the first step toward actually addressing it, because it produces the specific findings (which users, which entitlements, what scores) that an access review campaign needs as input.

---

## Clarification on the Two-Step Approach and the Singleton Gap

The pipeline's design is deliberately two-step:

1. **Identify a population** — the analyst selects users by identity attributes (`JobCode`, `Department`, `CostCenter`, etc.). Everyone in the resulting population shares those attribute values by definition. This step is attribute-driven.

2. **Within that population, identify clusters based on access** — the pipeline computes pairwise Jaccard similarity on residual entitlements and runs Leiden community detection. This step is entitlement-driven.

This separation is intentional and correct. Step 1 defines the peer group the analyst believes should share a role. Step 2 discovers what access patterns actually exist within that peer group, and who has drifted away from them.

**Where the gap actually is.**

The earlier discussion about attribute similarity and hybrid similarity was identifying a specific failure mode within step 2, not a flaw in the overall approach.

Within a well-scoped population — say, `JobCode = Physician Assistant AND Department = Ambulatory Informatics` — two users are organisationally identical. But if one has clean access and one has accumulated 50 extra entitlements over years of role changes, their residual Jaccard similarity may fall below `similarityThreshold`. They have no edge in the similarity graph. They end up in different communities, or one becomes a singleton.

The pipeline correctly identifies that their access is dissimilar. But the access dissimilarity is not a signal that they belong in different roles — it is the governance problem to be solved. The heavily drifted user's access needs review, not a separate role.

**What happens to singletons today.**

The pipeline reports `singletonCount` on the session document. That is the extent of singleton analysis. The singleton disappears from the role output entirely. No role is produced for them, no over-provisioning score is computed, and no analyst is told which role they most closely resemble or how far their access has drifted from their peer group.

This is the actual gap in the current implementation. It is not that the two-step approach is wrong — it is that singletons are currently a dead end.

**The correct fix: singleton-to-role affinity analysis.**

For every singleton, the pipeline should identify which detected community that user is most similar to (highest mean Jaccard against community members), and compute their over-provisioning and under-provisioning scores against that community's role definition. The singleton is not a role member — they are an outlier against the closest role. That is still a governance finding, and in many cases it is the most important one.

A singleton who is a Physician Assistant in Ambulatory Informatics but has 60 extra entitlements is not a mystery — they are a Physician Assistant whose access has drifted severely. The pipeline should say so explicitly: "closest role: Community 0 (Physician Assistant baseline), over-provisioning score: 0.82, extra entitlements: [list]." That finding goes directly into an access review campaign.

This reframes singletons from a failure of community detection into a governance output in their own right. A high singleton count is not just a signal to tune the similarity threshold — it is a list of users whose access has drifted so far from any peer group that they warrant individual access review, regardless of whether a community-based role can be defined for them.

**Implication for the Options discussed earlier.**

The hybrid similarity (Option 1) and attribute-seeded communities (Option 2) approaches discussed earlier were solving the wrong version of the problem. They were trying to prevent singletons by pulling drifted users into communities. That produces looser communities with lower confidence scores — the role quality degrades to accommodate the access drift.

The correct approach is the opposite: let the similarity threshold do its job and produce tight, high-confidence communities, then treat singletons as a separate governance output via affinity analysis rather than forcing them into communities where they do not belong. Tight roles plus explicit singleton affinity analysis produces better governance outcomes than loose roles that absorb drifted users.

Option 3 — intra-community entitlement co-occurrence analysis to validate and refine role definitions — remains valid as an enhancement to role definition quality once communities are formed. It is independent of the singleton question.