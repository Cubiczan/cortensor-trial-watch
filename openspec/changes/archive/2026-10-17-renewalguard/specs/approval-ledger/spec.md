# Spec Delta

## Purpose
Give a fractional CFO a monthly file of proposed cancellations, renewals, and renegotiations that never executes a vendor action.

## ADDED Requirements

### Requirement: Export the monthly proposal ledger
The system MUST export a chosen month's proposals as CSV and as JSON. Each row MUST include the merchant, the action (cancel, renew, or renegotiate), the reason, the deadline, the monthly cost, the status, and an executed flag.

#### Scenario: Month export writes both formats
- **WHEN** a human asks for a month that contains proposals
- **THEN** the system writes a CSV file and a JSON file for that month and omits proposals from other months

### Requirement: Never execute a vendor action
The system MUST NOT cancel, renew, or pay a vendor. New proposals MUST be stored with status pending_human. The executed flag MUST be false on every exported row. The guardrail MUST be stated in the export and in the project README.

#### Scenario: Queued cancellation stays pending
- **WHEN** the agent queues a cancellation for a merchant the analyzer flagged
- **THEN** the stored proposal has status pending_human and executed false

#### Scenario: Hallucinated merchant is refused
- **WHEN** a cancellation is requested for a merchant the analyzer did not flag
- **THEN** the system rejects the request and writes no proposal

### Requirement: Propose renewals separately from cancellations
The system MUST be able to queue a renewal or renegotiation proposal for a known recurring merchant that is inside the renewal lead time and is not already a cancellation candidate. That proposal MUST also stay pending for a human.

#### Scenario: In-window renewal is only a proposal
- **WHEN** a recurring merchant is inside its lead time and was not flagged for cancellation
- **THEN** a renewal or renegotiation proposal can be queued with status pending_human and executed false
