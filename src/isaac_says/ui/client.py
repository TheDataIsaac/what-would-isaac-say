"""Talks to the API for the Streamlit page. The page only uses the API, never the agent directly."""

from collections.abc import Iterable, Iterator

import httpx

# What to show on screen while each step runs.
STEP_LABELS = {
    "route": "Understanding your message",
    "chitchat": "Replying",
    "info_check": "Checking I have enough detail",
    "ask_user": "Asking you a question",
    "rewrite_query": "Preparing the search",
    "retrieve": "Searching the newsletter",
    "grade": "Checking the evidence",
    "write_answer": "Writing the answer",
    "write_review": "Reviewing your work",
    "verify": "Verifying every quote",
    "not_covered": "Checking what I can say",
}


class ApiError(Exception):
    """The API returned an error. The message is fine to show to a visitor."""


def parse_sse(lines: Iterable[str]) -> Iterator[tuple[str, dict]]:
    """Parse a Server-Sent Events stream into ``(event, data)`` pairs."""
    import json

    event, data = "message", ""
    for line in lines:
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            data = line.split(":", 1)[1].strip()
        elif not line.strip() and data:  # a blank line ends one event
            yield event, json.loads(data)
            event, data = "message", ""


def _raise_for_error(response: httpx.Response) -> None:
    if response.is_success:
        return
    try:
        detail = response.json().get("detail")
    except ValueError:
        detail = None
    if response.status_code == 401:
        raise ApiError("That admin key was not accepted.")
    if isinstance(detail, str):
        raise ApiError(detail)  # the API's own message, such as the daily limit being reached
    if response.status_code == 429:
        raise ApiError("You are sending messages too quickly. Please wait a moment.")
    raise ApiError(f"The server returned {response.status_code}.")


class ApiClient:
    def __init__(self, base_url: str, *, client: httpx.Client | None = None) -> None:
        self._http = client or httpx.Client(base_url=base_url, timeout=120.0)

    def stream_chat(
        self, message: str, thread_id: str | None, client_ip: str | None = None
    ) -> Iterator[tuple[str, dict]]:
        """Yield ("step", {...}) events, then one ("reply", {...}) event.

        ``client_ip`` is the visitor's address as seen by the web server. It is forwarded so the
        API can rate limit each visitor separately instead of limiting the UI as a whole.
        """
        payload = {"message": message, **({"thread_id": thread_id} if thread_id else {})}
        headers = {"X-Real-IP": client_ip} if client_ip else {}
        try:
            with self._http.stream(
                "POST", "/chat/stream", json=payload, headers=headers
            ) as response:
                if not response.is_success:
                    response.read()
                    _raise_for_error(response)
                for event, data in parse_sse(response.iter_lines()):
                    if event == "error":
                        raise ApiError(data.get("detail", "Something went wrong."))
                    yield event, data
        except httpx.TransportError as error:
            raise ApiError("Could not reach the assistant. Is the API running?") from error

    def delete_thread(self, thread_id: str) -> None:
        """Delete a conversation from the server."""
        try:
            _raise_for_error(self._http.delete(f"/chat/{thread_id}"))
        except httpx.TransportError as error:
            raise ApiError("Could not reach the assistant. Is the API running?") from error

    def send_feedback(self, request_id: str, rating: int) -> None:
        _raise_for_error(
            self._http.post("/feedback", json={"request_id": request_id, "rating": rating})
        )

    # ---- admin ------------------------------------------------------------------------------
    def admin_questions(self, api_key: str) -> list[dict]:
        response = self._http.get("/admin/questions", headers={"X-API-Key": api_key})
        _raise_for_error(response)
        return response.json()

    def admin_answer(self, api_key: str, question_id: int, answer: str) -> dict:
        response = self._http.post(
            f"/admin/questions/{question_id}/answer",
            headers={"X-API-Key": api_key},
            json={"answer": answer},
        )
        _raise_for_error(response)
        return response.json()

    def admin_stats(self, api_key: str) -> dict:
        response = self._http.get("/admin/stats", headers={"X-API-Key": api_key})
        _raise_for_error(response)
        return response.json()
