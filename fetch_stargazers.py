#!/usr/bin/env python3
"""
GitHub Stargazer Prospector

Fetches recent stargazers from analytics SDK repos, resolves their companies,
and sends qualified leads to a Clay webhook.

Target repos: Amplitude JS, Mixpanel JS, Segment Analytics.js
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# Configuration
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
CLAY_WEBHOOK_URL = os.environ.get("CLAY_WEBHOOK_URL")
LOOKBACK_DAYS = int(os.environ.get("LOOKBACK_DAYS", 30))

# Repos to monitor (owner/repo format)
REPOS = [
    "amplitude/Amplitude-JavaScript",
    "mixpanel/mixpanel-js",
    "segmentio/analytics.js",
]

# Rate limiting
REQUEST_DELAY = 0.5  # seconds between requests


def get_headers():
    """Get headers for GitHub API requests."""
    headers = {
        "Accept": "application/vnd.github.v3.star+json",  # Includes starred_at timestamp
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers


def fetch_stargazers(repo: str, since: datetime) -> list[dict]:
    """
    Fetch stargazers for a repo who starred after the given date.
    Returns list of {username, starred_at, repo} dicts.
    """
    stargazers = []
    page = 1
    per_page = 100
    
    print(f"  Fetching stargazers for {repo}...")
    
    while True:
        url = f"https://api.github.com/repos/{repo}/stargazers"
        params = {"per_page": per_page, "page": page}
        
        response = requests.get(url, headers=get_headers(), params=params)
        
        if response.status_code == 403:
            print(f"  ⚠️  Rate limited. Waiting 60 seconds...")
            time.sleep(60)
            continue
        
        if response.status_code != 200:
            print(f"  ❌ Error fetching {repo}: {response.status_code}")
            break
        
        data = response.json()
        if not data:
            break
        
        for star in data:
            starred_at_str = star.get("starred_at")
            if starred_at_str:
                starred_at = datetime.fromisoformat(starred_at_str.replace("Z", "+00:00"))
                if starred_at >= since:
                    stargazers.append({
                        "username": star["user"]["login"],
                        "starred_at": starred_at_str,
                        "repo": repo,
                        "user_url": star["user"]["html_url"],
                    })
                else:
                    # GitHub returns stargazers in reverse chronological order
                    # Once we hit old stars, we can stop
                    print(f"  ✓ Found {len(stargazers)} recent stargazers")
                    return stargazers
        
        page += 1
        time.sleep(REQUEST_DELAY)
        
        # Safety limit
        if page > 50:
            print(f"  ⚠️  Hit page limit, stopping")
            break
    
    print(f"  ✓ Found {len(stargazers)} recent stargazers")
    return stargazers


def fetch_user_details(username: str) -> dict:
    """Fetch detailed user info including company and email."""
    url = f"https://api.github.com/users/{username}"
    response = requests.get(url, headers=get_headers())
    
    if response.status_code == 403:
        print(f"    ⚠️  Rate limited on user {username}, waiting...")
        time.sleep(60)
        response = requests.get(url, headers=get_headers())
    
    if response.status_code != 200:
        return {}
    
    data = response.json()
    return {
        "name": data.get("name"),
        "company": data.get("company"),
        "email": data.get("email"),
        "bio": data.get("bio"),
        "location": data.get("location"),
        "blog": data.get("blog"),
        "twitter": data.get("twitter_username"),
        "public_repos": data.get("public_repos"),
        "followers": data.get("followers"),
    }


def fetch_user_orgs(username: str) -> list[str]:
    """Fetch public organizations for a user."""
    url = f"https://api.github.com/users/{username}/orgs"
    response = requests.get(url, headers=get_headers())
    
    if response.status_code != 200:
        return []
    
    return [org["login"] for org in response.json()]


def clean_company_name(company: str) -> str:
    """Clean up company name from GitHub profile."""
    if not company:
        return ""
    
    # Remove common prefixes
    company = company.strip()
    if company.startswith("@"):
        company = company[1:]
    
    # Remove common suffixes
    for suffix in [", Inc.", ", Inc", " Inc.", " Inc", " LLC", " Ltd", " Ltd."]:
        if company.endswith(suffix):
            company = company[:-len(suffix)]
    
    return company.strip()


def enrich_stargazers(stargazers: list[dict]) -> list[dict]:
    """Add user details and org info to stargazers."""
    enriched = []
    total = len(stargazers)
    
    print(f"\nEnriching {total} users...")
    
    for i, star in enumerate(stargazers):
        username = star["username"]
        print(f"  [{i+1}/{total}] {username}", end="")
        
        # Get user details
        details = fetch_user_details(username)
        time.sleep(REQUEST_DELAY)
        
        # Get orgs
        orgs = fetch_user_orgs(username)
        time.sleep(REQUEST_DELAY)
        
        company = clean_company_name(details.get("company", ""))
        
        enriched.append({
            **star,
            **details,
            "company_clean": company,
            "orgs": orgs,
            "org_count": len(orgs),
        })
        
        print(f" → {company or '(no company)'}")
    
    return enriched


def dedupe_and_score(leads: list[dict]) -> list[dict]:
    """
    Deduplicate by username and add a basic score.
    Higher score = more interesting lead.
    """
    # Dedupe - keep the one with most info
    by_username = {}
    for lead in leads:
        username = lead["username"]
        if username not in by_username:
            by_username[username] = lead
        else:
            # Merge repos they starred
            existing = by_username[username]
            if "repos_starred" not in existing:
                existing["repos_starred"] = [existing["repo"]]
            existing["repos_starred"].append(lead["repo"])
    
    # Score
    scored = []
    for lead in by_username.values():
        score = 0
        
        # Has company = good signal
        if lead.get("company_clean"):
            score += 3
        
        # In orgs = likely professional
        if lead.get("org_count", 0) > 0:
            score += 2
        
        # Has email = easier to contact
        if lead.get("email"):
            score += 2
        
        # Multiple repos starred = high intent
        repos_starred = lead.get("repos_starred", [lead["repo"]])
        score += (len(repos_starred) - 1) * 3
        
        # Some followers = established presence
        followers = lead.get("followers", 0)
        if followers > 100:
            score += 2
        elif followers > 10:
            score += 1
        
        lead["score"] = score
        lead["repos_starred"] = repos_starred
        scored.append(lead)
    
    # Sort by score descending
    scored.sort(key=lambda x: x["score"], reverse=True)
    
    return scored


def send_to_clay(leads: list[dict]) -> bool:
    """Send leads to Clay webhook."""
    if not CLAY_WEBHOOK_URL:
        print("\n⚠️  No CLAY_WEBHOOK_URL set. Skipping webhook.")
        return False
    
    print(f"\nSending {len(leads)} leads to Clay...")
    
    # Clay webhooks typically expect individual records or a batch
    # We'll send as a batch
    payload = {"leads": leads, "fetched_at": datetime.now(timezone.utc).isoformat()}
    
    response = requests.post(
        CLAY_WEBHOOK_URL,
        json=payload,
        headers={"Content-Type": "application/json"}
    )
    
    if response.status_code in (200, 201, 202):
        print("✓ Successfully sent to Clay")
        return True
    else:
        print(f"❌ Failed to send to Clay: {response.status_code} - {response.text}")
        return False


def save_local(leads: list[dict], filename: str = "leads.json"):
    """Save leads to local JSON file."""
    output_path = os.path.join(os.path.dirname(__file__), filename)
    with open(output_path, "w") as f:
        json.dump(leads, f, indent=2, default=str)
    print(f"✓ Saved {len(leads)} leads to {output_path}")
    return output_path


def main():
    print("=" * 60)
    print("GitHub Stargazer Prospector")
    print("=" * 60)
    
    # Check auth
    if GITHUB_TOKEN:
        print("✓ GitHub token configured (5000 requests/hour)")
    else:
        print("⚠️  No GitHub token - limited to 60 requests/hour")
        print("  Set GITHUB_TOKEN env var for better rate limits")
    
    # Calculate lookback date
    since = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    print(f"\nLooking for stargazers since: {since.date()}")
    print(f"Repos: {', '.join(REPOS)}")
    
    # Fetch stargazers from all repos
    all_stargazers = []
    for repo in REPOS:
        stargazers = fetch_stargazers(repo, since)
        all_stargazers.extend(stargazers)
        time.sleep(REQUEST_DELAY)
    
    print(f"\nTotal stargazers found: {len(all_stargazers)}")
    
    if not all_stargazers:
        print("No stargazers found in the time period. Exiting.")
        return
    
    # Enrich with user details
    enriched = enrich_stargazers(all_stargazers)
    
    # Dedupe and score
    leads = dedupe_and_score(enriched)
    
    print(f"\nFinal lead count: {len(leads)}")
    
    # Show top leads
    print("\n" + "=" * 60)
    print("Top 10 Leads by Score:")
    print("=" * 60)
    for lead in leads[:10]:
        print(f"  {lead['score']:2d} | {lead['username']:20s} | {lead.get('company_clean', '-'):30s}")
    
    # Save locally
    output_path = save_local(leads)
    
    # Send to Clay
    send_to_clay(leads)
    
    print("\n✓ Done!")
    return output_path


if __name__ == "__main__":
    main()
