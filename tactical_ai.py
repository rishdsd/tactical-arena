
import threading
import time

from collections import Counter

from logger import log
from ollama_client import choose_tactical_action


class TacticalAI:
    def __init__(self, decision_interval=2.0):
        self.decision_interval = decision_interval
        self.last_request_at = 0.0
        self.request_in_progress = False

        self.latest_decision = None
        self.lock = threading.Lock()
        self.stats = Counter()  # ok / failed / requests

    def request_decision(self, observation):
        now = time.monotonic()

        with self.lock:
            if self.request_in_progress:
                return

            if now - self.last_request_at < self.decision_interval:
                return

            self.request_in_progress = True
            self.stats["requests"] += 1
            self.last_request_at = now

        thread = threading.Thread(
            target=self._run_decision,
            args=(observation,),
            daemon=True,
        )
        thread.start()

    
    def _run_decision(self, observation):
        try:
            decision = choose_tactical_action(observation)

            if decision is not None:
                with self.lock:
                    self.latest_decision = decision
                self.stats["ok"] += 1
            else:
                self.stats["failed"] += 1
        except Exception as exc:
            self.stats["failed"] += 1
            log.debug(f"[TacticalAI] unexpected error: {type(exc).__name__}: {exc}")
        finally:
            with self.lock:
                self.request_in_progress = False

    def get_latest_decision(self):
        with self.lock:
            decision = self.latest_decision
            self.latest_decision = None
            return decision
