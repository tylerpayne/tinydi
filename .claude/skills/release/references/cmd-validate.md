# `uvr workflow validate`

Check an existing `release.yml` against the expected schema.

```bash
uvr workflow validate
```

Reports whether the workflow is valid, invalid, or has warnings.

- **Errors**: required jobs are missing from the workflow.
- **Warnings**: the workflow file differs from the template. Run `uvr workflow init --upgrade` to reconcile.
- **Custom jobs** are accepted without validation — the workflow model allows extra jobs.
