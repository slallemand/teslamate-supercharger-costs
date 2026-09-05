# Publishing the Docker image to GHCR

Images are built by [`.github/workflows/docker-publish.yml`](../.github/workflows/docker-publish.yml) and published to:

`ghcr.io/slallemand/teslamate-supercharger-costs`

## About `GITHUB_TOKEN` (automatic)

Yes — GitHub Actions **automatically** provides `secrets.GITHUB_TOKEN` for every workflow run. You do not create or store it yourself. The workflow already uses it:

```yaml
password: ${{ secrets.GHCR_TOKEN || secrets.GITHUB_TOKEN }}
```

So login is not the problem. The failure `denied: write_package` means GitHub **refuses** that token for writing to the Container Registry, even when:

- the workflow declares `packages: write`, and
- the repository is set to **Read and write permissions**.

This is common on **forked repositories** (this repo is a fork of `kalich5/teslamate-supercharger-costs`). `GITHUB_TOKEN` can build the image but is often blocked from creating/updating GHCR packages.

**Reliable fix: add a Personal Access Token (PAT) as `GHCR_TOKEN`** (Option B below).

---

## Option B — PAT as `GHCR_TOKEN` (recommended)

### 1. Create a classic PAT

1. Open **https://github.com/settings/tokens**
2. **Generate new token (classic)**
3. Scopes:
   - `write:packages`
   - `read:packages`
   - `repo` (only if this repository is **private**)
4. Generate and copy the token

### 2. Add it as a repository secret

1. Open **https://github.com/slallemand/teslamate-supercharger-costs/settings/secrets/actions**
2. **New repository secret**
3. Name: **`GHCR_TOKEN`**
4. Value: paste the PAT
5. Save

### 3. Re-run the workflow

**Actions → Publish Docker image → Re-run all jobs**

The workflow prefers `GHCR_TOKEN` over `GITHUB_TOKEN` when both exist.

---

## Option A — `GITHUB_TOKEN` only (often insufficient)

If you want to try again without a PAT:

### Repository setting

**https://github.com/slallemand/teslamate-supercharger-costs/settings/actions**

→ **Workflow permissions** → **Read and write permissions** → Save

### Account setting (personal repos only)

Also check **https://github.com/settings/actions**

→ **Workflow permissions** → **Read and write permissions**

GitHub uses the **most restrictive** limit across workflow file, repository, and account settings.

### Orphan GHCR package

A failed first publish can leave a package that is not linked to this repository.

1. Open **https://github.com/users/slallemand/packages/container/teslamate-supercharger-costs/settings**
2. Either **Connect repository** → `slallemand/teslamate-supercharger-costs`
3. Or **Delete this package** and re-run the workflow

---

## Make the package public (optional)

After the first successful publish:

1. **https://github.com/users/slallemand/packages/container/teslamate-supercharger-costs**
2. **Package settings → Change visibility → Public**

```bash
docker pull ghcr.io/slallemand/teslamate-supercharger-costs:latest
```

## Manual publish (local)

```bash
docker build -t ghcr.io/slallemand/teslamate-supercharger-costs:latest .
echo "$GHCR_TOKEN" | docker login ghcr.io -u slallemand --password-stdin
docker push ghcr.io/slallemand/teslamate-supercharger-costs:latest
```
