# Publishing the Docker image to GHCR

Images are built by [`.github/workflows/docker-publish.yml`](../.github/workflows/docker-publish.yml) and published to:

`ghcr.io/slallemand/teslamate-supercharger-costs`

## If the workflow fails with `write_package` denied

GitHub is blocking the push to the Container Registry. Fix **one** of the following.

### Option A — Allow GITHUB_TOKEN to write (recommended)

1. Open **https://github.com/slallemand/teslamate-supercharger-costs/settings/actions**
2. Under **Workflow permissions**, select **Read and write permissions**
3. Click **Save**
4. Re-run the failed workflow (**Actions → Publish Docker image → Re-run all jobs**)

If this repository is under an organization, an org admin must change the same setting under **Organization → Settings → Actions**.

### Option B — Use a Personal Access Token (PAT)

Use this when Option A is not available (org policy, etc.).

1. Create a **classic** PAT at **https://github.com/settings/tokens**
   - Scopes: `write:packages`, `read:packages`, and `repo` (if the repository is private)
2. In the repository, go to **Settings → Secrets and variables → Actions**
3. Add a repository secret named **`GHCR_TOKEN`** with the PAT value
4. Re-run the workflow

The workflow uses `GHCR_TOKEN` when set, otherwise falls back to `GITHUB_TOKEN`.

## Make the package public (optional)

After the first successful publish:

1. Open **https://github.com/users/slallemand/packages/container/teslamate-supercharger-costs**
2. **Package settings → Change visibility → Public**

Then anyone can pull without logging in:

```bash
docker pull ghcr.io/slallemand/teslamate-supercharger-costs:latest
```

## Manual publish (local)

```bash
docker build -t ghcr.io/slallemand/teslamate-supercharger-costs:latest .
echo "$GHCR_TOKEN" | docker login ghcr.io -u slallemand --password-stdin
docker push ghcr.io/slallemand/teslamate-supercharger-costs:latest
```
