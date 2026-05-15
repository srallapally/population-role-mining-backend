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

**4. ARM does not handle the universal entitlement problem.**

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

## The Honest Assessment

For clean, well-scoped populations where most users have a single dominant functional profile, user-clustering produces significantly better roles than ARM — more coherent membership, directly interpretable quality scores, and natural outlier detection.

For populations with many multi-role users or highly individualised access, neither approach works well. ARM would still surface frequent entitlement patterns even if it cannot identify membership, whereas user-clustering produces a high singleton rate and few communities. In these cases the singleton rate itself is a governance finding: the population does not have role-like structure, and access is too individualised to mine into managed roles without first cleaning up the access landscape.

A hybrid would be strongest: use user-clustering to find communities, then use entitlement co-occurrence analysis within each community to validate and refine the role definition. The two-tier entitlement system (role-defining vs common-not-universal) approximates this — it applies prevalence thresholds within each detected community rather than session-wide, which preserves the role signal for small communities that would be invisible to session-wide ARM.

---

## One Algorithmic Correction vs the Original Spec

The original specification described birthright clustering using connected components on a thresholded co-occurrence graph. The POC implements complete-linkage agglomerative clustering instead.

Connected components allow transitivity: entitlement A groups with entitlement C via B, even when `J(holders(A), holders(C))` is below the threshold. This produces over-merged birthright roles and understated `memberCount` values, since the intersection of holder sets across a transitively-merged cluster is smaller than the pairwise thresholds would suggest.

Complete-linkage enforces that every pair within a cluster meets the threshold — not just adjacent pairs. This is the correct semantic for "these entitlements travel together" and produces birthright roles with accurate membership counts. The original spec should be updated to reflect this correction.
