import os
import json
import time
import logging
from typing import Optional
import requests
import jwt
from fastapi import FastAPI, Request, HTTPException, Header, Response, status
from signature import verify_signature

# Load env file locally if present (ignored in production Render env)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="GitHub Issue-to-PR Webhook Receiver")

# Configuration from environment variables
WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET")
GITHUB_APP_ID = os.environ.get("GITHUB_APP_ID")
GITHUB_APP_PRIVATE_KEY = os.environ.get("GITHUB_APP_PRIVATE_KEY")

def get_installation_token(installation_id: str) -> str:
    """Generates an installation access token using the GitHub App private key."""
    if not (GITHUB_APP_ID and GITHUB_APP_PRIVATE_KEY):
        raise ValueError("Missing GITHUB_APP_ID or GITHUB_APP_PRIVATE_KEY in server environment.")
        
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 600,
        "iss": GITHUB_APP_ID
    }
    # Sign JWT with App private key PEM
    jwt_token = jwt.encode(payload, GITHUB_APP_PRIVATE_KEY, algorithm="RS256")
    
    url = f"https://api.github.com/app/installations/{installation_id}/access_tokens"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Accept": "application/vnd.github+json"
    }
    
    res = requests.post(url, headers=headers)
    if res.status_code != 201:
        raise RuntimeError(f"Failed to generate installation token: {res.text}")
    return res.json()["token"]

def dispatch_github_action(repo_full_name: str, token: str, task_payload: dict):
    """Triggers the repository_dispatch workflow event in the repository."""
    url = f"https://api.github.com/repos/{repo_full_name}/dispatches"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    body = {
        "event_type": "trigger-agent",
        "client_payload": {
            "payload": json.dumps(task_payload)
        }
    }
    res = requests.post(url, headers=headers, json=body)
    if res.status_code != 204:
        raise RuntimeError(f"Failed to dispatch GitHub Action: {res.text}")
    logger.info(f"Successfully triggered repository dispatch for {repo_full_name}")

@app.get("/health")
def health_check():
    return {"status": "ok"}

@app.post("/webhook")
async def webhook_receiver(
    request: Request,
    x_github_event: str = Header(...),
    x_hub_signature_256: str = Header(...)
):
    # Read raw body for signature verification
    body = await request.body()
    
    # 1. Signature validation
    if not WEBHOOK_SECRET:
        logger.warning("GITHUB_WEBHOOK_SECRET is not configured. Skipping verification.")
    else:
        if not verify_signature(body, x_hub_signature_256, WEBHOOK_SECRET):
            logger.error("Signature verification failed.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature"
            )
            
    # 2. Parse payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload"
        )
        
    logger.info(f"Received GitHub event: {x_github_event}")
    
    # 3. Filter trigger criteria
    trigger_detected = False
    repo_info = payload.get("repository", {})
    repo_url = repo_info.get("clone_url")
    repo_full_name = repo_info.get("full_name")
    installation_id = payload.get("installation", {}).get("id")
    
    task_payload = {
        "event_type": x_github_event,
        "repo_url": repo_url,
        "repo_full_name": repo_full_name,
        "installation_id": installation_id,
    }
    
    if x_github_event == "issues":
        action = payload.get("action")
        issue = payload.get("issue", {})
        label_name = payload.get("label", {}).get("name", "")
        
        # Trigger when label "@agent fix" is added
        is_labeled_trigger = (action == "labeled" and label_name == "@agent fix")
        
        if is_labeled_trigger:
            trigger_detected = True
            task_payload.update({
                "issue_number": issue.get("number"),
                "title": issue.get("title"),
                "body": issue.get("body"),
                "type": "issue"
            })
            
    elif x_github_event == "issue_comment":
        action = payload.get("action")
        comment = payload.get("comment", {})
        comment_body = comment.get("body", "")
        issue = payload.get("issue", {})
        
        # Trigger on comment containing "@agent fix"
        is_created_or_edited = action in ("created", "edited")
        has_trigger_phrase = "@agent fix" in comment_body
        
        if is_created_or_edited and has_trigger_phrase:
            trigger_detected = True
            task_payload.update({
                "issue_number": issue.get("number"),
                "title": issue.get("title"),
                "body": issue.get("body"),
                "comment_body": comment_body,
                "type": "pr" if "pull_request" in issue else "issue"
            })
            
    # 4. Dispatch to GitHub Actions if triggered
    if trigger_detected:
        try:
            # Generate the short-lived installation access token
            token = get_installation_token(str(installation_id))
            
            # Dispatch trigger-agent event to target repository
            dispatch_github_action(repo_full_name, token, task_payload)
            
            return {"status": "dispatched", "task": task_payload}
        except Exception as e:
            logger.error(f"Failed to dispatch event to GitHub Actions: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to trigger workflow: {str(e)}"
            )
            
    return {"status": "ignored", "reason": "event did not match trigger criteria"}
