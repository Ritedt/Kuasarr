# Release Process

How a merged pull request becomes a running container. No manual publish step
exists — merging to `main` is what produces the Docker image.

---

## The chain

```
merge PR into main
      ↓
CI runs (.github/workflows/unified-ci.yml, event: push)
      ↓
version = highest git tag vMAJOR.MINOR.PATCH, patch bumped
      ↓
builds linux/amd64 + linux/arm64, merges into a multi-arch manifest
      ↓
pushes ghcr.io/ritedt/kuasarr:<version> and :latest
      ↓
creates git tag v<version> and GitHub Release v<version>
```

Verified with the merge of PR #82: tag `v2.0.5` was the highest at the time,
so the run produced **2.0.6**, and `ghcr.io/ritedt/kuasarr:latest` reports
`{"version": "2.0.6"}`.

---

## Tags that get pushed

| Tag | Content |
|---|---|
| `<version>` | multi-arch manifest (amd64 + arm64) |
| `<version>-amd64` | single-arch build |
| `<version>-arm64` | single-arch build |
| `latest` | multi-arch manifest, tracks the newest merge to `main` |
| `beta`, `<version>-beta<n>` | PR builds, never point at a release |

A version-pinned tag is immutable in practice. `latest` moves with every merge,
so **pin the version when a rollback has to be possible.**

---

## Where the version actually comes from

The **git tag is the source of truth**, not `version.json`:

1. The workflow lists tags matching `^v[0-9]+\.[0-9]+\.[0-9]+$` and takes the
   highest by `sort -V`.
2. It bumps the patch component (a `major`/`minor` bump is possible via the
   `version_bump` workflow input).
3. `Hier_Version_Ändern.txt` in the repository root overrides the result — but
   **only if it is higher than the latest tag**. A stale value is ignored with a
   warning, which is why the leftover `2.0.3` in that file is harmless.
4. CI injects the result into `version.json` and `kuasarr/version.json` before
   building.

### version.json in the repository is stale on purpose

The committed `version.json` on `main` reads `1.17.2` while releases are on
`2.0.x`. That is **not a bug in the build** — the file is overwritten at build
time and the shipped artifact carries the correct `2.0.6`. But reading the
committed file tells you the wrong version.

> Do not treat the repository `version.json` as the current version. Check the
> GitHub Release list or the `latest` tag instead.

---

## Updating a running instance

The container only picks up a new image when it is re-created. A restart alone
is not enough — Unraid's "Restart" reuses the existing image layers.

```bash
docker pull ghcr.io/ritedt/kuasarr:latest
docker rm -f kuasarr
docker run -d --name kuasarr \
  -p 9999:9999 \
  -v /pfad/zum/config:/config \
  -e INTERNAL_ADDRESS=http://<host>:9999 \
  -e EXTERNAL_ADDRESS=http://<host>:9999 \
  -e TZ=Europe/Berlin \
  ghcr.io/ritedt/kuasarr:latest
```

Confirm afterwards that the banner reports the expected version, then run the
checks in [Container-Test-Playbook](Container-Test-Playbook.md).

### In-memory state does not survive the swap

`recents_imdb_titles` and the other negative caches live in a
`multiprocessing.Manager().dict()` — RAM, not a file. Re-creating the container
clears them, which is what you want after an upgrade: a cached `None` entry from
a previous version would otherwise mask the fixed code path for up to an hour.

---

## Troubleshooting

**"The fix is merged but the container still shows the old behaviour."**
Compare the banner version in the log against the release list. The image on the
host was never re-created — see above.

**"Is the tag I expect actually published?"**
GHCR's `tags/list` endpoint is **paginated**. A plain query returns only the
first 100 tags and silently omits everything newer, which looks exactly like a
missing release. Follow the `Link: ...rel="next"` header until it stops:

```bash
TOKEN=$(curl -s "https://ghcr.io/token?scope=repository:ritedt/kuasarr:pull&service=ghcr.io" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
curl -s -H "Authorization: Bearer $TOKEN" \
  "https://ghcr.io/v2/ritedt/kuasarr/tags/list?n=100" | python3 -m json.tool
```

**`docker pull` fetches but the behaviour is unchanged.**
The image is current but a cached lookup masks it. Re-create the container to
drop the in-memory cache (previous section).