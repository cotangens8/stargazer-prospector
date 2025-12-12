# GitHub Stargazer Prospector

Automatically discover companies evaluating analytics tools by monitoring who stars Amplitude, Mixpanel, and Segment SDKs on GitHub. Enriches leads and sends them to Clay for further processing.

## What It Does

1. **Fetches** recent stargazers (last 30 days) from:
   - `amplitude/Amplitude-JavaScript`
   - `mixpanel/mixpanel-js`
   - `segmentio/analytics.js`

2. **Enriches** each user with:
   - Company name (from GitHub profile)
   - Email (if public)
   - Organizations they belong to
   - Social links (Twitter, blog)

3. **Scores** leads based on:
   - Has company info (+3)
   - Has org memberships (+2)
   - Has public email (+2)
   - Starred multiple repos (+3 each)
   - Has followers (+1-2)

4. **Sends** to Clay webhook for firmographic enrichment

---

## Setup Guide (15 minutes)

### Step 1: Create Your GitHub Repository

1. Go to [github.com/new](https://github.com/new)
2. Name it `stargazer-prospector` (or whatever you like)
3. Make it **Private**
4. Click **Create repository**

### Step 2: Upload the Files

**Option A: Using GitHub Web UI**

1. In your new repo, click **Add file** → **Upload files**
2. Drag and drop these files:
   - `fetch_stargazers.py`
   - `requirements.txt`
3. Click **Commit changes**

4. Now create the workflow folder:
   - Click **Add file** → **Create new file**
   - Name it: `.github/workflows/fetch-stargazers.yml`
   - Paste the contents of the workflow file
   - Click **Commit changes**

**Option B: Using Git CLI**

```bash
git clone https://github.com/YOUR_USERNAME/stargazer-prospector.git
cd stargazer-prospector
# Copy files here
git add .
git commit -m "Initial setup"
git push
```

### Step 3: Create a GitHub Personal Access Token

The script needs a token to avoid rate limits (60 → 5000 requests/hour).

1. Go to [github.com/settings/tokens](https://github.com/settings/tokens?type=beta)
2. Click **Generate new token** → **Fine-grained token**
3. Settings:
   - Name: `stargazer-prospector`
   - Expiration: 90 days (set a reminder to renew)
   - Repository access: **Public repositories (read-only)**
   - Permissions: No additional permissions needed
4. Click **Generate token**
5. **Copy the token** (you won't see it again!)

### Step 4: Set Up Clay Webhook

1. Log into [Clay](https://app.clay.com)
2. Create a new table called "GitHub Stargazer Leads"
3. Click **Add data source** → **Webhook**
4. Copy the webhook URL (looks like `https://api.clay.com/v1/webhooks/...`)

### Step 5: Add Secrets to GitHub

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Add these two secrets:

| Name | Value |
|------|-------|
| `GH_PAT` | Your GitHub personal access token from Step 3 |
| `CLAY_WEBHOOK_URL` | Your Clay webhook URL from Step 4 |

### Step 6: Test It!

1. Go to **Actions** tab in your repo
2. Click **GitHub Stargazer Prospector** in the left sidebar
3. Click **Run workflow** → **Run workflow**
4. Watch it run (takes 5-15 minutes depending on how many stargazers)
5. Check your Clay table for incoming leads!

---

## Clay Table Setup

After leads arrive, set up these enrichment columns in Clay:

### Recommended Columns

| Column | Type | Purpose |
|--------|------|---------|
| `username` | Text | GitHub username |
| `company_clean` | Text | Company from GitHub profile |
| `email` | Text | Public email if available |
| `repos_starred` | Text | Which repos they starred |
| `score` | Number | Lead score (higher = better) |
| `user_url` | URL | Link to GitHub profile |

### Enrichment Columns to Add

1. **Company Domain** (Clay enrichment)
   - Use "Find company domain from name" on `company_clean`

2. **Company Info** (Clay enrichment)
   - Use "Enrich company" on the domain
   - Get: employee count, industry, funding, description

3. **ICP Filter** (Formula)
   ```
   IF(
     AND(
       {Employee Count} >= 50,
       {Employee Count} <= 300,
       OR({Industry} = "Software", {Industry} = "SaaS", {Industry} = "Technology")
     ),
     "✅ ICP Match",
     "❌ Not ICP"
   )
   ```

4. **Find Decision Maker** (Clay enrichment)
   - Use "Find people at company" 
   - Filter: VP Engineering, Head of Product, CTO

---

## Customization

### Change Lookback Period

In GitHub Actions secrets, add:
- Name: `LOOKBACK_DAYS`
- Value: `7` (or whatever number of days)

### Add More Repos

Edit `fetch_stargazers.py` and update the `REPOS` list:

```python
REPOS = [
    "amplitude/Amplitude-JavaScript",
    "mixpanel/mixpanel-js",
    "segmentio/analytics.js",
    "PostHog/posthog-js",  # Add more here
    "rudderlabs/rudder-sdk-js",
]
```

### Change Schedule

Edit `.github/workflows/fetch-stargazers.yml`:

```yaml
schedule:
  # Every Monday at 9am UTC
  - cron: '0 9 * * 1'
  
  # Twice daily
  - cron: '0 9,21 * * *'
```

---

## Troubleshooting

### "Rate limit exceeded"
- Make sure `GH_PAT` secret is set correctly
- Check the token hasn't expired

### "No stargazers found"
- The repos might not have new stargazers in the last 30 days
- Try increasing `LOOKBACK_DAYS`

### "Clay webhook failed"
- Verify the webhook URL is correct
- Check Clay table is set up to receive webhooks
- Look at Clay's webhook logs for errors

### Check Logs
1. Go to **Actions** tab
2. Click on a workflow run
3. Click on the job to see detailed logs

---

## How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  GitHub Actions (runs daily at 9am UTC)                     │
│                                                             │
│  1. Fetch stargazers from 3 repos (last 30 days)            │
│  2. For each user: get profile + orgs                       │
│  3. Clean company names, dedupe, score                      │
│  4. POST to Clay webhook                                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Clay                                                       │
│                                                             │
│  1. Receive leads via webhook                               │
│  2. Enrich: company domain → firmographics                  │
│  3. Filter: 50-300 employees, B2B SaaS                      │
│  4. Find contacts: VP Eng, Head of Product                  │
└─────────────────────────────────────────────────────────────┘
```

---

## Cost

- **GitHub Actions**: Free (2000 minutes/month on free plan)
- **GitHub API**: Free (with token)
- **Clay**: Free tier includes webhooks and some enrichments

---

## Questions?

Open an issue in this repo or reach out!
