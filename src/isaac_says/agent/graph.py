"""How the agent's steps are connected. The flow:

START -> route -+-> chitchat ------------------------------------------------> END
                |
                +-> rewrite_query -> retrieve -+-> grade -+-> write_answer -> verify -> END
                |        ^                     |          |
                |        |                     |          +-> write_review -> verify -> END
                |        |                     |          |
                +-> info_check                 +----------+-> not_covered -------> END
                      |  ^
                      v  |
                    ask_user   (pauses the graph until the user answers)
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from isaac_says.agent.nodes import AgentNodes
from isaac_says.agent.state import AgentState


# These small functions choose the next step.
def _by_intent(state: AgentState) -> str:
    return {"chitchat": "chitchat", "review": "info_check"}.get(state["intent"], "rewrite_query")


def _needs_answer_from_user(state: AgentState) -> str:
    return "ask_user" if state.get("pending_question") else "rewrite_query"


def _has_candidates(state: AgentState) -> str:
    # Nothing passed the similarity cutoff, so refuse without calling the model.
    return "grade" if state["candidates"] else "not_covered"


def _after_grade(state: AgentState) -> str:
    if not state["relevant"]:
        return "not_covered"
    return "write_review" if state["intent"] == "review" else "write_answer"


def build_graph(
    nodes: AgentNodes, checkpointer: BaseCheckpointSaver | None = None
) -> CompiledStateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("route", nodes.route)
    graph.add_node("chitchat", nodes.chitchat)
    graph.add_node("info_check", nodes.info_check)
    graph.add_node("ask_user", nodes.ask_user)
    graph.add_node("rewrite_query", nodes.rewrite_query)
    graph.add_node("retrieve", nodes.retrieve)
    graph.add_node("grade", nodes.grade)
    graph.add_node("write_answer", nodes.write_answer)
    graph.add_node("write_review", nodes.write_review)
    graph.add_node("verify", nodes.verify)
    graph.add_node("not_covered", nodes.not_covered)

    graph.add_edge(START, "route")
    graph.add_conditional_edges("route", _by_intent, ["chitchat", "info_check", "rewrite_query"])
    graph.add_edge("chitchat", END)

    graph.add_conditional_edges(
        "info_check", _needs_answer_from_user, ["ask_user", "rewrite_query"]
    )
    graph.add_edge("ask_user", "info_check")  # after the user answers, check again

    graph.add_edge("rewrite_query", "retrieve")
    graph.add_conditional_edges("retrieve", _has_candidates, ["grade", "not_covered"])
    graph.add_conditional_edges(
        "grade", _after_grade, ["write_answer", "write_review", "not_covered"]
    )
    graph.add_edge("write_answer", "verify")
    graph.add_edge("write_review", "verify")
    graph.add_edge("verify", END)
    graph.add_edge("not_covered", END)

    # The checkpointer saves the conversation, so it continues between messages.
    return graph.compile(checkpointer=checkpointer)
