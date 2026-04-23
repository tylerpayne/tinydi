# `uvr download`

Download platform-compatible wheels from GitHub releases or CI run artifacts without installing them.

```bash
uvr download PKG --repo ORG/REPO              # latest release
uvr download PKG --repo ORG/REPO --release-tag PKG/v1.2.3  # specific version
uvr download PKG --repo ORG/REPO --run-id ID  # from CI artifacts
```

## Flags

| Flag | Description |
|------|-------------|
| `-o`, `--output` | Directory to save wheels into (default: `dist/`) |
| `--release-tag` | Download from a specific GitHub release tag |
| `--run-id` | Download from a GitHub Actions run's artifacts |

## Resolution order

1. `--run-id` — download from a workflow run's uploaded artifacts
2. `--release-tag` — download from an explicit GitHub release tag
3. None of the above — finds the latest release tag for the package

Wheels are filtered by platform compatibility before saving.
