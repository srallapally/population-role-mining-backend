# Role Mining — Overview

## What Problem Are We Solving?

Every enterprise accumulates an access problem over time. People join teams, get entitlements, move roles, and rarely have access removed. After a few years, nobody has a clean picture of what a given job function actually needs. When an auditor asks "what should a Clinical Educator have access to?", the honest answer is "we don't know — let's look at what they actually have."

**Role mining** is the process of working backwards from what people currently have to discover the access patterns that define functional roles. The output is a set of candidate roles — clusters of entitlements that tend to travel together across similar users — that a governance analyst can review, name, trim, and promote into managed roles.

This system does role mining on analyst-defined populations. The analyst picks a group of users (e.g. "all Epic Link staff in Ambulatory Informatics"), sets some parameters, and the system discovers what roles exist within that group.

---

## Why Not Use the Existing Approach?

The previous approach used **Association Rule Mining (ARM)** — a standard technique that finds frequently co-occurring entitlements and proposes them as candidate roles.

ARM has two fundamental problems at this scale:

**1. It requires large datasets to produce useful results.** ARM finds patterns by counting how often entitlement combinations appear together. With a mid-size customer population, the counts are too low to produce statistically meaningful rules. Most combinations appear only once or twice, which ARM interprets as noise and discards.

**2. It produces too much output.** ARM enumerates every frequent combination above a support threshold. A population with hundreds of entitlements produces thousands of rules. Analysts cannot make sense of thousands of rules — they need roles, not rules.

The new approach addresses both problems. It operates on analyst-scoped populations of any size, and its output is bounded — at most 25 candidate roles per session by default.

---

## What Does This System Do?

The system takes a filtered population of users and their current entitlement assignments, and produces two kinds of output:

**Birthright roles** — entitlements held by nearly everyone in the population. These represent the baseline access that comes with membership in the group. For a population of Epic Link staff, this might be Active Directory access, VPN, and the Epic production environment — things everyone has regardless of what else they do.

**Candidate roles** — clusters of users with similar non-baseline access. After stripping the universal entitlements, users who share similar residual access patterns are grouped together. Each group becomes a candidate role representing a functional profile within the population.

Both outputs are enriched with enough metadata for an analyst to understand why each role was produced — which entitlements define it, how similar the members are to each other, and what parameters produced the result.

---

## What the System Does Not Do

- It does not make access change recommendations
- It does not flag policy violations
- It does not decompose users who hold multiple functional roles — each user is assigned to at most one candidate role
- It does not persist results across server restarts (POC limitation — in-memory store)
- It does not mine the entire organisation at once — the analyst always scopes a population first

---

## How the System Is Structured

The system is a Python REST API. An analyst interacts with it by:

1. Creating a session with a population filter and optional parameter overrides
2. Starting the pipeline, which runs asynchronously in a background thread
3. Polling the session until it reaches `complete` or `failed` status
4. Retrieving the produced roles

The pipeline itself reads from three CSV files (identities, entitlements, assignments) and writes results to an in-memory store. A Vue frontend (under development) will provide a UI over the same REST API.

---

## Key Terms

| Term | Meaning |
|---|---|
| **Session** | One run of the pipeline against a specific population with specific parameters |
| **Population** | The set of users selected by the analyst's filter criteria |
| **Birthright role** | A role containing entitlements held by ≥90% of the population (universal entitlements) |
| **Candidate role** | A role discovered by clustering users with similar residual access |
| **Residual access** | A user's entitlements after universal entitlements are removed |
| **Singleton** | A user whose residual access is too unique to be placed in any community |
| **Community** | A group of users with similar residual access, detected by the Leiden algorithm |
| **Entitlement** | A single permission, group membership, or role assignment in a target system |
