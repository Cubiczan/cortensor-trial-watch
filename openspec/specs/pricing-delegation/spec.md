# Pricing Delegation Specification

## Purpose
Check current vendor pricing with a second OpenMinion agent before a renewal or renegotiation proposal, using deterministic price evidence.

## Requirements

### Requirement: Compare billed price with a local price fixture
The pricing check MUST compare the billed monthly amount with the local price fixture and return a recommendation of renew, renegotiate, or review. The percent difference MUST be computed in Python. A missing fixture MUST yield review rather than a guessed price.

#### Scenario: Billed amount above list price
- **WHEN** the billed monthly amount is more than 10 percent above the fixture list price
- **THEN** the recommendation is renegotiate and the result includes the computed percent difference

#### Scenario: Unknown vendor
- **WHEN** the merchant is not in the price fixture
- **THEN** the recommendation is review and no list price is invented

### Requirement: Delegate the check to a second OpenMinion agent
During a live audit, the pricing check MUST run as a second OpenMinion agent created with the SDK subagent helper, with its own instructions and the price-check tool. The parent MUST keep the Python-computed evidence as the numeric result. The sub-agent MUST NOT cancel, renew, or pay anything.

#### Scenario: Parent delegates to the pricing sub-agent
- **WHEN** a parent agent is active and a pricing check is requested
- **THEN** the SDK subagent helper is invoked with the pricing-check name and the price-check tool, and the returned numbers match the Python price comparison
