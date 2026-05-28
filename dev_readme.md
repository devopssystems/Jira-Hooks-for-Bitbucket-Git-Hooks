# jhfb-hooks Developer Notes

This file is for maintainers of the `jhfb-hooks` package.

The package lives in `local-hooks/` and is published as `jhfb-hooks` based on [pyproject.toml](/Users/benni/DevOpsSystems/Development/Repository/atlassian-addons/jira-hooks-for-bitbucket-cloud/local-hooks/pyproject.toml:1).

## Build and publish to TestPyPI

1. Change into the package directory:

```bash
cd local-hooks
```

2. Install the required build tools:

```bash
python3 -m pip install --upgrade build twine
```

3. Build the distribution files:

```bash
python3 -m build
```

4. Check the generated package metadata and README rendering:

```bash
python3 -m twine check dist/*
```

5. Upload the package to TestPyPI:

```bash
python3 -m twine upload --repository testpypi dist/*
```

When `twine` asks for credentials:

- Username: `__token__`
- Password: your TestPyPI API token

## Verify the uploaded package

Create a fresh virtual environment and install the package from TestPyPI:

```bash
python3 -m venv .venv-test
source .venv-test/bin/activate
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple jhfb-hooks
```

## Important notes

- Each version can only be uploaded once per package index.
- If `1.0.0` already exists on TestPyPI, bump the version in `local-hooks/pyproject.toml` before uploading again.
- TestPyPI and PyPI are separate indexes. A successful upload to TestPyPI does not publish anything to the real PyPI.
