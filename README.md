# Autonomous GitHub Issue-to-PR Agent

This repository contains the source code for an autonomous, self-hosted software engineering agent designed to automatically resolve GitHub issues. The system securely ingests GitHub webhook events, provisions isolated microVM sandboxes, executes a Reasoning-Action (ReAct) loop using LLMs, verifies edits through automated test suites, and submits validated Pull Requests back to your codebases.

The architecture is configured to run entirely within free-tier cloud services, utilizing FastAPI for webhook reception, GitHub Actions for orchestrator execution, E2B Cloud for code sandboxing, and Google Gemini for model reasoning.

---

## Architecture Overview

1. **Trigger**: A user adds the `@agent fix` label or comments on a GitHub issue.
2. **Ingestion**: A FastAPI web server (hosted on Render) receives the webhook, cryptographically validates the signature, and dispatches a trigger to the control repository.
3. **Execution**: A GitHub Actions workflow is triggered. It boots a runner VM, pulls the codebase, and executes the orchestrator script.
4. **Sandboxing**: The orchestrator provisions an isolated E2B microVM sandbox and clones the target repository inside it to protect system secrets and resources.
5. **ReAct Loop**: The orchestrator interacts with the Google Gemini API to identify the bug, read files, apply edits, and execute terminal commands.
6. **Validation**: The orchestrator runs the repository's test suite inside the E2B sandbox and computes test coverage.
7. **Delivery**: If tests pass and safety policies are met, the orchestrator pushes the fix branch and opens a Pull Request with a full reasoning summary.

---

## Repository Structure

* `webhook-receiver/` - FastAPI web service that receives and validates GitHub webhook triggers.
* `worker/` - Core agent logic, tools, verification runners, and safety diff guards.
* `eval/` - Local offline benchmarking suite to test agent performance against seed issues.
* `.github/workflows/` - GitHub Actions runner configuration for orchestrating cloud runs.
* `infra/` - Enterprise Terraform configurations for alternate AWS-based deployments.

---

## Configuration

Copy the `.env.example` file to `.env` and fill in the required credentials:

```bash
cp .env.example .env
```

### Required Keys

* `E2B_API_KEY`: API credential key from E2B (e2b.dev) to manage sandbox VMs.
* `GEMINI_API_KEY`: API credential key from Google AI Studio to run model reasoning.
* `LLM_PROVIDER`: Set to `gemini`.
* `LLM_MODEL`: Set to `gemini-2.5-flash`.

---

## Verification & Testing

### 1. Local Offline Evaluation
To test the agent's logic locally using pre-configured mock issues without triggering GitHub webhooks:

1. Ensure the required keys are populated in your local `.env` file.
2. Install the Python dependencies:
   ```bash
   pip install -r worker/requirements.txt python-dotenv
   ```
3. Run the evaluation script:
   ```bash
   python eval/run_eval.py
   ```
This will spin up a local E2B sandbox, inject a test python codebase, let the agent resolve the bug, verify the test results, and output the benchmark metrics.

### 2. Cloud Workflow Secrets Configuration
For live GitHub integration, add the following repository secrets to your control repository settings under **Settings -> Secrets and variables -> Actions**:

* `E2B_API_KEY` - E2B Sandbox API Key.
* `GEMINI_API_KEY` - Google Gemini API Key.
* `APP_ID` - GitHub App ID.
* `INSTALLATION_ID` - GitHub App Installation ID.
* `APP_PRIVATE_KEY` - Contents of the downloaded private key PEM file.
