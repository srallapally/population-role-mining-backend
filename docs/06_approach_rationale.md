# Role Mining — Approach Rationale

This document explains why the pipeline is designed the way it is, specifically why user-similarity clustering was chosen over Association Rule Mining (ARM), where the approach excels, and where it falls short. It is intended for engineers and data scientists who want to understand the algorithmic trade-offs, not just the implementation.

---

## The Fundamental Question Determines the Answer

Role mining asks: **"which users belong together?"** That is a user-partitioning problem. The natural formulation is to start from users and cluster them directly.

The ARM-based approach answers a different question: **"among users who share certain identity attributes, which entitlements do they frequently hold together?"** The training pipeline reads actual user-entitlement assignments and identity attributes, then runs FPGrowth on the combined set. The antecedent of each rule is a combination of identity attribute values (job code, department, cost centre). The consequent is an entitlement ID. The rule states: "among users with attribute combination X, entitlement Y appears in N% of cases" — a frequency observation derived from real assignment data.

This is useful for understanding what access is common within attribute groups. It is a weaker foundation for governance, because it produces attribute-entitlement frequency associations — not role membership, not per-user deviation analysis, and not a comparison between what any individual user holds and what their peer group's pattern would suggest they should hold.

---

## ARM's Structural Weaknesses

**1. ARM requires a large population to produce reliable rules.**

FPGrowth requires statistically significant support frequencies to produce reliable rules. Minimum support is calculated as `floor(minGroup / population)`. A team of 30 people in a 10,000-person organisation has a support of 0.3% — near the floor of what is statistically meaningful. Smaller populations produce rules below minimum support thresholds and are effectively invisible to the algorithm.

User-similarity clustering operates on pairwise user comparisons within the analyst-defined population, which can be as small as `minGroupSize` (default 30). The computation does not require population-wide statistical significance.

**2. ARM observes frequencies but never computes per-user deltas.**

ARM reads actual assignments — it knows which users hold which entitlements. FPGrowth finds that, among users with attribute combination X, entitlement Y appears in N% of cases. What it never computes is: for any specific user who satisfies attribute combination X, how does their actual entitlement set compare to the frequent pattern? A user who holds the 5 entitlements that appear in the frequent pattern plus 50 accumulated extras satisfies the same rule antecedent as a cleanly provisioned peer. ARM records both as matching the rule. The 50 extras are visible in the raw assignment data but are never compared against the rule's pattern — the delta is never computed, and overprovisioning is never surfaced.

User-clustering computes this delta explicitly for every community member: the over-provisioning score is the fraction of a user's residual entitlements that fall outside the role-defining set, and the specific extra entitlements are listed by ID.

**3. ARM has no notion of role cohesion.**

ARM produces attribute-entitlement frequency rules, not role membership. There is no direct measure of how coherent the set of users who match a given rule antecedent actually is in terms of their access. Two users with the same job code who have very different entitlement profiles are treated identically by ARM — they both satisfy the same antecedent. User-clustering computes mean pairwise Jaccard within each detected community, producing a direct role quality score. ARM has no equivalent.

**4. ARM buries access drift in rule frequency.**

When users accumulate entitlements over time, their attribute profiles do not change — their job code and department stay the same. ARM continues to find that users with those attributes frequently hold the role-appropriate entitlements. The accumulated extras appear in the assignment data but are not part of any rule's consequent unless they are themselves frequent across the attribute group. If one user has 50 idiosyncratic extras, those extras do not reach the frequency threshold and are simply absent from the rule output. The pipeline cannot distinguish between a user who was cleanly provisioned yesterday and a user who has accumulated 50 extras over 10 years — both satisfy the same attribute-to-entitlement frequency patterns.

User-clustering surfaces access drift as an explicit, per-user, per-entitlement finding. The analyst knows exactly which users have excess access and exactly what that excess is.

**5. Universal entitlements dilute the attribute signal.**

In most populations, certain entitlements are held by nearly everyone regardless of their attribute values — VPN access, email, basic portal login. These appear as high-frequency consequents across many rule antecedents and add noise to the output without adding discriminating information.

The user-clustering pipeline strips universal entitlements in a dedicated step before any clustering runs. The residual matrix passed to community detection contains only the access that differentiates users by functional profile. This is a form of feature selection that the ARM training pipeline does not perform.

---

## Why User-Clustering Produces Better Roles

**Direct answer to the right question.** Clustering users directly produces role membership as a first-class output. Each community is a set of users, and the role is derived from what those users share. There is no translation step from frequency rules to roles.

**Cohesion is measurable.** Mean pairwise Jaccard within a community is a direct quality score for the role. A cohesion of 0.8 means community members share 80% of their combined residual access on average. This is interpretable and actionable — an analyst can decide whether a low-cohesion role is worth promoting.

**Outlier detection falls out naturally.** Once a community is defined, any member whose access deviates significantly from the community profile is an outlier. The deviation can be measured precisely and decomposed into under-provisioning (missing role entitlements) and over-provisioning (holding extra entitlements outside the role). ARM never computes this delta — it produces frequency observations, not per-user comparisons against a role baseline.

**Universal stripping is a critical enabler.** Without removing universal entitlements before clustering, every user looks similar to every other user because they all share the same dominant entitlements. The similarity signal is overwhelmed by noise. Stripping universals first means the clustering algorithm operates on the access that genuinely differentiates functional profiles.

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

The extra access exists because users accumulate entitlements over time. The pipeline groups these users together because they share a meaningful core — but they each bring their own accumulated extras with them. The over-provisioning scores are not artefacts — they are the primary governance finding.

**Why ARM does not avoid this problem.**

ARM reads the same assignment data and therefore sees the same entitlements. The difference is what it does with them. ARM computes frequency patterns — which entitlements appear together across users who share attribute values. It never computes the delta between what any individual user holds and what the frequent pattern for their attribute group would suggest. A user with 50 extra entitlements satisfies the same attribute-frequency rules as a cleanly provisioned peer. The extras may not reach the frequency threshold to appear as a rule consequent, so they are simply absent from the output. The overprovisioning is in the data; ARM's output structure has no place to put it.

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

For populations with many multi-role users or highly individualised access, neither approach works well. ARM would still produce attribute-entitlement frequency observations even where access is dirty, but those observations would not surface who is overprovisioned or how far any individual has drifted. User-clustering produces a high singleton rate and few communities. In these cases the singleton rate itself is a governance finding: the population does not have role-like structure, and access is too individualised to mine into managed roles without first cleaning up the access landscape.

A hybrid would be strongest: use user-clustering to find communities, then use entitlement prevalence analysis within each community to validate and refine the role definition. The two-tier entitlement system (role-defining vs common-not-universal) approximates this — it applies prevalence thresholds within each detected community rather than session-wide, which preserves the role signal for small communities that would be invisible to org-wide ARM training.

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

If an analyst filters by a specific attribute value — `JobCode = Physician Assistant` — all users in the session already share that attribute. Within that population, entitlement similarity is the right discriminator for finding sub-groups and surfacing access drift. The problem resurfaces when the analyst uses a broader filter (e.g. a whole department) where multiple job functions are mixed together.

**What this means for production.**

In the current POC, the analyst's population filter is the primary control for ensuring attribute homogeneity. Narrow, attribute-specific filters (a single job code in a single department) produce the most actionable output. Broad filters that mix multiple job functions will produce lower-confidence communities and higher singleton rates, not because the algorithm is failing, but because the input population contains multiple overlapping role profiles that entitlement similarity alone cannot cleanly separate.

This is the most significant algorithmic gap between the current implementation and a production-grade role mining system. It is a candidate for the next iteration after the current POC is validated.

---

## Review of the Production ARM Pipeline

The existing Ping IGA role mining implementation consists of two jobs. The training job (`train.py`) reads actual user-entitlement assignments and identity attributes, then runs FPGrowth on the combined dataset to produce association rules. The rules take the form: "among users with attribute combination X, entitlement Y appears in N% of cases." The mining job (`mine.py`) takes those pre-computed rules, filters them by confidence and frequency thresholds, groups them into candidate roles, and writes results to Elasticsearch.

The key structural point: ARM reads real assignment data — it knows which users hold which entitlements. The gap is not that it lacks access to the data. The gap is that it computes frequency observations across attribute groups but never computes the delta between what any individual user holds and what the frequent pattern for their group would suggest. That delta is the overprovisioning signal.

Several structural observations from reviewing the implementation:

**No population scoping.** There is no analyst-defined population filter — this is an org-wide batch job. Every rule that survives the threshold filters becomes a candidate role regardless of which population it applies to.

**No cohesion scoring.** The only quality signals are `conf_threshold` (rule confidence) and `freq_threshold` (rule support). These measure how frequently an attribute combination predicts an entitlement — not how coherent the set of users who match that combination actually is.

**No per-user delta analysis.** The pipeline builds `df_role_assignments` but never computes the difference between what each user holds and what their role's frequent pattern contains. A user with 50 extra entitlements is recorded as a role member identically to a cleanly provisioned peer. The extras are in the raw data; they are never extracted, compared, or surfaced.

**Access drift is structurally invisible.** Because the output is frequency observations across attribute groups, idiosyncratic extras that do not reach the frequency threshold simply do not appear in any rule consequent. They are present in `df_assignments` but are never compared against anything.

**Final role mapping is a deduplication heuristic.** `_map_mined_to_final` maps newly mined roles back to existing promoted roles using a distance score. This is necessary because FPGrowth produces different rule sets each run — there is no stable role identity across runs. The POC avoids this problem: roles have stable UUIDs and can be re-run on the same population without reconciling against prior runs.

**Candidate deduplication is fragile.** `_remove_existing_candidates_from_mined` deduplicates by matching on `entitlements` and `justifications` columns. If either changes by even one token between runs, a previously promoted candidate is not recognised and a duplicate is written.

---

## Does ARM Do a Better Job Reducing Overprovisioned Access?

No. ARM reads the same assignment data as the POC but never computes per-user deltas against a role pattern. The overprovisioning is present in the data; ARM's output structure has no place to represent it.

The POC detects and quantifies overprovisioning explicitly. For every community member, `overProvisioningScore` is computed — the fraction of the user's residual entitlements that fall outside the role-defining set — and the specific extra entitlements are listed by ID. An analyst reviewing a role can see immediately: this user holds 50 entitlements beyond the role definition, here is the list, here is the percentage. That is directly actionable in an access review or certification campaign.

**Where ARM has a genuine advantage: population scale.**

ARM's training runs org-wide and produces rules that reflect access patterns across the entire organisation. For large, stable populations with consistent provisioning, this produces well-supported rules with high frequency confidence. The POC is scoped to analyst-defined populations (up to 10,000 users) and requires the analyst to define the population correctly. ARM requires no analyst judgment about population selection — it mines the whole org automatically.

**Where ARM's advantage collapses: dirty access landscapes.**

ARM's frequency observations are only as good as the assignment data they are derived from. In organisations with significant access accumulation, the training data contains years of drift. Frequency patterns derived from that data reflect what users have accumulated, not what their roles actually require. The apparent authority of ARM's rules is an artefact of the historical data, not evidence of clean role boundaries.

| Capability | ARM pipeline | POC |
|---|---|---|
| Reads actual assignment data | Yes | Yes |
| Computes per-user delta vs role pattern | No | Yes — overProvisioningScore per user |
| Detects underprovisioning | No | Yes — underProvisioningScore per user |
| Role cohesion score | No | Yes — mean pairwise Jaccard on members |
| Handles access drift | Frequency observations absorb it | Surfaces it explicitly per user |
| Population scoping | No — org-wide only | Yes — analyst-defined |
| Works on small populations | No — needs statistical support | Yes — down to minGroupSize |
| Stable role identity across runs | Yes — via distance mapping heuristic | Not yet — production gap |

ARM does not reduce overprovisioned access — the delta between what users hold and what their role requires is never computed. The POC produces that delta explicitly for every role member, which is what an access review campaign needs as input.

---

## Clarification on the Two-Step Approach and the Singleton Gap

The pipeline's design is deliberately two-step:

1. **Identify a population** — the analyst selects users by identity attributes (`JobCode`, `Department`, `CostCenter`, etc.). Everyone in the resulting population shares those attribute values by definition. This step is attribute-driven.

2. **Within that population, identify clusters based on access** — the pipeline computes pairwise Jaccard similarity on residual entitlements and runs Leiden community detection. This step is entitlement-driven.

This separation is intentional and correct. Step 1 defines the peer group the analyst believes should share a role. Step 2 discovers what access patterns actually exist within that peer group, and who has drifted away from them.

**Where the gap actually is.**

Within a well-scoped population — say, `JobCode = Physician Assistant AND Department = Ambulatory Informatics` — two users are organisationally identical. But if one has clean access and one has accumulated 50 extra entitlements over years of role changes, their residual Jaccard similarity may fall below `similarityThreshold`. They end up in different communities, or one becomes a singleton.

The pipeline correctly identifies that their access is dissimilar. But the access dissimilarity is not a signal that they belong in different roles — it is the governance problem to be solved. The heavily drifted user's access needs review, not a separate role.

**What happens to singletons today.**

The pipeline reports `singletonCount` on the session document. That is the extent of singleton analysis. The singleton disappears from the role output entirely. No role is produced for them, no over-provisioning score is computed, and no analyst is told which role they most closely resemble or how far their access has drifted from their peer group. This is the actual gap in the current implementation.

**The correct fix: singleton-to-role affinity analysis.**

For every singleton, the pipeline should identify which detected community that user is most similar to (highest mean Jaccard against community members), and compute their over-provisioning and under-provisioning scores against that community's role definition. The singleton is not a role member — they are an outlier against the closest role. That is still a governance finding, and in many cases it is the most important one.

A singleton who is a Physician Assistant in Ambulatory Informatics but has 60 extra entitlements is not a mystery — they are a Physician Assistant whose access has drifted severely. The pipeline should say so explicitly: "closest role: Community 0 (Physician Assistant baseline), over-provisioning score: 0.82, extra entitlements: [list]." That finding goes directly into an access review campaign.

This reframes singletons from a failure of community detection into a governance output in their own right. A high singleton count is not just a signal to tune the similarity threshold — it is a list of users whose access has drifted so far from any peer group that they warrant individual access review, regardless of whether a community-based role can be defined for them.

**The correct approach: tight communities plus singleton affinity analysis.**

Attempting to prevent singletons by pulling drifted users into communities via hybrid similarity or attribute-seeded partitioning produces looser communities with lower confidence scores — role quality degrades to accommodate the access drift. The correct approach is the opposite: let the similarity threshold do its job and produce tight, high-confidence communities, then treat singletons as a separate governance output via affinity analysis rather than forcing them into communities where they do not belong.

Tight roles plus explicit singleton affinity analysis produces better governance outcomes than loose roles that absorb drifted users.
