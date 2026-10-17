
import threading
import time

from ollama_client import choose_tactical_action


class TacticalAI:
    def __init__(self, decision_interval=2.0):
        self.decision_interval = decision_interval
        self.last_request_at = 0.0
        self.request_in_progress = False

        self.latest_decision = None
        self.lock = threading.Lock()

    def request_decision(self, observation):
        now = time.monotonic()

        with self.lock:
            if self.request_in_progress:
                return

            if now - self.last_request_at < self.decision_interval:
                return

            self.request_in_progress = True
            self.last_request_at = now

        thread = threading.Thread(
            target=self._run_decision,
            args=(observation,),
            daemon=True,
        )
        thread.start()

    
    def _run_decision(self, observation):
        started_at = time.monotonic()

        try:
            decision = choose_tactical_action(observation)

            if decision is not None:
                with self.lock:
                    self.latest_decision = decision

                print(
                    f"[TacticalAI] Decision ready in "
                    f"{time.monotonic() - started_at:.2f}s: "
                    f"{decision}",
                    flush=True,
                )
            else:
                print(
                    "[TacticalAI] No valid decision returned; "
                    "keeping the existing bot behavior.",
                    flush=True,
                )
        except Exception as exc:
            print(
                f"[TacticalAI] Unexpected error: "
                f"{type(exc).__name__}: {exc}",
                flush=True,
            )
        finally:
            with self.lock:
                self.request_in_progress = False


    def get_latest_decision(self):
        with self.lock:
            decision = self.latest_decision
            self.latest_decision = None
            return decision
