"""Builds the real agent from the settings."""

from langgraph.checkpoint.base import BaseCheckpointSaver

from isaac_says.agent.graph import build_graph
from isaac_says.agent.llm import OpenAIClient
from isaac_says.agent.nodes import AgentNodes, GapRecorder
from isaac_says.agent.service import ChatService
from isaac_says.config import Settings
from isaac_says.retrieval.embeddings import make_embeddings
from isaac_says.retrieval.index import VectorIndex


def build_chat_service(
    settings: Settings,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    gap_recorder: GapRecorder | None = None,
) -> tuple[ChatService, VectorIndex]:
    """Return the chat service and the search index it uses."""
    index = VectorIndex(settings.chroma_dir, make_embeddings(settings))
    nodes = AgentNodes(OpenAIClient(settings), index, settings, gap_recorder)
    return ChatService(build_graph(nodes, checkpointer), settings), index
