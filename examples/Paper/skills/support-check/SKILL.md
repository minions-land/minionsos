---
name: support-check
description: "Run a lightweight confirmation that important claims are actually supported"
---

# /support-check — Lightweight Claim Support Check

Run a lightweight support confirmation pass before stronger packaging decisions.

## Goal

Catch claim-evidence mismatches early, without turning into a full reviewer.

## Check

- whether the claim is backed by current evidence
- whether a figure or table actually supports the stated wording
- whether the phrasing is stronger than the evidence allows
- whether missing support should trigger a request to other agents

## Do

- stay practical and lightweight
- focus on packaging safety
- flag risk clearly

## Do not do

- do not become a full review workflow
- do not invent criticism without evidence

## Output

Return a support-check note:
- claim
- support status
- risk level
- recommended wording or support request