# `uvr install`

Install a package directly from GitHub releases.

```bash
uvr install PKG --repo ORG/REPO              # latest version
uvr install "PKG==1.2.3" --repo ORG/REPO     # specific version
```

Downloads the wheel from the GitHub release and installs it with `uv pip install`. Use PEP 508 version pinning (e.g., `"PKG==1.2.3"`) for a specific version. When no version is specified, finds the latest release tag for the package.
