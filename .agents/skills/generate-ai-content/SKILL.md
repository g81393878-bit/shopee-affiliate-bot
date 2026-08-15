---
name: generate-ai-content
description: >-
  Runs the local AI content generation pipeline for products missing content in the Shopee Affiliate bot.
  Use when the user asks to "เขียนคอนเทนต์", "generate AI content", or fill the content backlog using Groq.
---

# Generate AI Content (Local Pipeline)

## Overview
This skill executes the local `product_pipeline.py analyze` script to generate high-quality AI sales scripts (hook, problem, solution, CTA) for products that lack content. It automatically uses the `GROQ_API_KEY` from the environment.

## Dependencies
- `content-backfill` (for context on how content relates to the database and dashboard).

## Workflow

### 1. Set Environment Encoding
Because the pipeline processes Thai text, you must ensure the terminal uses UTF-8 encoding.
- Set the environment variable: `$env:PYTHONIOENCODING="utf-8"`

### 2. Reload Environment Variables (Important)
If Groq keys were recently updated in `.env`, ensure you run the script with `python` or load the variables explicitly, as the agent's background shell might hold stale keys.

### 3. Run the Pipeline
Execute the analysis pipeline. By default, this will process a small batch.
```bash
$env:PYTHONIOENCODING="utf-8"; python tools/product_pipeline.py analyze
```

### 4. Error Handling & Rate Limits
- **429 Rate Limit**: The script has built-in failover. If all Groq keys hit the 100K token/day limit, the script will automatically catch the error and fall back to using non-AI templates (`build_template_script()`) so the queue continues processing. **Do not stop or crash**; just let the script finish its fallback mechanism.
