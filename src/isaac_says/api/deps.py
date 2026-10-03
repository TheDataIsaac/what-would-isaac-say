"""The things the API creates once at startup (agent, search index, database) and shares."""

from dataclasses import dataclass

from fastapi import Request

from isaac_says.agent.service import ChatService
from isaac_says.api.limiter import SlidingWindowLimiter
from isaac_says.api.schemas import PostSummary
from isaac_says.config import Settings
from isaac_says.db.repository import Repository
from isaac_says.retrieval.index import VectorIndex


@dataclass
class Resources:
    settings: Settings
    chat: ChatService
    index: VectorIndex
    repo: Repository
    limiter: SlidingWindowLimiter
    posts: list[PostSummary]


def get_resources(request: Request) -> Resources:
    return request.app.state.resources
