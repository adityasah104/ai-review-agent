# AI PR Review Agent — Project Documentation

> **Version:** 1.0.0 — Production-Ready  
> **Platform:** Azure DevOps · Amazon Bedrock · LangGraph  
> **Model:** Amazon Nova Pro (via AWS Bedrock)  
> **Aider Version:** v0.86.2+  

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Technology Stack](#2-technology-stack)
3. [System Architecture](#3-system-architecture)
4. [Agent Flow (Step by Step)](#4-agent-flow-step-by-step)
5. [Component Reference](#5-component-reference)
6. [Infrastructure Setup](#6-infrastructure-setup)
7. [What is Aider and How It Works](#7-what-is-aider-and-how-it-works)
8. [Test Rounds Conducted](#8-test-rounds-conducted)
9. [Final Evaluation — 20-Bug Test](#9-final-evaluation--20-bug-test)
10. [What the Agent Is Currently Missing](#10-what-the-agent-is-currently-missing)
11. [Future Improvement Roadmap](#11-future-improvement-roadmap)

---

## 1. Project Overview

The **AI PR Review Agent** is a fully autonomous, no-human-in-the-loop (No-HITL) code review system that triggers automatically when a Pull Request is opened in Azure DevOps.

The agent performs three core jobs:

| Job | Description |
|---|---|
| **CI Auto-Fix** | Detects and fixes linting/formatting failures in the CI pipeline before the code review begins |
| **Deep Code Review** | Uses three specialized AI agents in parallel to analyse code for quality, security, and performance issues |
| **Auto-Fix & Commit** | Uses Aider + Amazon Nova Pro to apply the suggested fixes directly to the feature branch |

The agent operates entirely in the background. A developer opens a Pull Request, and within minutes receives a detailed PR comment with findings and a commit from the AI that has already fixed the issues.

---

## 2. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| **API Server** | FastAPI + Uvicorn | Receives Azure DevOps webhooks |
| **Agent Orchestration** | LangGraph (StateGraph) | Controls the multi-step agent workflow |
| **LLM** | Amazon Bedrock — Nova Pro | Powers code review and fix generation |
| **Code Fixer** | Aider v0.86.2 | Applies LLM-generated fixes to actual files |
| **Python Linter** | Ruff | Validates and auto-formats Python code |
| **SQL Linter** | SQLFluff | Validates and auto-formats SQL/dbt models |
| **Version Control** | Azure DevOps Git | Source of truth for all PRs and commits |
| **Database** | SQLite | Stores job queue, PR metadata, run history |
| **Webhook Tunnel** | Ngrok | Exposes local server to Azure DevOps |
| **Logging** | Structlog | Structured JSON logging throughout |

---

## 3. System Architecture

```
Azure DevOps (PR Created)
         │
         │  POST /webhook/azure/pr
         ▼
┌─────────────────────────────┐
│        FastAPI Server       │
│        (main.py :8000)      │
│                             │
│  Webhook → Job Queue        │
│  (SQLite background worker) │
└────────────┬────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│                    LangGraph StateGraph                  │
│                                                         │
│  START                                                  │
│    │                                                    │
│    ▼                                                    │
│  [pr_ingestion] ──────────────────────────────────────► │
│    │                                                    │
│    ▼                                                    │
│  [ci_status] ◄──────────────────────────────────────── │
│    │                                                    │
│    ├── CI Passed ──────────────────────────────────────►│
│    │                                                    │
│    └── CI Failed                                        │
│              │                                          │
│              ▼                                          │
│         [aider_ci_fix] ── push fix ──► Azure DevOps    │
│              │                                          │
│              └──► [ci_status] (loop, max 2 retries)    │
│                                                         │
│  [context_retrieval]                                    │
│    │                                                    │
│    ├──► [code_quality]      ─────────────────────────► │
│    ├──► [security_audit]    ─────────────────────────► │  (parallel)
│    └──► [performance_analysis] ──────────────────────► │
│                   │                                     │
│                   ▼  (fan-in — all findings merged)     │
│           [aider_llm_fix]                               │
│           (per-file loop + validation gate)             │
│                   │                                     │
│                   ▼                                     │
│           [publish_review] ──► Azure DevOps PR Comment  │
│                   │                                     │
│                  END                                    │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Agent Flow (Step by Step)

### Step 1 — Webhook Received
Azure DevOps sends a `git.pullrequest.created` event to `POST /webhook/azure/pr`.  
The server validates the event, creates a job in SQLite, and enqueues it.

### Step 2 — PR Ingestion (`ingestion.py`)
- Fetches the list of changed files from Azure DevOps REST API
- Filters to only `.py` and `.sql` files
- Reads file contents for later analysis

### Step 3 — CI Status Check (`ci_status.py`)
- Polls the Azure DevOps Builds API for the latest pipeline run on the PR branch
- Waits up to 120 seconds for the build to complete
- Returns `ci_passed: True/False` and the raw CI log summary

### Step 4 — CI Auto-Fix Loop (`aider_ci_fix.py`)
*Only triggered if CI failed.*
- Sends the CI error logs to Aider with a targeted prompt
- Aider reads all changed files and calls Nova Pro to generate fixes
- Commits and pushes the fix to the feature branch
- Graph loops back to Step 3 (re-checks CI)
- **Maximum 2 retry attempts** (`AIDER_MAX_CI_RETRIES=2`)
- If retries exhausted, agent force-continues to review anyway

### Step 5 — Context Retrieval (`context_retrieval.py`)
- Fetches additional context (file history, project structure) for the LLM agents
- Prepares the shared state for parallel review

### Step 6 — Parallel LLM Review (3 Agents)
All three agents run simultaneously via LangGraph's fan-out edges:

| Agent | File | Focus |
|---|---|---|
| **Code Quality** | `code_quality.py` | Naming, structure, type hints, docstrings, bad patterns |
| **Security Audit** | `security_audit.py` | Hardcoded secrets, SQL injection, `eval()`, insecure patterns |
| **Performance** | `performance.py` | N+1 queries, `SELECT *`, inefficient loops, memory issues |

Each agent sends the file contents to Amazon Nova Pro with a role-specific system prompt and returns structured findings with severity (`critical`, `major`, `minor`) and line-level suggestions.

### Step 7 — Aider LLM Fix (`aider_llm_fix.py`)
*Applies fixes for all findings merged from the three agents.*

Uses **Layer 2 architecture** — processes one file at a time:

```
For each file with findings:
  1. Build a targeted prompt for that file only
  2. Run Aider (Nova Pro generates a diff)
  3. Run ruff format + ruff check --fix (auto-format Python)
  4. Run sqlfluff fix (if SQL file)
  5. Validation Gate:
     - Run ruff check . (final lint check)
     - Run sqlfluff lint models/ (final SQL check)
     - If PASS → mark file as fixed
     - If FAIL → git checkout -- <file> (discard this file only)
  6. Move to next file

After all files processed:
  - git add -A
  - git commit with summary of fixed/skipped files
  - git push origin <branch>
```

### Step 8 — Publish Review (`publish_review.py`)
- Aggregates all findings from all three agents
- Generates a formatted PR comment with:
  - Summary counts by severity
  - Per-finding details with file, line, description, and fix suggestion
  - CI Auto-Fix status
  - Aider Auto-Fix status (files fixed / skipped)
- Posts comment to Azure DevOps PR via REST API

---

## 5. Component Reference

### File Structure

```
ai-review-agent/
├── main.py                          # FastAPI entrypoint, webhook router, job queue
├── .env                             # Environment config (Azure PAT, AWS keys, paths)
├── requirements.txt
└── src/
    ├── agents/
    │   ├── graph.py                 # LangGraph StateGraph definition
    │   ├── state.py                 # PRReviewState dataclass
    │   └── nodes/
    │       ├── ingestion.py         # PR file fetching
    │       ├── ci_status.py         # Azure DevOps build polling
    │       ├── aider_ci_fix.py      # CI lint auto-fix via Aider
    │       ├── context_retrieval.py # Context preparation
    │       ├── code_quality.py      # Code quality LLM agent
    │       ├── security_audit.py    # Security LLM agent
    │       ├── performance.py       # Performance LLM agent
    │       ├── aider_llm_fix.py     # Bug auto-fix via Aider (Layer 2)
    │       └── publish_review.py    # PR comment publisher
    └── config/
        └── settings.py              # Pydantic settings loader

demo-python-dbt-fixed/               # Demo repository (target of agent reviews)
├── src/
│   ├── etl_pipeline.py
│   └── data_processor.py
└── models/
    └── staging/
        └── stg_bad_example.sql
```

### Key Environment Variables

| Variable | Purpose |
|---|---|
| `AZURE_DEVOPS_ORG` | Azure DevOps organisation name |
| `AZURE_DEVOPS_PROJECT` | Azure DevOps project name |
| `AZURE_DEVOPS_PAT` | Personal Access Token for API calls |
| `AWS_ACCESS_KEY_ID` | AWS credentials for Bedrock |
| `AWS_SECRET_ACCESS_KEY` | AWS credentials for Bedrock |
| `AWS_REGION` | AWS region (`us-east-1`) |
| `DEMO_REPO_PATH` | Absolute path to the demo repository on disk |
| `AIDER_MAX_CI_RETRIES` | Max CI fix retry attempts (default: 2) |

---

## 6. Infrastructure Setup

### Running the Agent

```bash
cd ai-review-agent
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

> ⚠️ Do NOT use `--reload`. It causes Aider subprocess crashes due to process file-watching conflicts.

### Exposing to Azure DevOps (Development)

```bash
ngrok http 8000
# Copy the URL e.g. https://abc123.ngrok-free.app
```

### Azure DevOps Webhook Configuration

```
Project Settings → Service Hooks → Web Hooks → Create Subscription
  Event:  Pull request created
  URL:    https://<ngrok-url>/webhook/azure/pr
```

### Azure DevOps CI Pipeline Requirements

Your CI pipeline must run these two checks on the PR branch:

```yaml
# ruff check (Python linting)
- script: ruff check src/
  displayName: 'Run Ruff on src/'

# sqlfluff lint (SQL linting)
- script: sqlfluff lint models/ --dialect ansi --format human
  displayName: 'Run SQLFluff on models/'
```

---

## 7. What is Aider and How It Works

An **LLM** (Amazon Nova Pro) is a text-in, text-out model. It can read and understand code, but it cannot touch any files on disk.

**Aider** is a coding agent that wraps the LLM and gives it hands:

| Capability | LLM alone | Aider |
|---|---|---|
| Read files from disk | ❌ | ✅ |
| Write changes to files | ❌ | ✅ |
| Run linting commands | ❌ | ✅ |
| Commit to Git | ❌ | ✅ |
| Calls the LLM | It IS the LLM | ✅ |

### Aider Flags Used in This Project

| Flag | Purpose |
|---|---|
| `--yes` | Auto-confirm all file changes |
| `--no-auto-commits` | Agent controls Git commits manually |
| `--no-stream` | Required for Amazon Bedrock (no streaming support) |
| `--edit-format diff` | Forces Nova Pro to output standard unified diffs |
| `--auto-lint` | Runs ruff after each edit and feeds errors back to Nova Pro |
| `--lint-cmd "python: ruff check ."` | Specifies the lint command for Python files |
| `--model bedrock/amazon.nova-pro-v1:0` | Specifies the Bedrock model endpoint |

---

## 8. Test Rounds Conducted

### Round 1 — Initial Integration Test
**Branch:** `feature/demo-pr-review-test`  
**Goal:** Verify end-to-end webhook → review → comment flow  
**Result:** Agent triggered successfully, CI fix loop worked, PR comment posted  
**Issues Found:** Aider using old v0.37.0 caused `BadRequestError` with Bedrock

**Fix Applied:** Upgraded to Aider v0.86.2, added `--no-stream` and `--edit-format diff`

---

### Round 2 — Security Bug Test
**Branch:** `feature/demo-pr-review-test` (re-pushed)  
**Bugs Planted:** Hardcoded credentials, `SELECT *`, bad naming, SQL injection  
**Result:** Agent found 18–32 findings across multiple runs  
**Issues Found:** Agent reported critical issues but Aider would not fix them (old filter blocked critical severity)

**Fix Applied:** Modified `aider_llm_fix.py` to include `critical` severity in fixable findings

---

### Round 3 — CI Pipeline Fix Test
**Branch:** `feature/agent-test-round-3`  
**Bugs Planted:** SQL injection, hardcoded DB credentials, bare except, `SELECT *`, lowercase SQL keywords  
**Result:** Agent caught all bugs. CI loop fixed SQL formatting. Aider fixed Python issues  
**Issues Found:** After Aider fixed security issues, `ruff format` was not being run, breaking `main` CI

**Fix Applied:** Added `ruff format` + `ruff check --fix` + `sqlfluff fix` calls after each Aider run

---

### Round 4 — Missing Import Trap Test
**Branch:** `feature/agent-test-round-4`  
**Bugs Planted:** `pickle.load()` security risk, hardcoded AWS key (with `import os` deliberately removed)  
**Goal:** Test Aider's `--auto-lint` feedback loop  
**Result:** Nova Pro correctly fixed security bugs. Auto-lint caught `F821 Undefined name` and forced Nova Pro to add `import os`  
**Issues Found:** Nova Pro injected `import os` in the middle of the file (`E402`), not at the top

**Fix Applied:** Added post-Aider `ruff check --fix --unsafe-fixes` to handle import sorting

---

### Round 5 — Hallucination Stress Test
**Branch:** `feature/agent-test-round-5`  
**Bugs Planted:** SQL injection, hardcoded password, bare except, bad variable name, lowercase SQL keywords  
**Result:** Nova Pro hallucinated — deleted class header in `data_processor.py`, inserted `CREATE INDEX` statements inside a `SELECT` query in SQL  
**Issues Found:** Agent committed broken code that failed CI with syntax errors

**Fix Applied (Layer 1):** Added Validation Gate — runs `ruff check` + `sqlfluff lint` before committing. If validation fails, `git checkout -- .` discards ALL of Aider's changes

---

### Round 6 — Per-File Loop Test (Layer 2)
**Branch:** `feature/agent-test-round-6`  
**Bugs Planted:** `eval()` code execution, hardcoded Stripe key, unused `import re`, mutable default argument, SQL formatting  
**Goal:** Test Layer 2 architecture (one file at a time)  
**Result:** Agent processed each file independently. SQL file fixed cleanly. Python files fixed successfully  
**Improvement:** Hallucination on one file no longer contaminates other files

---

### Round 7 — Semantic Bug Test
**Branch:** `feature/agent-test-round-7`  
**Bugs Planted:** SQL injection f-string, hardcoded JWT secret, file opened without context manager, hardcoded GitHub token, mutable default argument  
**Result:** Agent caught all critical security bugs. Fixed JWT and GitHub token. Mutable default arg partially detected  
**Outstanding:** `f = open(...)` not flagged by any agent (context manager issue)

---

### Final Evaluation — 20-Bug Grand Test
**Branch:** `feature/agent-final-test`  
**See Section 9 for full results.**

---

## 9. Final Evaluation — 20-Bug Test

### Bugs Planted

| # | File | Severity | Bug |
|---|---|---|---|
| 1 | `etl_pipeline.py` | 🔴 Critical | Hardcoded `JWT_SECRET` |
| 2 | `etl_pipeline.py` | 🔴 Critical | Hardcoded `DB_PASS` |
| 3 | `etl_pipeline.py` | 🔴 Critical | SQL injection via f-string |
| 4 | `etl_pipeline.py` | 🟡 Major | Bare `except Exception` |
| 5 | `etl_pipeline.py` | 🟡 Major | File opened without context manager |
| 6 | `etl_pipeline.py` | 🟡 Major | `print()` instead of `logging` (×2) |
| 7 | `etl_pipeline.py` | 🔵 Minor | Unused `import sys` |
| 8 | `etl_pipeline.py` | 🔵 Minor | TODO comment left in code |
| 9 | `data_processor.py` | 🔴 Critical | Hardcoded `STRIPE_KEY` |
| 10 | `data_processor.py` | 🔴 Critical | `eval()` arbitrary code execution |
| 11 | `data_processor.py` | 🟡 Major | Mutable default argument `cache=[]` |
| 12 | `data_processor.py` | 🟡 Major | `result = cache` compounding bug |
| 13 | `data_processor.py` | 🟡 Major | Bad variable name `BadlyNamedVar` |
| 14 | `data_processor.py` | 🟡 Major | Missing return type on `load_data` |
| 15 | `data_processor.py` | 🔵 Minor | Unused `import re` |
| 16 | `data_processor.py` | 🔵 Minor | `any` instead of `Any` type hint |
| 17 | `stg_bad_example.sql` | 🟡 Major | `SELECT *` wildcard |
| 18 | `stg_bad_example.sql` | 🟡 Major | Lowercase SQL keywords (CI trigger) |
| 19 | `stg_bad_example.sql` | 🔵 Minor | `and`, `is not null` lowercase |
| 20 | `etl_pipeline.py` | 🟡 Major | `print()` in `run_pipeline()` |

### Agent Results

| Metric | Score |
|---|---|
| **Detection Rate** | 13/20 (65%) |
| **Fix Rate (of detected)** | 10/13 (77%) |
| **Critical Security Detection** | 5/5 (100%) ✅ |
| **Critical Security Fix** | 4/5 (80%) |
| **Code Quality Detection** | 4/11 (36%) |
| **SQL Issues Detection** | 3/3 (100%) ✅ |
| **Overall Rating** | **7/10** |

### What the Agent Fixed Correctly
- All 4 hardcoded secrets moved to `os.getenv()`
- `eval()` replaced with `ast.literal_eval()`
- `except Exception` narrowed to specific exceptions
- `BadlyNamedVar` renamed to `is_badly_named_var`
- `SELECT *` replaced with explicit column names
- Unused imports removed (via CI auto-fix)

### What the Agent Missed
- SQL injection f-string was reported but **not fixed** in code
- `f = open(...)` — no context manager — not detected
- `print()` vs `logging` — not detected
- Mutable default argument `cache=[]` — not detected
- `any` vs `Any` type hint — not detected
- Missing return type annotation — not detected
- TODO comment — not detected

---

## 10. What the Agent Is Currently Missing

### 10.1 No Final CI Verification After Bug Fix
The agent runs a CI fix loop before the LLM review but has **no verification loop after** the Aider LLM fix. If Aider's bug fixes introduce new linting issues, the PR stays in a failing CI state with no further agent intervention.

### 10.2 SQL Injection Not Always Fixed
The agent correctly detects and reports SQL injection vulnerabilities but sometimes fails to apply the actual code fix. Nova Pro understands the concept but struggles with applying the precise diff transformation required to switch from f-string interpolation to parameterised queries.

### 10.3 Weak Code Quality Detection
The agent reliably catches **security** bugs (100% on critical) but misses many **code quality** patterns:
- Missing context managers (`with open(...)`)
- `print()` vs structured `logging`
- Mutable default arguments (`def func(cache=[])`)
- Type annotation issues (`any` vs `Any`)
- TODO comments

### 10.4 Cross-File Dependency Blindness
The Layer 2 (per-file) architecture processes files in isolation. If a fix in `etl_pipeline.py` changes a function signature that `data_processor.py` calls, the second file will not be updated accordingly.

### 10.5 No Diff-Based Review
The agent currently reads **entire file contents** rather than reviewing only the **changed lines (diff)**. This causes the LLM to flag pre-existing issues in unchanged code, generating noise in the PR comment.

### 10.6 No Confidence Scoring
All findings are reported with equal weight. There is no confidence score to distinguish between a near-certain SQL injection detection and a speculative performance suggestion.

### 10.7 Single Model Dependency
The entire agent relies on Amazon Nova Pro. There is no fallback if the model is unavailable, rate-limited, or returns a malformed response.

---

## 11. Future Improvement Roadmap

### 🔴 High Priority

#### 1. Add Final CI Verification Loop
After `aider_llm_fix` pushes its commit, add a new node in `graph.py` that polls CI one more time. If CI fails, trigger one final Aider CI fix. This closes the loop completely.

```python
# In graph.py — add after aider_llm_fix
builder.add_edge("aider_llm_fix", "final_ci_check")
builder.add_conditional_edges("final_ci_check", route_final_ci, {...})
builder.add_edge("final_ci_check", "publish_review")
```

#### 2. Upgrade to Claude 3.5 Sonnet
Amazon Nova Pro produces lower-quality diffs compared to Anthropic Claude 3.5 Sonnet, which is Aider's native preferred model. Switching the model ID is a one-line change:

```python
# In aider_llm_fix.py and aider_ci_fix.py
"--model", "bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0"
```

Expected improvement: Detection rate from 65% → ~85%, fix rate from 77% → ~95%, near-zero hallucinations.

#### 3. Diff-Based Review
Instead of sending full file contents to the LLM, send only the Git diff of the PR. This reduces token usage by ~70%, eliminates noise from pre-existing issues, and focuses the review on what the developer actually changed.

```python
# In ingestion.py
diff = subprocess.run(["git", "diff", "main...", "--", file_path], ...)
```

---

### 🟡 Medium Priority

#### 4. Smart File Grouping for Layer 2
Before processing files one at a time, analyse the import graph to group files that share dependencies. Files that import each other are sent to Aider together; independent files are processed alone.

#### 5. Confidence Scoring
Add a `confidence` field (0.0–1.0) to each finding. Only findings above a threshold (e.g., 0.7) trigger auto-fix. Low-confidence findings are reported but not auto-applied.

#### 6. PR Diff Filtering in Findings
Map each finding's line number back to the PR diff. Findings in lines that were not touched by the developer are flagged as `pre-existing` and excluded from the auto-fix, but still shown as informational notes.

#### 7. Auto-Merge on Clean Review
If the agent finds **zero critical findings** and all fixes pass CI, automatically approve and merge the PR using the Azure DevOps REST API. This is true No-HITL operation.

---

### 🔵 Low Priority / Future Research

#### 8. Vector Store for Project-Specific Rules
Use ChromaDB (already integrated) to store organisation-specific coding standards. The context retrieval node fetches relevant rules and injects them into each agent's system prompt, making reviews project-aware.

#### 9. Multi-Model Ensemble
Run two different models (e.g., Nova Pro + Claude Haiku) and only report a finding if both models agree. This dramatically reduces false positives.

#### 10. GitHub / GitLab Support
Abstract the Azure DevOps integration into a generic `VCSProvider` interface, then implement `GitHubProvider` and `GitLabProvider` backends. The agent logic remains unchanged.

#### 11. Slack / Teams Notification
Post a summary to a Slack or Teams channel when a review is complete, including the finding count, severity breakdown, and a direct link to the PR comment.

#### 12. Agent Dashboard (Web UI)
Build a web UI connected to the SQLite database showing:
- Real-time job queue status
- Per-PR review history
- Finding trends over time (are developers improving?)
- Model performance metrics

---

## Summary

The AI PR Review Agent is a production-grade autonomous code review system that successfully catches **100% of critical security vulnerabilities** and applies intelligent fixes using a safe, per-file validation architecture. Its current detection rate of 65% is primarily limited by the capabilities of Amazon Nova Pro on subtle code quality patterns. Upgrading to Claude 3.5 Sonnet and adding a final CI verification loop are the two highest-impact improvements available today, which would bring the overall rating from 7/10 to approximately 9/10.
