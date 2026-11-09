"""HTTP client for the simulator with explicit retry semantics.

* Reads are retried on transport errors and 5xx with backoff.
* Writes that carry an idempotency key (proposal_id) are retried too; a 409 duplicate on a retry is
  resolved by the caller via reconciliation (it means the first attempt landed).
* `advance_to` never blindly re-POSTs: after a failure it re-reads the sim clock first, so a timeout
  that actually advanced the world can't advance it twice.
* Credit-spending calls (LLM, validation) are *not* retried after an ambiguous failure.
* 4xx are returned to the caller as ApiError with the simulator's error code.
"""
from __future__ import annotations

import logging
import time

import httpx

log = logging.getLogger("controller.sim")


class ApiError(Exception):
    def __init__(self, status: int, code: str, detail):
        super().__init__(f"{status} {code}: {detail}")
        self.status, self.code, self.detail = status, code, detail


class Sim:
    def __init__(self, url: str, timeout: float = 600.0):
        self.url = url.rstrip("/")
        self.c = httpx.Client(base_url=self.url, timeout=httpx.Timeout(timeout, connect=10.0))
        self.calls = 0

    def wait_ready(self, max_wait_s: float = 1800):
        t0 = time.time()
        while True:
            try:
                if self.c.get("/health").status_code == 200:
                    return
            except httpx.TransportError:
                pass
            if time.time() - t0 > max_wait_s:
                raise RuntimeError(f"simulator at {self.url} not ready after {max_wait_s}s")
            time.sleep(1.0)

    def _req(self, method: str, path: str, *, retry: bool = True, tries: int = 8, **kw) -> httpx.Response:
        delay = 0.5
        for attempt in range(tries):
            self.calls += 1
            try:
                r = self.c.request(method, path, **kw)
            except httpx.TransportError as e:
                if not retry or attempt == tries - 1:
                    raise
                log.warning("transport error on %s %s (%s); retrying in %.1fs", method, path, e, delay)
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            if r.status_code >= 500 and retry and attempt < tries - 1:
                log.warning("%s on %s %s; retrying in %.1fs", r.status_code, method, path, delay)
                time.sleep(delay)
                delay = min(delay * 2, 30)
                continue
            if r.status_code >= 400:
                try:
                    body = r.json()
                except ValueError:
                    body = {"error": "http_%d" % r.status_code, "detail": r.text[:500]}
                raise ApiError(r.status_code, body.get("error") or str(body.get("detail")), body.get("detail"))
            return r
        raise RuntimeError("unreachable")

    # ---------------------------------------------------------------- reads
    def state(self) -> dict:
        return self._req("GET", "/sim/state").json()

    def workflows(self) -> list[dict]:
        return self._req("GET", "/workflows").json()

    def config(self, wid: str) -> dict:
        return self._req("GET", f"/workflows/{wid}/config").json()

    def config_history(self, wid: str) -> list[dict]:
        return self._req("GET", f"/workflows/{wid}/config/history").json()

    def chunks(self, kind: str, after: int) -> list[dict]:
        return self._req("GET", "/events/chunks", params={"kind": kind, "after": after}).json()

    def chunk(self, n: int) -> bytes:
        return self._req("GET", f"/events/chunks/{n}").content

    def approval(self, aid: str) -> dict:
        return self._req("GET", f"/approvals/{aid}").json()

    def approvals(self, workflow_id: str | None = None, status: str | None = None) -> list[dict]:
        p = {k: v for k, v in (("workflow_id", workflow_id), ("status", status)) if v}
        return self._req("GET", "/approvals", params=p).json()

    # ---------------------------------------------------------------- writes
    def advance_to(self, target_minute: int) -> dict:
        """Advance to `target_minute`, safe against ambiguous failures."""
        for attempt in range(8):
            st = self.state()
            if st["finished"] or st["sim_minute"] >= target_minute:
                return st
            try:
                return self._req("POST", "/sim/advance", json={"minutes": target_minute - st["sim_minute"]},
                                 retry=False).json()
            except httpx.TransportError as e:
                log.warning("advance failed (%s); re-reading clock", e)
                time.sleep(min(2 ** attempt, 30))
            except ApiError as e:
                if e.code == "finished":
                    return self.state()
                raise
        raise RuntimeError("could not advance the simulator")

    def request_approval(self, body: dict) -> dict:
        return self._req("POST", "/approvals", json=body).json()

    def auto_apply(self, wid: str, body: dict) -> dict:
        return self._req("PUT", f"/workflows/{wid}/config", json=body).json()

    def apply(self, wid: str, aid: str) -> dict:
        return self._req("POST", f"/workflows/{wid}/apply", json={"approval_id": aid}).json()

    def suggest_fixes(self, wid: str, problem: str) -> dict:
        return self._req("POST", "/llm/suggest-fixes", json={"workflow_id": wid, "problem": problem},
                         retry=False).json()

    def validate(self, wid: str, prompt: str, n: int) -> dict:
        return self._req("POST", "/validation/runs", json={"workflow_id": wid, "prompt_version": prompt, "n": n},
                         retry=False).json()
