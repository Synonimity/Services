# synon_usage_tracker

Tracks per-user token usage and cost, and enforces plan-based quotas.

**Convention:** importable Python package, not a standalone service.

## Setup

1. Copy this folder into your project.
2. Add dependencies from `requirements.snippet.txt`.
3. Run `schema.sql` against your project's Supabase instance if using the Supabase backend.

## Usage

```python
from synon_usage_tracker import UsageTrackerConfig, UsageTrackerService, InMemoryBackend

config = UsageTrackerConfig()
tracker = UsageTrackerService(config, backend=InMemoryBackend())

# Record usage
tracker.record(user_id="user_123", model="claude-3-5-sonnet-20240620", input_tokens=100, output_tokens=200)

# Check quota
quota = tracker.check_quota(user_id="user_123")
if not quota.within_limit:
    print(f"Quota exceeded: {quota.reason}")
```
