# charmed-analytics-ci

A CLI tool to automate CI-driven integration of updated rock images into consumer Charmed Operator repositories.

This tool is designed for use in Canonical's Charmed Kubeflow stack and enables automated pull request creation after a rock image is built and published. It removes manual effort, reduces errors, and supports scalable release processes.

---

## ✨ Features

- Automatically clones target charm repositories
- Updates image references in YAML/JSON configuration files
- Optionally modifies service spec fields (`user`, `command`)
- Opens pull requests with templated titles and descriptions
- Supports GitHub authentication and branch targeting
- Fully CI-compatible and installable via PyPI

---

## 🚀 Installation

```bash
pip install charmed-analytics-ci
```

Or with Poetry for development:

```bash
git clone https://github.com/canonical/charmed-analytics-ci.git
cd charmed-analytics-ci
poetry install
```

---


## 🔒 License

This project is licensed under the [Apache 2.0 License](LICENSE).

---

## ✍️ Authors

Developed by the [Canonical Charmed Kubeflow team](https://github.com/canonical).