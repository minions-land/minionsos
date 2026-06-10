---
slug: huggingface-fetch
summary: Pull Hugging Face datasets/models through the working mirror path on this host; use curl against hf-mirror.com and avoid the broken hf CLI path.
layer: logical
tools: Bash, curl, git
version: 1
status: active
supersedes:
references: fetch-fallback-ladder
provenance: human
---

# huggingface-fetch (MinionsOS Role mirror)

Roles use this procedure when they need to download a dataset or model from
Hugging Face during execution.

## Trigger phrases
- "pull / download / fetch from huggingface", "huggingface dataset", "hf:" URL
- A pasted `huggingface.co/...` or `hf.co/...` URL
- A bare `<owner>/<repo>` slug that looks like an HF ID

---

## Host facts (verified 2026-05-22)

- `huggingface.co` is fully TCP-reset on this host. `curl` returns `(35) Recv failure: Connection reset by peer` immediately. DNS resolves cleanly; it's network-level filtering.
- `hf-mirror.com` works via **system curl** (LibreSSL). It is the only working endpoint.
- Python (miniconda OpenSSL 3.6.2 and system LibreSSL 2.8.3) **fails the TLS handshake** to `hf-mirror.com` with `[SSL: UNEXPECTED_EOF_WHILE_READING]`. Therefore the `hf` CLI, `requests`, `urllib`, and `httpx` are all broken on this path.
- `hf-mirror.com` redirects bare slugs to canonical `<owner>/<repo>` (via 307). API on a bare slug returns 401 — looks like an auth failure, isn't.
- `git clone https://hf-mirror.com/datasets/<owner>/<repo>` succeeds, but the LFS smudge filter fails on Xet-bridge DNS (`cas-bridge.xethub.hf-mirror.org` — NXDOMAIN). Skip smudge and rewrite `lfs.url` after clone.

**Implication:** every HF download on this host runs through `curl` against `hf-mirror.com`, with the canonical `<owner>/<repo>` slug.

---

## The recipe

### 1. Probe and resolve canonical slug

```bash
curl -sS --max-time 10 -o /dev/null -w "mirror: %{http_code} %{time_total}s\n" https://hf-mirror.com/

# Resolve canonical owner if needed:
curl -sS --max-time 10 -I "https://hf-mirror.com/api/datasets/<slug>" | grep -i location

# Metadata:
curl -sS --max-time 15 "https://hf-mirror.com/api/datasets/<owner>/<repo>" \
  | python3 -c "import json,sys;d=json.load(sys.stdin);print({k:d.get(k) for k in ['id','sha','lastModified','license','downloads']})"
```

### 2. Single file

```bash
curl -sSL --max-time 60 -o <local-name> \
  "https://hf-mirror.com/datasets/<owner>/<repo>/resolve/main/<path>"
```

Drop `/datasets` for models. Use `/raw/main/` instead of `/resolve/main/` for raw text without LFS resolution.

### 3. List then bulk-fetch

```bash
curl -sSL --max-time 30 \
  "https://hf-mirror.com/api/datasets/<owner>/<repo>/tree/main?recursive=true" \
  | python3 -c "import json,sys;[print(f\"{f['type']}\\t{f['path']}\\t{f.get('size','')}\") for f in json.load(sys.stdin)]"
```

Generate a `fetch.sh` from the listing; loop one curl per blob. Don't pack multiple curls into a single inline shell `for` — prone to mangling.

### 4. Whole repo (git over hf-mirror)

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone --depth=1 \
  https://hf-mirror.com/datasets/<owner>/<repo> <local-dir>
cd <local-dir>
git config -f .lfsconfig lfs.url "https://hf-mirror.com/datasets/<owner>/<repo>.git/info/lfs"
git lfs fetch --include "<narrow-glob>"
git lfs checkout
```

If LFS still fails (Xet-only datasets), use the auto-generated parquet snapshot at:
```
https://hf-mirror.com/datasets/<owner>/<repo>/resolve/refs%2Fconvert%2Fparquet/...
```

### 5. Gated / token-required (GAIA, ImageNet, Llama-2, etc.)

```bash
export HF_TOKEN="hf_..."   # leading space avoids zsh history if HIST_IGNORE_SPACE is set
curl -sSL --max-time 60 -H "Authorization: Bearer $HF_TOKEN" \
  -o <local-name> \
  "https://hf-mirror.com/datasets/<owner>/<repo>/resolve/main/<path>"
```

Terms must already be accepted on huggingface.co (over VPN). The mirror proxies the auth header but cannot accept terms on the user's behalf.

---

## Pitfalls

- Never call `huggingface-cli` / `hf` here — it will look fine and fail mid-handshake.
- Never `WebFetch` on `huggingface.co` — same TCP reset.
- Always resolve to canonical `<owner>/<repo>` before hitting the API; bare slug returns 401.
- Always set `GIT_LFS_SKIP_SMUDGE=1` for the initial clone, then rewrite `.lfsconfig`.
- Don't pull multi-GB repos blindly — narrow the LFS include glob.

---

## Self-update

If a step stops working, patch this file with the new working command line and
a date stamp. If a native Claude Code bundle exists for the same host recipe,
keep its command path aligned with this Role procedure.
