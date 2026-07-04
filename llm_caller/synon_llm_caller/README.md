# synon_llm_caller

Minimal microservice for calling an LLM API. Provider/model/endpoint are
all configurable via Pydantic settings so this same script can point at
Anthropic, OpenAI-compatible, or any other Bearer-token JSON API.

**Convention:** importable Python package, not a standalone service.

## Setup

1. Copy this folder into your project.
2. Add dependencies from `requirements.snippet.txt`.
3. Set `LLM_API_KEY` in your environment.

## Usage

```python
from synon_llm_caller import LLMCallerConfig, LLMCallerService

config = LLMCallerConfig(api_key="your-key")
service = LLMCallerService(config)

reply = service.call("Say hello in one sentence.")
print(reply)
```
