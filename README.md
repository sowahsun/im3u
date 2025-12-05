M3U Checker

An automated tool to fetch, merge, and validate M3U playlists. Powered by GitHub Actions.

Features

Auto-Fetch: Downloads multiple m3u sources from a configurable list.

Merge: Combines all sources into a single playlist (source.m3u).

Validation: Checks the connectivity of each stream and filters out dead links.

Result Generation: Produces a clean, valid playlist (valid.m3u).

Secure: Uses GitHub Secrets to protect your source URLs.

Automated: Runs automatically on a schedule (default: every 12 hours).

Quick Start (GitHub Actions)

Fork this repository.

Navigate to Settings > Secrets and variables > Actions.

Click New repository secret.

Name: M3U_CONFIG

Secret: Paste your JSON configuration (see format below).

Go to the Actions tab and enable workflows. It will run automatically or you can trigger it manually.

Configuration Format

Your M3U_CONFIG (or local config.json) should follow this JSON structure:

{
  "sources": {
    "Category Name 1": "[http://example.com/playlist1.m3u](http://example.com/playlist1.m3u)",
    "Category Name 2": "[http://example.com/playlist2.m3u](http://example.com/playlist2.m3u)"
  }
}


Local Usage

To run the script locally on your machine:

Install Dependencies:

pip install -r requirements.txt


Configuration:

Create a config.json file in the root directory (same format as above).

Note: config.json is git-ignored by default to prevent leaks.

Run:

python app.py


Output

source.m3u: The raw merged playlist containing all channels from all sources.

valid.m3u: The final playlist containing only accessible streams.
