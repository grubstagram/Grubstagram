# Grubstagram

One AI-invented recipe a day on Instagram. Two flavours, alternating: **edible** (real, cookable) and **not edible** (gross-out joke, hazard-tape styling, never mistakable for food).

Everything runs on GitHub Actions. No server, no n8n, no Make.

```
07:13 UTC  1. Generate  Claude writes the recipe → second Claude pass safety-checks it → fal.ai makes the photo
                        → Pillow renders a 4-slide carousel (1080×1350 JPEG) → committed to queue/DATE/
                        → a GitHub Issue opens with the previews (you get it on your phone)
           (your review window: add the `reject` label to stop it, or do nothing)
16:37 UTC  2. Publish   Instagram API pulls the slides from this repo's public URLs and posts the carousel
                        → issue closed with the live link
1st/11th/21st  3. Refresh  renews the 60-day Instagram token automatically
```

## One-time setup (about 45 minutes)

### 1. Keys you need
| Secret name | Where to get it | Cost |
|---|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API keys (add a few £ of credit) | pennies per post |
| `FAL_KEY` | fal.ai → Dashboard → Keys (add ~$10 credit) | ~$0.08 per photo |
| `IG_ACCESS_TOKEN` | Meta developer app, see step 2 | free |
| `IG_USER_ID` *(optional)* | shown next to the token; leave blank to use `me` | — |
| `GH_PAT` | GitHub → Settings → Developer settings → Fine-grained token, this repo only, **Secrets: Read and write** | free |

### 2. Instagram
1. In the Instagram app: Settings → Account type → switch to **Professional (Creator)**. No Facebook Page needed.
2. developers.facebook.com → **Create app** → choose the Instagram use case (*Instagram API with Instagram Login*).
3. In the app: **Instagram → API setup with Instagram login** → add your Instagram account → **Generate token**. Copy it into the `IG_ACCESS_TOKEN` secret. Make sure the content-publish permission (`instagram_business_content_publish`) is ticked.
4. The app can stay in Development mode: you're only posting to your own account.

### 3. This repo
1. Repo must be **public**: Instagram fetches the slide images from `raw.githubusercontent.com`. Your secrets stay private.
2. Settings → Secrets and variables → Actions → add the secrets above.
3. Settings → Actions → General → Workflow permissions → **Read and write**.
4. Settings → Notifications / GitHub mobile app: make sure issue notifications reach your phone.

### 4. First run (do these in order)
1. Actions → **1. Generate daily post** → Run workflow → tick **dry_run**. Checks the plumbing with no API spend; opens a `DRY RUN` issue. Dry runs are never posted.
2. Run it again with dry_run unticked. Real recipe, real photo. Check the issue.
3. Actions → **2. Publish to Instagram** → Run workflow. Your first post goes live.
4. Leave it alone. It now runs every day.

## Daily life
- **Skip a post:** add the `reject` label to that day's issue before 16:37 UTC.
- **Replace it:** run *1. Generate* with **replace** ticked. A fresh draft and a new issue appear; the newest issue for a date is the one that counts.
- **Force a type:** run *1. Generate* with `kind` set.
- **Something broke:** GitHub emails you when a workflow fails. Most common cause: an expired token (re-generate it in the Meta dashboard and update the secret).

## Customise (`config.toml`)
- `schedule.pattern`: e.g. `["edible", "edible", "not_edible"]` for 2:1.
- `image.model`: swap fal.ai models (`fal-ai/nano-banana-pro`, a FLUX model, etc.). If fal returns 422, trim `image.params`.
- `image.style`: the house photo style. Keep "no people" — it keeps you clear of Instagram's AI-generated-person label rules.
- `caption.*`: footers and base hashtags. Brand handle in `brand.handle`.
- Post times: the `cron:` lines in `.github/workflows/` (UTC).

## Run locally
```bash
pip install -r requirements.txt
python -m grub generate --dry-run                     # no keys needed
export ANTHROPIC_API_KEY=... FAL_KEY=...
python -m grub generate --date 2026-11-01 --kind not_edible
python -m grub check                                  # verifies keys + Instagram account
```

## Safety rails built in
- Edible: a second model reviews food safety (meat/egg cooking, raw flour, quantities, allergens). Fails → rewritten, up to 3 tries.
- Not edible: hard word blocklist (chemicals, medicines, alcohol, toxic plants, bodily fluids…) plus a reviewer that fails anything mistakable for food, copyable as a dare, or hazardous if imitated.
- Every not-edible post carries NOT FOOD badges, hazard tape and a "DO NOT ATTEMPT" closing slide.
- Every caption says it's AI-generated.

## v2 ideas
- Reels: animate the hero shot (Kling / Veo via fal.ai) and add music with ffmpeg.
- Private repo: point `MEDIA_BASE_URL` at Cloudflare R2 or Cloudinary instead of GitHub raw URLs.
- Pull trending dishes/ingredients into the prompt; auto-reply to comments.
