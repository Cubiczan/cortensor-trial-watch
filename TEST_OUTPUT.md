# Test output

Captured 2026-10-17 on Python 3.12.3. RenewalGuard tests use the stock `openminion==0.1.4` install and do not call a model. The bug #1 exposure test is run against a patched copy of the 0.1.4 sources (see `upstream/`). It is not part of this repo's `pytest` collection.

## `python3 -m pytest -v` (this repo)

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.7.0 -- /usr/bin/python3
cachedir: .pytest_cache
rootdir: /workspace
plugins: platformdirs-4.13.3, anyio-4.15.1
collecting ... collected 11 items

test_analyzer.py::test_detects_trial_and_stale PASSED                    [  9%]
test_analyzer.py::test_chase_style_card_export PASSED                    [ 18%]
test_analyzer.py::test_debit_credit_columns_and_quarterly PASSED         [ 27%]
test_analyzer.py::test_queue_guard_rejects_hallucinated_merchant_and_dedupes PASSED [ 36%]
test_renewalguard.py::test_renewal_calendar_alerts_price_rise_inside_lead_time PASSED [ 45%]
test_renewalguard.py::test_single_annual_charge_is_yearly_and_one_offs_are_not PASSED [ 54%]
test_renewalguard.py::test_vendor_memory_persists_and_rejected_cancellation_is_not_requeued PASSED [ 63%]
test_renewalguard.py::test_price_fixture_recommendations PASSED          [ 72%]
test_renewalguard.py::test_pricing_delegation_uses_openminion_subagent PASSED [ 81%]
test_renewalguard.py::test_direct_fixture_when_no_parent_agent PASSED    [ 90%]
test_renewalguard.py::test_renewal_proposal_and_monthly_ledger PASSED    [100%]

============================== 11 passed in 1.98s ==============================
```

## Bug #1 exposure test on the patched OpenMinion 0.1.4 tree

```text
============================= test session starts ==============================
platform linux -- Python 3.12.3, pytest-9.1.1, pluggy-1.7.0 -- /usr/bin/python3
cachedir: .pytest_cache
rootdir: /tmp/om-patched/tests/api
plugins: platformdirs-4.13.3, anyio-4.15.1
collecting ... collected 1 item

../tmp/om-patched/tests/api/test_decorated_tool_exposure.py::test_plain_decorated_tool_is_exposed_for_the_run_only PASSED [100%]

============================== 1 passed in 2.07s ===============================
```

The same test against stock 0.1.4 failed, as expected: `AssertionError: assert 'lookup_order' == 'plugin.user.lookup_order'`.
