# charmed-analytics-ci

A CLI tool to automate CI-driven integration of updated **rock images** into consumer **Charmed Operator** repositories.

This tool is part of Canonical's Charmed Kubeflow stack and enables automated pull request creation after a rock image is built and published. It eliminates manual effort, reduces human error, and supports scalable, reproducible CI/CD pipelines.

---

## ✨ Features

- ✅ Automatically clones target charm repositories
- 🔁 Updates image references in YAML or JSON configuration files
- ⚙️ Optionally modifies service-spec fields like `user` and `command`
- 🔧 Validates metadata schemas for correctness before modification
- 🤖 Opens pull requests with deterministic branches and templated descriptions
- 🔐 Supports GitHub authentication via token
- 📦 Installable via PyPI and usable from CI pipelines

---

## 🚀 Installation

Install from PyPI:

```bash
pip install charmed-analytics-ci
```

Or install for development:

```bash
git clone https://github.com/canonical/charmed-analytics-ci.git
cd charmed-analytics-ci
poetry install
```

---

## 🧪 CLI Usage

After installing, the CLI provides a single command:

```bash
chaci integrate-rock METADATA_FILE BASE_BRANCH ROCK_IMAGE [GITHUB_TOKEN] [GITHUB_USERNAME] [--clone-dir PATH]
```

### Example:

```bash
export GH_TOKEN="ghp_abc123..."  # or pass explicitly

chaci integrate-rock rock-ci-metadata.yaml main ghcr.io/canonical/my-rock:1.0.0
```

### Arguments:

| Argument        | Description                                                                 |
|-----------------|-----------------------------------------------------------------------------|
| `METADATA_FILE` | Path to `rock-ci-metadata.yaml` describing integration targets              |
| `BASE_BRANCH`   | Target branch for PRs (e.g. `main` or `develop`)                            |
| `ROCK_IMAGE`    | Full rock image string (e.g. `ghcr.io/org/my-rock:1.0.0`)                   |
| `GITHUB_TOKEN`  | Optional. GitHub token. Falls back to `$GH_TOKEN` env var if not provided   |
| `GITHUB_USERNAME` | Optional. GitHub username. Defaults to `"__token__"` if not provided      |
| `--clone-dir`   | Optional. Directory where target repos will be cloned (default: `/tmp`)     |

---

## 📄 rock-ci-metadata.yaml Format

```yaml
integrations:
  - consumer-repository: canonical/my-charm
    replace-image:
      - file: "metadata.yaml"
        path: "resources.my-rock.upstream-source"
      - file: "src/images.json"
        path: "config.batcher"
    service-spec:
      - file: "service-spec.json"
        user:
          path: "containers[0].user"
          value: "1001"
        command:
          path: "containers[0].command[1]"
          value: "/start"
```

- All file paths are **relative to the repo root**
- Paths can use `dot` and `bracket` notation for navigating YAML/JSON

---

## 🧪 Testing

### Unit tests

```bash
tox -e unit
```

### Integration tests

Requires access to a real GitHub repo and valid token. These tests:
- Open a real PR in a test repository
- Validate the contents of the PR
- Automatically clean up the branch and PR after execution

Run with:

```bash
export GH_TOKEN=<your_token>
export CHACI_TEST_REPO="org/repo-name"
export CHACI_TEST_BASE_BRANCH="target-branch"

tox -e integration
```

---

## 🧰 Development & Contributing

This project uses:
- [tox](https://tox.readthedocs.io/) for test environments
- [pytest](https://docs.pytest.org/) for testing
- [black](https://black.readthedocs.io/) + [ruff](https://docs.astral.sh/ruff/) for linting

To run all checks locally:

```bash
tox -e lint,unit,integration
```

---

## 📁 Project Structure

| File                          | Purpose                                      |
|-------------------------------|----------------------------------------------|
| `rock_integrator.py`          | Core logic for modifying files with images   |
| `git_client.py`               | Git and GitHub abstraction for PR workflow   |
| `rock_metadata_handler.py`    | Orchestration for multi-repo integration     |
| `rock_ci_metadata_schema.py` | JSON Schema used to validate metadata files  |
| `cli.py`                      | CLI entrypoint via `click`                   |
| `templates/pr_body.md.j2`     | Jinja2 template for pull request bodies      |

---

## 🔒 License

This project is licensed under the [Apache 2.0 License](LICENSE).

---

## ✍️ Authors

Built by the [Canonical Charmed Kubeflow team](https://github.com/canonical).