# Support Check Reports

This directory holds generated support-check reports that are useful to keep in
the repository but are not user-facing documentation.

Regenerate matcher contract reports with:

```bash
python3 app/support_checks/audit_matcher_contract_json_authority.py --write
python3 app/support_checks/audit_matcher_contract_toml_sources.py \
  --output-dir app/languages/sv/matcher_contracts/sources \
  --allow-checkout-output \
  --write-report
```
