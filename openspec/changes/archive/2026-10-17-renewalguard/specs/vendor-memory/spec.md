# Spec Delta

## Purpose
Remember vendors and subscriptions across runs on local disk so a later audit respects what a human already decided.

## ADDED Requirements

### Requirement: Persist vendors across runs
The system MUST store each detected subscription vendor in local storage that survives a new process, including merchant identity, cadence, amounts, flags, and the last time it was seen.

#### Scenario: Second run sees the first run's vendor
- **WHEN** an audit detects a recurring merchant and a later audit runs against the same state directory
- **THEN** the stored vendor record for that merchant is still present and includes the latest amounts and flags

### Requirement: Respect a rejected cancellation
The system MUST NOT queue another cancellation proposal for a merchant whose cancellation a human has already rejected.

#### Scenario: Rejected cancellation is not re-queued
- **WHEN** a human has recorded a rejected cancellation for a merchant and a later audit tries to queue that cancellation again
- **THEN** the queue call does not add a new pending proposal and reports that the cancellation was already rejected

### Requirement: Record human decisions without executing them
The system MUST record a human approval or rejection of a proposal as a decision only. Recording a decision MUST NOT cancel, renew, or pay the vendor.

#### Scenario: Approval updates the proposal and does not execute it
- **WHEN** a human records an approval for a pending proposal
- **THEN** the proposal status becomes approved and the record still states that nothing was executed
