# Curation Operator Flow Contract V1

This contract is the end-to-end smoke path for the human-operated curation loop.

It does not add a new product capability. It proves that the existing curation
surfaces compose coherently across consecutive recorded runs.

## Contract

The tested flow is:

```text
refresh-view
-> record run
-> operator overview
-> publication preview
-> explicit human confirm
-> publication checkpoint
-> next refresh-view
-> record next run
-> delta / change brief / publication coverage
-> explicit human confirm
-> complete coverage
-> empty next publishable view
```

The smoke test uses two fictional opportunities and two consecutive runs.

The first run exposes both opportunities as publishable. The operator records
a checkpoint for only one item. The overview must then show partial publication
coverage and the exact remaining uncheckpointed publishable ID.

The second run must suppress the already checkpointed item from the current
publishable set while leaving the other item publishable. Because publication
checkpoints are attached to a specific recorded run, the second run starts with
no checkpoint coverage of its own.

After the operator explicitly confirms the remaining item against the second
run, publication coverage becomes complete and the next daily view contains no
publishable opportunities.

## Evidence boundaries

The contract freezes these distinctions:

```text
RECORDED RUN != EXTERNAL PUBLICATION
PREVIEW != CONFIRMATION
CHECKPOINT != PROVIDER RECEIPT
UNCHECKPOINTED != UNPUBLISHED
DELTA != CAUSAL EXPLANATION
OVERVIEW != NEW EVIDENCE
OVERVIEW != ACTION
```

A publication checkpoint is a durable record of an explicit operator
confirmation inside Opportunity OS. It is not independent evidence that a
message exists on WhatsApp, email, or another external provider.

The absence of a checkpoint means only that Opportunity OS has no recorded
confirmation for that run/item pair.

## Human authority boundary

Every overview component remains read-only:

- no message is sent;
- no external provider is called;
- no opportunity is marked externally published by inference;
- no review, verification, or application state is advanced automatically;
- every `external_actions` collection remains empty.

The only state-changing publication step in this contract is the existing
explicit preview/confirm checkpoint path.

## Regression target

The contract should fail if a future change causes any of these regressions:

- a checkpoint silently leaks from one run into another run's coverage;
- an explicitly checkpointed item remains publishable in the next curation
  view when suppression should apply;
- the operator overview combines inconsistent run IDs;
- publication coverage stops exposing the exact remaining IDs;
- a composed read-only view acquires external action authority.

The executable regression is
`tests/test_curation_operator_flow_contract.py`.
