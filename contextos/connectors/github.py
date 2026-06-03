"""
ContextOS connectors/github.py — GitHub Issues and Wiki connector.

Pulls GitHub Issues and Wiki pages from a public repository (or private
with a token) and converts them to structured Markdown vault documents.

Usage:
  context pull github --repo owner/repo --type issues
  context pull github --repo owner/repo --type wiki
  context pull github --repo owner/repo --type all

Auth (optional, for private repos or higher rate limits):
  export GITHUB_TOKEN=ghp_xxxx
  # or set in .contextos/config.yaml under connectors.github.token
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from contextos.connectors.base import BaseConnector, ConnectorResult

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
MAX_ISSUES  = 100   # max issues per pull
MAX_RETRIES = 3


class GitHubConnector(BaseConnector):
    """Pull GitHub Issues and Wiki pages into the vault."""

    name        = "github"
    description = "Pull GitHub Issues and Wiki pages as indexed vault docs"

    def __init__(self, project: str, config: Optional[dict] = None):
        super().__init__(project, config)
        self.repo  = self.config.get("repo", "")
        self.token = self.config.get("token") or os.environ.get("GITHUB_TOKEN", "")
        self.pull_type = self.config.get("type", "issues")  # issues | wiki | all
        self.label = self.config.get("label")   # filter by label
        self.state = self.config.get("state", "open")  # open | closed | all
        self.max_items = int(self.config.get("max_items", MAX_ISSUES))

    def fetch(self) -> list[ConnectorResult]:
        if not self.repo:
            raise ValueError("GitHub connector requires 'repo' config (e.g. owner/repo)")

        results = []
        if self.pull_type in ("issues", "all"):
            results.extend(self._fetch_issues())
        if self.pull_type in ("wiki", "all"):
            results.extend(self._fetch_wiki())
        return results

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    def _fetch_issues(self) -> list[ConnectorResult]:
        """Fetch open issues from GitHub REST API."""
        try:
            import urllib.request, urllib.error
        except ImportError:
            logger.error("urllib not available")
            return []

        results = []
        page = 1
        per_page = min(self.max_items, 50)

        while len(results) < self.max_items:
            url = (
                f"{GITHUB_API}/repos/{self.repo}/issues"
                f"?state={self.state}&per_page={per_page}&page={page}"
            )
            if self.label:
                url += f"&labels={self.label}"

            data = self._api_get(url)
            if not data:
                break

            for issue in data:
                # Skip pull requests (they appear in issues endpoint too)
                if "pull_request" in issue:
                    continue

                result = self._issue_to_result(issue)
                if result:
                    results.append(result)

            if len(data) < per_page:
                break
            page += 1

        logger.info("GitHub Issues: fetched %d from %s", len(results), self.repo)
        return results

    def _issue_to_result(self, issue: dict) -> Optional[ConnectorResult]:
        number    = issue.get("number", 0)
        title     = issue.get("title", "Untitled")
        body      = issue.get("body") or ""
        state     = issue.get("state", "open")
        labels    = [l["name"] for l in issue.get("labels", [])]
        created   = (issue.get("created_at") or "")[:10]
        updated   = (issue.get("updated_at") or "")[:10]
        url       = issue.get("html_url", "")
        assignees = [a["login"] for a in issue.get("assignees", [])]

        # Map GitHub state/labels to DocumentType
        doc_type = "context"
        if any(l in ("bug", "fix") for l in labels):
            doc_type = "note"
        elif any(l in ("enhancement", "feature") for l in labels):
            doc_type = "product"

        frontmatter = self._frontmatter({
            "project":    self.project,
            "type":       doc_type,
            "status":     "approved" if state == "closed" else "draft",
            "updated_at": updated,
            "tags":       ["github-issue"] + labels[:5],
            "owner":      assignees[0] if assignees else None,
        })

        content = f"{frontmatter}\n\n# Issue #{number}: {title}\n\n"
        if url:
            content += f"**Source:** [{url}]({url})  \n"
        content += f"**State:** {state}  \n**Created:** {created}  \n\n"
        if body.strip():
            content += f"## Description\n\n{body.strip()}\n"

        return ConnectorResult(
            filename   = f"ISSUE-{number:04d}-{self._slugify(title)}.md",
            content    = content,
            source_url = url,
            title      = f"Issue #{number}: {title}",
            doc_type   = doc_type,
        )

    # ------------------------------------------------------------------
    # Wiki
    # ------------------------------------------------------------------

    def _fetch_wiki(self) -> list[ConnectorResult]:
        """
        Fetch wiki pages via the GitHub REST API (requires wiki to be enabled).
        Falls back to scraping the wiki git repo if API unavailable.
        """
        try:
            import urllib.request
            # GitHub doesn't expose a clean wiki pages API — use git clone approach
            # For MVP: fetch the sidebar/home page only via raw URL
            owner, repo = self.repo.split("/", 1)
            home_url = f"https://raw.githubusercontent.com/wiki/{owner}/{repo}/Home.md"
            req = urllib.request.Request(home_url, headers=self._headers())
            with urllib.request.urlopen(req, timeout=10) as resp:
                home_content = resp.read().decode("utf-8")

            frontmatter = self._frontmatter({
                "project":    self.project,
                "type":       "architecture",
                "status":     "approved",
                "updated_at": time.strftime("%Y-%m-%d"),
                "tags":       ["github-wiki", "documentation"],
            })

            content = f"{frontmatter}\n\n{home_content}"
            return [ConnectorResult(
                filename   = "wiki-home.md",
                content    = content,
                source_url = f"https://github.com/{self.repo}/wiki",
                title      = f"{self.repo} Wiki — Home",
                doc_type   = "architecture",
            )]

        except Exception as exc:
            logger.debug("Wiki fetch failed (may not be enabled): %s", exc)
            return []

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict:
        h = {"Accept": "application/vnd.github.v3+json",
             "User-Agent": "ContextOS/1.2"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _api_get(self, url: str) -> Optional[list]:
        import urllib.request, urllib.error, json as _json
        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(url, headers=self._headers())
                with urllib.request.urlopen(req, timeout=15) as resp:
                    return _json.loads(resp.read())
            except urllib.error.HTTPError as e:
                if e.code == 403:
                    logger.warning("GitHub rate limit hit — try setting GITHUB_TOKEN")
                    return None
                if e.code == 404:
                    logger.warning("Repo not found or not accessible: %s", self.repo)
                    return None
                logger.warning("HTTP %d on attempt %d", e.code, attempt + 1)
                time.sleep(2 ** attempt)
            except Exception as exc:
                logger.warning("Request failed: %s", exc)
                time.sleep(1)
        return None

    @staticmethod
    def _slugify(text: str) -> str:
        import re
        s = re.sub(r"[^\w\s-]", "", text.lower())
        return re.sub(r"[\s_-]+", "-", s).strip("-")[:40]
