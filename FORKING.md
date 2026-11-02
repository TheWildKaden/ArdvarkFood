# Forking and hosting ArdvarkFood

Forks are welcome. The project overview site is static and can be deployed to
GitHub Pages or Cloudflare Pages. The FastAPI application, model inference, and
image generation are separate from that site; static Pages hosting does not
run those backends. The separate Stock Watch source is not currently a verified
build target.

## GitHub Pages

1. Fork the repository.
2. In the fork, open **Settings → Pages** and set the build/deployment source
   to **GitHub Actions**.
3. Push a change to the fork's default branch or manually run **Deploy GitHub
   Pages** from the Actions tab.

The workflow builds the static site for pull requests, then deploys pushes to
the repository's configured default branch. It derives repository links from
the fork checkout, so no owner/repository edits should be needed.

## Cloudflare Pages

1. Create a Pages project and connect it to your fork.
2. Set the project root to `/`.
3. Set the build command to `npm run build:pages`.
4. Set the build output directory to `dist`.
5. Use the fork's default branch for production. Cloudflare can create preview
   deployments for other branches and pull requests.

The build has no npm dependencies. It obtains the GitHub repository URL from
the Git remote, `GITHUB_REPOSITORY`, or the optional
`PAGES_REPOSITORY_URL` environment variable. It gets the branch from the CI
environment or Git checkout; override it with `PAGES_REPOSITORY_BRANCH` when
needed. These variables are useful for mirrors and custom CI.

For a local build and preview:

```bash
npm run build:pages
npm run preview:pages
```

The preview serves the generated `dist/` folder at <http://localhost:4173>.
Alternatively, `./infrastructure/scripts/preview-pages.sh` serves the source
`docs/` folder.

## Running the application

Pages serves only the static overview. To run the application UI and its
backend, follow the Python app instructions in [README.md](./README.md). Do not
put model weights, secrets, databases, generated files, or backend source into
the static Pages output. Review [SECURITY.md](./SECURITY.md) before exposing
any application service to the internet.
