# Contributing to ArdvarkFood

Thanks for your interest in improving ArdvarkFood. Contributions of code,
documentation, testing, and thoughtful issue reports are welcome.

## Before you start

- Search existing issues and pull requests to avoid duplicate work.
- For larger changes, open an issue first to discuss the approach.
- Follow the project [Code of Conduct](./CODE_OF_CONDUCT.md).
- For a suspected security vulnerability, use the private process in
  [SECURITY.md](./SECURITY.md); do not open a public issue.

## Development

1. Fork the repository and create a focused branch.
2. Install the dependencies needed for the part of the project you are working
   on. The root `requirements.txt` aggregates the runtime, core, and test
   dependencies. The optional local image-generation dependencies are listed
   separately in `packages/image_generation/requirements.txt`.
3. Make the smallest complete change that fits the existing architecture.
   Avoid committing credentials, model weights, generated output, or local
   databases.
4. Add or update tests and documentation when behavior changes.
5. Run the relevant checks. For example:

   ```bash
   python -m pytest -q
   ```

   The standalone encoding suite is:

   ```bash
   python -m pytest -q tests/core/test_encoding.py
   ```

   Two optional encoding examples are skipped when their upstream fixtures are
   unavailable; report that limitation rather than claiming those cases
   passed.
6. Open a pull request using the repository template and explain the change,
   tests, and any known limitations.

## Pull requests

- Keep each pull request focused and describe user-visible behavior.
- Link related issues when applicable.
- Include tests for bug fixes and new functionality when practical.
- Update relevant documentation and configuration examples.
- Redact secrets and personal information from logs, screenshots, and examples.
- Be responsive to review feedback and explain any proposed alternatives.

Maintainers may ask for changes, defer work that needs further discussion, or
close a pull request that is out of scope or does not meet project requirements.

## Being recognized as a contributor

The Contributors section in `README.md` links to GitHub's automatically
generated contributor graph. It is not a manually maintained name list. GitHub
updates contributor recognition based on activity that becomes part of the
repository's default branch, including merged pull requests. To help GitHub
associate your work with your profile, use a commit email address connected to
your GitHub account and make sure the pull request is merged.

GitHub controls when and how contributions appear in its graph. If your work
does not show up, check that the commit email is associated with your account
and consult GitHub's contribution graph guidance:
<https://docs.github.com/en/account-and-profile/contributing-to-github-with-pull-requests/viewing-contributions-on-your-profile>.
