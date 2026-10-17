# Renewal Calendar Specification

## Purpose
Surface upcoming subscription renewals with lead-time alerts and cancel-by dates so a CFO can act before the next charge.

## Requirements

### Requirement: Build a renewal calendar from recurring charges
The system MUST attach a renewal calendar to each analysis. Each entry MUST include the renew-on date, days until renewal, a cadence-based lead time, a cancel-by date, and whether the renewal falls inside that lead time. Dates and amounts MUST be computed in Python.

#### Scenario: Monthly renewal inside the lead window
- **WHEN** a monthly subscription's next expected charge is within 14 days of the statement end
- **THEN** the calendar entry marks the renewal as inside the lead time and sets cancel-by to the day before the renewal date

### Requirement: Alert on price changes inside the lead window
When a renewal is inside its lead time and the charge amount has risen, the calendar alert MUST include both the days remaining and the price-change percent computed from the observed amounts.

#### Scenario: Price rise is stated as a percent
- **WHEN** a subscription's latest amount is 25 percent above its first observed amount and the next charge is inside the lead time
- **THEN** the alert text includes the days until renewal and a 25 percent price increase

### Requirement: Detect a single annual charge
The system MUST treat a single charge whose description marks it as annual or yearly as a yearly renewal, with a 30-day lead time, without treating ordinary one-off spend as a subscription.

#### Scenario: Annual keyword becomes a yearly renewal
- **WHEN** a statement contains one charge described as an annual plan and no second charge for that merchant
- **THEN** the calendar lists that merchant as a yearly renewal with a 30-day lead time
