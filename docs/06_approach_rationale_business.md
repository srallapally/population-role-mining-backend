# Role Mining — How It Works and Why

This document explains what the role mining tool does, why it was built the way it was, and what the results mean for governance analysts. It assumes no knowledge of data science or algorithms.

---

## The Problem We Are Solving

In any large organisation, people accumulate access over time. Someone joins a team and gets provisioned with the access their manager requests. They move to a different team and get more access. They cover for a colleague and get temporary access that is never revoked. After a few years, their access profile is a patchwork of everything they have ever been given — much of which they no longer need.

Multiply this across thousands of employees and hundreds of applications, and you have an access landscape where nobody has a clear picture of what a given job function actually requires. When you ask "what should a Physician Assistant in Ambulatory Informatics have access to?", there is no clean answer — only a distribution of what they actually have, which includes years of accumulated extras.

Role mining is the process of looking at what people actually have and working backwards to discover what the roles should look like. The output is not a finished role catalog. It is a set of candidate roles that a governance analyst reviews, names, trims, and promotes into managed roles — along with a list of who has more access than their role requires.

---

## How the Tool Works: Two Steps

**Step 1 — You define the population.**

You select a group of users by their identity attributes: job code, department, cost centre, location. The tool mines roles within that group only. There is no "mine the whole organisation" option — and this is intentional. Organisation-wide mining produces noise. Population-scoped mining produces actionable candidates.

For example: "all users with JobCode = Physician Assistant in the Ambulatory Informatics department." The tool will analyse only those users and tell you what roles exist within that group.

**Step 2 — The tool finds clusters based on access.**

Within your selected population, the tool looks at which users have similar access to each other — specifically, which non-universal entitlements they share. Users who share a lot of the same access are grouped together. Each group becomes a candidate role.

The key word is "non-universal." Before grouping users, the tool first identifies entitlements that nearly everyone in the population holds — things like VPN access, email, basic portal login. These are stripped out before the clustering runs. They are handled separately as "birthright" roles. The clustering then operates only on the access that differentiates one functional group from another.

---

## What "Similar Access" Means

Two users are considered similar based on how much of their access they share, measured as a fraction of their combined access.

If User A holds 10 entitlements and User B holds 10 entitlements, and they share 8 of them, their similarity score is 8 out of 12 (the 8 shared plus the 2 each holds exclusively) — approximately 67%. If the similarity threshold is set to 30%, these two users would be connected and potentially grouped together.

This similarity score is computed only on residual access — after birthright entitlements have been removed. Two users who both have VPN and email but nothing else in common have a residual similarity of zero. The birthright layer has already accounted for that shared access.

---

## Two Kinds of Output

**Birthright roles** — entitlements held by a very high fraction of the population (default: 90% or more). These are the baseline access that is effectively universal for this job function. Examples in a clinical setting: domain login, MFA enrollment, basic EHR view access. The tool groups birthright entitlements that are held by the same set of users into a single birthright role, and separates ones held by different subsets into distinct birthright roles.

**Candidate roles** — discovered by grouping users who share similar non-universal access. Each candidate role represents a functional profile within the population: a set of entitlements that a coherent subgroup holds in common. These are the roles that distinguish, for example, a Physician Assistant who orders medications from one who only views records.

---

## Role Confidence

Every candidate role carries a confidence score — High, Medium, or Low. This tells you how tight the group is.

A **High confidence** role means the members share most of their access with each other. The role boundary is clean and the membership is coherent. You can trust that these users genuinely form a functional peer group.

A **Medium or Low confidence** role means the members are connected but diverge significantly in their individual access profiles. They share a core, but each member brings their own accumulated extras. The role core is probably real, but the membership is noisy.

Low confidence is not a failure — it is a signal. It tells you either to tighten the similarity threshold (which will produce smaller, cleaner groups) or that this population has significant access drift and needs cleanup before clean roles can emerge.

---

## The Most Important Output: Who Has More Than They Should

For every role, the tool identifies members whose access differs significantly from the role definition. Two findings per person:

**Extra access** — entitlements the user holds that are outside the role definition. These are candidates for access revocation. The tool lists the specific entitlements and gives a percentage: "58% of this user's non-birthright access is outside the role definition."

**Missing access** — entitlements in the role definition that this user does not hold. These may indicate incomplete provisioning or that the user belongs in a different role.

These are the governance findings that drive the access review. The candidate roles tell you what the roles should look like. The extra and missing access findings tell you who needs remediation and exactly what needs to change.

---

## What Singletons Mean

Some users cannot be grouped with anyone else — their access is too different from every other user in the population. These are called singletons, and a high singleton count is one of the most important findings the tool produces.

Singletons are not a failure of the tool. They are users whose access has drifted so far from their peer group that the algorithm cannot place them in a community. In governance terms, a singleton in a population of Physician Assistants is a Physician Assistant whose access looks nothing like any other Physician Assistant. That is exactly the user who needs individual access review.

The current tool reports how many singletons exist. A planned enhancement will go further: for each singleton, it will identify which candidate role they most closely resemble and compute how far their access has drifted from that role's definition. A singleton who most closely matches the "Physician Assistant — Medication Ordering" role but holds 60 extra entitlements on top of it is a specific, actionable finding — not just a number in a count.

---

## Why Not Just Group People by Job Code?

Grouping by job code tells you what roles should exist according to your org chart. The tool discovers what roles do exist according to your access data. These are different questions with different answers, and both are useful.

In a clean, well-provisioned organisation, the answers converge: everyone with the same job code has roughly the same access, and the tool's communities map cleanly to job codes. In this case the tool validates your provisioning model and confirms that roles are being applied consistently.

In a real organisation with access drift, the answers diverge: people with the same job code have very different access profiles because of accumulated extras, inconsistent provisioning, or role changes without deprovisioning. In this case the tool surfaces the divergence — it shows you the access that the job code community actually shares, who has drifted from it, and by how much. That is the governance finding you cannot get from the org chart alone.

The analyst's population filter bridges the two questions. By filtering to a specific job code and department, you define the peer group you believe should share a role, and the tool discovers what that peer group actually has in common and who has drifted from it.

---

## Why Not Use the Previous Role Mining Approach?

The previous approach (Association Rule Mining, or ARM) also reads actual user-entitlement assignments — it has access to the same underlying data. What it does with that data is different, and that difference is what matters for governance.

ARM looks at the data and asks: "among users who share certain job attributes, which entitlements do they frequently hold together?" It finds patterns — for example, "users with JobCode = Physician Assistant and Department = Ambulatory Informatics frequently hold entitlement X." That is a useful observation about what is common within a group.

What ARM never asks is: "for this specific user, how does what they actually hold compare to what their peer group's pattern says is typical?" That comparison — the gap between what someone has and what their role requires — is the overprovisioning finding. ARM produces the group pattern but never computes the individual gap.

The new tool computes that gap explicitly for every role member. It reads the same assignment data, identifies the role's defining entitlements, and then for each member calculates exactly how much extra access they hold and lists the specific entitlements. That is what makes the output actionable in an access review — not just "here is what this group tends to have" but "here is exactly what this specific person holds beyond their role definition."

**A concrete example.** Suppose ARM finds that Physician Assistants in Ambulatory Informatics frequently hold entitlements A, B, C, D, and E. User 0259383 holds A, B, C, D, E, and 50 others. ARM records User 0259383 as matching the Physician Assistant pattern — correct, they do hold all five. The 50 extras are not part of any frequent pattern for this group, so they simply do not appear in ARM's output. No analyst is told they exist.

The new tool groups User 0259383 with their peers, identifies A through E as role-defining, and then explicitly computes: this user holds 50 entitlements outside the role definition, representing 56% of their non-birthright access. Here is the list. That finding goes directly into a certification campaign.

**Three additional limitations of ARM:**

ARM requires a large organisation to produce reliable patterns — a team of 30 people in a 10,000-person organisation may be too small to appear in ARM's output at all. The new tool is designed for analyst-scoped populations and works on groups as small as 30 users.

ARM mines the whole organisation at once with no analyst control over which population is analysed. The new tool requires the analyst to define the population — which produces dramatically better output because the peer group is well-defined before the mining begins.

ARM produces no role confidence score — there is no measure of how coherent the users who match a given pattern actually are. The new tool computes a confidence score for every candidate role, telling you how tightly the members' access aligns.

---

## How to Get the Best Results

**Use narrow, specific population filters.** A filter of `JobCode = Physician Assistant AND Department = Ambulatory Informatics` gives the tool a coherent peer group to work with. A filter of `Department = Hospital Operations` mixes dozens of job functions and produces lower-quality output.

**Start with the default similarity threshold (30%) to establish a baseline.** Then look at the confidence scores and over-provisioning rates. If most roles are Medium or Low confidence with high extra-access rates, raise the threshold to 50% and re-run.

**Treat singletons as a governance finding, not a failure.** A high singleton count means a significant fraction of the population has access that looks nothing like any peer group. These users need individual access review regardless of whether the tool can place them in a role.

**Use the over-provisioning output as access review input.** The specific entitlements flagged as extra access for each role member are the starting point for a certification campaign. The tool has already done the work of identifying what each person holds beyond their role definition — the reviewer's job is to confirm or revoke.

**Re-run after access cleanup.** The tool produces better roles on cleaner access data. After a certification campaign removes accumulated extras, a second mining run on the same population will produce tighter communities, higher confidence scores, and fewer singletons. This is the intended cycle: mine → review → clean up → mine again.
