import os
import time
import logging
import requests
import jwt
from github import Github

logger = logging.getLogger(__name__)

class GitHubAppClient:
    """
    Handles authentication as a GitHub App and installation token generation.
    Wraps PyGithub to perform issue fetching, branch pushing (delegated),
    and PR operations.
    """
    def __init__(self, app_id: str = None, private_key: str = None, installation_id: str = None):
        self.app_id = app_id or os.environ.get("GITHUB_APP_ID")
        self.private_key = private_key or os.environ.get("GITHUB_APP_PRIVATE_KEY")
        self.installation_id = installation_id or os.environ.get("GITHUB_INSTALLATION_ID")
        
        self.token = None
        self.token_expiry = 0
        self.github_client = None

    def _generate_jwt(self) -> str:
        """Generates a signed JWT valid for 10 minutes."""
        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + 600,
            "iss": self.app_id
        }
        # Use RS256 algorithm to sign JWT with App's private key PEM
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def get_installation_token(self) -> str:
        """Fetches a short-lived App installation token (cached)."""
        now = time.time()
        if self.token and now < self.token_expiry - 60:
            return self.token
            
        logger.info(f"Generating access token for installation ID {self.installation_id}")
        jwt_token = self._generate_jwt()
        
        url = f"https://api.github.com/app/installations/{self.installation_id}/access_tokens"
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Accept": "application/vnd.github+json"
        }
        
        response = requests.post(url, headers=headers)
        if response.status_code != 201:
            raise RuntimeError(f"Failed to generate installation token: {response.text}")
            
        data = response.json()
        self.token = data["token"]
        # Parse expiry format (e.g. "2026-07-09T22:42:19Z")
        expires_at = data["expires_at"]
        struct_time = time.strptime(expires_at.replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
        self.token_expiry = time.mktime(struct_time) - time.timezone
        
        # Reset authenticated PyGithub instance
        self.github_client = Github(self.token)
        return self.token

    def get_github_client(self) -> Github:
        """Returns authenticated PyGithub client instance."""
        self.get_installation_token()
        return self.github_client

    def get_issue(self, repo_name: str, issue_number: int) -> dict:
        """Fetches the details of a GitHub issue."""
        client = self.get_github_client()
        repo = client.get_repo(repo_name)
        issue = repo.get_issue(issue_number)
        return {
            "title": issue.title,
            "body": issue.body or "",
            "is_pull_request": issue.pull_request is not None
        }

    def create_pull_request(self, repo_name: str, title: str, body: str, head: str, base: str = "main") -> int:
        """Creates a Pull Request on GitHub."""
        client = self.get_github_client()
        repo = client.get_repo(repo_name)
        pr = repo.create_pull(title=title, body=body, head=head, base=base)
        logger.info(f"Created Pull Request #{pr.number} in {repo_name}")
        return pr.number

    def add_labels_to_pr(self, repo_name: str, pr_number: int, labels: list):
        """Adds labels to a Pull Request or Issue."""
        client = self.get_github_client()
        repo = client.get_repo(repo_name)
        issue = repo.get_issue(pr_number)
        issue.add_to_labels(*labels)
        logger.info(f"Added labels {labels} to PR #{pr_number}")

    def post_pr_comment(self, repo_name: str, pr_number: int, comment: str):
        """Posts a comment on a PR/Issue thread."""
        client = self.get_github_client()
        repo = client.get_repo(repo_name)
        issue = repo.get_issue(pr_number)
        issue.create_comment(comment)
        logger.info(f"Posted comment on issue #{pr_number}")
