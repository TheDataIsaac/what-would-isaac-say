"""The Streamlit web page. Streamlit runs this file again on every click, so the conversation
is kept in st.session_state.
"""

import contextlib
import os

import streamlit as st

from isaac_says.ui.client import STEP_LABELS, ApiClient, ApiError

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000")
# The public site sets this to 0, so the admin page is not shown.
ENABLE_ADMIN_TAB = os.getenv("ENABLE_ADMIN_TAB", "1") == "1"

st.set_page_config(page_title="What Would Isaac Say?", page_icon="📊", layout="centered")


@st.cache_resource
def get_client() -> ApiClient:
    return ApiClient(API_URL)


client = get_client()

# Session state
if "history" not in st.session_state:
    st.session_state.history = []  # list of {"role", "text"?, "reply"?, "request_id"?}
    st.session_state.thread_id = None


def reset_conversation() -> None:
    """Start again, and delete the old conversation from the server."""
    if st.session_state.thread_id:
        with contextlib.suppress(ApiError):
            client.delete_thread(st.session_state.thread_id)
    st.session_state.history = []
    st.session_state.thread_id = None


# Showing replies
def render_source(citation: dict) -> None:
    label = (
        "Isaac's direct answer" if citation["source_type"] == "isaac_answer" else citation["title"]
    )
    with st.expander(f"{label} - {citation['heading']}"):
        st.markdown(f"> {citation['quote']}")
        if citation.get("url"):
            st.markdown(f"[Read the full post]({citation['url']})")


def render_reply(reply: dict) -> None:
    kind = reply["kind"]
    if kind == "answer":
        st.markdown(reply["text"])
        st.caption("Sources (each quote was checked against the original text)")
        for citation in reply["citations"]:
            render_source(citation)
    elif kind == "review":
        st.markdown(reply["summary"])
        for strength in reply["strengths"]:
            st.success(strength)
        for issue in reply["issues"]:
            with st.container(border=True):
                st.markdown(f"**{issue['title']}**")
                st.markdown(issue["problem"])
                st.markdown(f"**Try:** {issue['advice']}")
                render_source(issue["citation"])
        st.info(f"**Next step:** {reply['next_step']}")
    elif kind == "needs_input":
        st.markdown(reply["question"])
    elif kind == "not_covered":
        st.warning(reply["text"])
    else:  # chitchat
        st.markdown(reply["text"])


def send_feedback(request_id: str, key: str) -> None:
    """Called when a thumb is clicked (st.feedback gives 1 for up and 0 for down)."""
    value = st.session_state.get(key)
    if value is not None:
        # If sending fails, carry on with the conversation.
        with contextlib.suppress(ApiError):
            client.send_feedback(request_id, 1 if value == 1 else -1)


def render_history() -> None:
    for i, item in enumerate(st.session_state.history):
        with st.chat_message(item["role"]):
            if item["role"] == "user":
                st.markdown(item["text"])
                continue
            render_reply(item["reply"])
            if item["reply"]["kind"] in {"answer", "review"}:
                key = f"fb_{i}"
                st.feedback(
                    "thumbs", key=key, on_change=send_feedback, args=(item["request_id"], key)
                )


def visitor_address() -> str | None:
    """The visitor's IP address, as passed on by the proxy."""
    return st.context.headers.get("X-Real-IP")


def handle_message(message: str) -> None:
    st.session_state.history.append({"role": "user", "text": message})
    with st.chat_message("user"):
        st.markdown(message)
    with st.chat_message("assistant"):
        final = None
        try:
            with st.status("Working...", expanded=False) as status:
                for event, data in client.stream_chat(
                    message, st.session_state.thread_id, visitor_address()
                ):
                    if event == "step":
                        status.update(label=STEP_LABELS.get(data["node"], "Working..."))
                    else:
                        final = data
                status.update(label="Done", state="complete")
        except ApiError as error:
            st.error(str(error))
            return
        st.session_state.thread_id = final["thread_id"]
        st.session_state.history.append(
            {"role": "assistant", "reply": final["reply"], "request_id": final["request_id"]}
        )
        render_reply(final["reply"])
    st.rerun()  # redraw, so the thumbs appear under the new reply


# The two pages
def chat_page() -> None:
    """The chat page. st.chat_input must sit at the top level of the page to stay at the bottom."""
    st.title("What Would Isaac Say?")
    st.caption(
        "An AI assistant that answers using the *Explain the Data* newsletter. It relies only on "
        "what Isaac has written and shows the exact quotes. It is not Isaac."
    )
    with st.sidebar:
        st.button("New conversation", on_click=reset_conversation, use_container_width=True)
        st.markdown("**Try asking**")
        for example in (
            "When should I use a dual axis chart?",
            "Why do treemaps make ranking hard?",
            "How should I present a dashboard in a meeting?",
        ):
            if st.button(example, use_container_width=True):
                st.session_state.pending = example
        st.markdown("**Or share your work**")
        st.caption(
            "Describe a dashboard, chart or report and ask for a review. The assistant will "
            "ask one question if it needs more detail."
        )
        st.caption(
            "Please do not paste confidential data. Conversations are stored on the server so "
            "follow-up questions work; New conversation deletes yours. Questions the newsletter "
            "cannot answer are also saved for Isaac."
        )

    render_history()
    typed = st.chat_input("Ask a question, or describe your dashboard for a review")
    message = typed or st.session_state.pop("pending", None)
    if message:
        handle_message(message)


def admin_page() -> None:
    st.title("Admin")
    st.subheader("Question queue")
    st.caption("Questions readers asked that the newsletter does not cover, most asked first.")
    admin_key = st.text_input("Admin key", type="password")
    if not admin_key:
        return
    try:
        stats = client.admin_stats(admin_key)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Chats", stats["total_queries"])
        c2.metric("Open questions", stats["open_questions"])
        c3.metric("p95 latency", f"{stats['p95_latency_ms'] / 1000:.1f}s")
        c4.metric("Total cost", f"${stats['total_cost_usd']:.3f}")

        for question in client.admin_questions(admin_key):
            with st.container(border=True):
                st.markdown(f"**{question['question']}**")
                st.caption(f"Asked {question['times_asked']} time(s)")
                answer = st.text_area("Your answer", key=f"ans_{question['id']}", height=100)
                if st.button("Publish answer", key=f"pub_{question['id']}"):
                    try:
                        client.admin_answer(admin_key, question["id"], answer)
                        st.success("Saved. The assistant can now cite this answer.")
                        st.rerun()
                    except ApiError as error:
                        st.error(str(error))
    except ApiError as error:
        st.error(str(error))


view = "Chat"
if ENABLE_ADMIN_TAB:
    with st.sidebar:
        view = st.radio("View", ["Chat", "Admin"], horizontal=True, label_visibility="collapsed")

# This is a plain if, because Streamlit would print "None" for a one-line conditional.
if view == "Chat":
    chat_page()
else:
    admin_page()
