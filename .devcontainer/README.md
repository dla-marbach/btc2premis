# Development in GitHub Codespaces / Dev Container

This configuration builds on the [`mcr.microsoft.com/devcontainers/python`](https://mcr.microsoft.com/en-us/product/devcontainers/python/about)
image with a fixed version tag (see [`Dockerfile`](Dockerfile), updated by
Dependabot) and no additional features. All project-specific setup is performed by
[`post-create.sh`](post-create.sh) after the container is created:

```bash
python3 -m pip install --require-hashes -r requirements-dev.txt
python3 -m pip install --no-deps -e .
```

Compared to the instructions in [`../README.md`](../README.md), the `dev`
(pytest, ruff) and `validate` (lxml for `--validate`) extras are already
installed, with the exact versions from the lockfile `requirements-dev.txt`; no manual installation step is required.

## Common commands

```bash
ruff check . && ruff format --check .
pytest -q
btc2premis --help
```

The tests run without network access against the fake API in `tests/fixtures/`.

## Credentials in Codespaces

Do not store passwords in files in the repository for runs against the real
Browsertrix instance. Instead, create
[Codespaces secrets](https://docs.github.com/en/codespaces/managing-your-codespaces/managing-your-account-specific-secrets-for-github-codespaces);
they are available in the container as environment variables:

- `BTC_USER`
- `BTC_OID`
- `BTC_PASSWORD`

```bash
btc2premis --list
```

If no secrets are set, interactive prompting with `-p` still works.

## Notes

- If `post-create.sh` does not run (for example, because the setup run was aborted),
  it can be executed manually at any time: `bash .devcontainer/post-create.sh`.
- The image includes Python 3.13; `post-create.sh` aborts if it is older than
  3.11.
