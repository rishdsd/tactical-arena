from ollama_client import choose_tactical_action

observation = {
    "bot_hp": 20,
    "health": "critical",
    "experience_tier": "veteran",
    "enemy_visible_now": True,
    "seconds_since_enemy_seen": 0.0,
    "enemy_distance": 150,
    "enemy_hp": 100,
    "visible_enemy_count": 1,
    "ally_alive": True,
    "rules_suggest": "cover_peek",
    "available_actions": ["attack", "cover_peek", "flank"],
}

decision = choose_tactical_action(observation)
print("Observation:", observation)
print("Decision:", decision)

assert decision is not None, "Ollama did not return a valid decision."
assert decision["action"] in observation["available_actions"]
print("Client test passed.")
