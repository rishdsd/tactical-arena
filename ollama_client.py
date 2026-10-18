import json
import urllib.request
import urllib.error
import time

from logger import log


OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:2b"


SYSTEM_PROMPT = """
You are the tactical planner for one bot in a 2D team shooter.
The bot has limited knowledge: it only knows where enemies were last seen,
not where they are now.

Choose exactly one action from available_actions:
- attack: advance on the enemy and shoot (normal combat).
- cover_peek: hide behind nearby cover, briefly peek out to shoot, return.
- flank: circle around to hit the enemy's last known position from a new
  angle. Good when the enemy has been hidden for a while and health is fine.

Guidance:
- health "critical" or "hurt": prefer cover_peek.
- health "healthy": prefer attack, or flank if the enemy has been out of
  sight for several seconds.
- If visible_enemy_count >= 2 and health is not "healthy": cover_peek.
- rules_suggest is a sensible default. Only deviate for a clear reason.
- Use the "health" word, not raw numbers, to judge health.

Return JSON: {"action": "<one of available_actions>", "reason": "max 12 words"}
"""


def choose_tactical_action(observation, timeout=8):
    """
    Ask the local Ollama model for one high-level action.
    Returns {"action", "target_id", "reason"} or None on any failure.
    """
    available_actions = observation.get("available_actions", [])
    if not available_actions:
        return None

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": "Battlefield observation:\n" + json.dumps(observation),
            },
        ],
        "stream": False,
        # A JSON schema forces valid output: the action must be one of the
        # allowed values, and truncated/malformed JSON can't happen.
        "format": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": list(available_actions)},
                "reason": {"type": "string"},
            },
            "required": ["action", "reason"],
        },
        "think": False,
        "options": {"temperature": 0, "num_predict": 120},
    }

    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started_at = time.monotonic()
    log.debug(f"[Ollama] request | HP={observation.get('bot_hp')}")

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            result = json.loads(response.read().decode("utf-8"))

        content = result.get("message", {}).get("content", "")
        decision = json.loads(content)
        action = decision.get("action")

        if action not in available_actions:
            log.debug(f"[Ollama] invalid action={action!r}")
            return None

        elapsed = time.monotonic() - started_at
        log.debug(f"[Ollama] {elapsed:.2f}s action={action} reason={decision.get('reason', '')}")

        return {
            "action": action,
            "target_id": None,
            "reason": str(decision.get("reason", ""))[:200],
            "latency": elapsed,
            # Keep the rule hint we sent, so logs can measure LLM-vs-rules agreement.
            "rules_suggest": observation.get("rules_suggest"),
        }

    except (urllib.error.URLError, TimeoutError, OSError, ValueError, TypeError) as exc:
        elapsed = time.monotonic() - started_at
        log.debug(f"[Ollama] failed after {elapsed:.2f}s | {type(exc).__name__}: {exc}")
        return None
