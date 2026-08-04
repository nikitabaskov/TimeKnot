"""Graph assembly."""

from __future__ import annotations

from zoneinfo import ZoneInfo

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from graph import nodes
from graph.llm import LLMClient
from graph.state import DialogState
from services.tasks import TaskService

PARSE_NODE = "parse"


def build_message_graph(
    llm: LLMClient,
    task_service: TaskService,
    timezone: ZoneInfo,
    checkpointer: BaseCheckpointSaver | None = None,
):
    builder = StateGraph(DialogState)
    builder.add_node(PARSE_NODE, nodes.make_parse_node(llm, timezone))
    builder.add_node(nodes.CLARIFY_ROUTE, nodes.make_clarify_node(llm, timezone))
    builder.add_node("create_task", nodes.make_create_task_node(task_service, timezone))
    builder.add_node("list_tasks", nodes.make_list_tasks_node(task_service, timezone))
    builder.add_node("complete_task", nodes.make_complete_task_node(task_service))
    builder.add_node("smalltalk", nodes.smalltalk)
    builder.add_node("unparsed", nodes.unparsed)

    builder.add_edge(START, PARSE_NODE)
    builder.add_conditional_edges(PARSE_NODE, nodes.route_by_intent, nodes.ROUTES)
    # After the question is answered the same router runs again. It cannot pick
    # `clarify` a second time, because the node sets `clarified`.
    builder.add_conditional_edges(nodes.CLARIFY_ROUTE, nodes.route_by_intent, nodes.BRANCH_NODES)
    for branch in nodes.BRANCH_NODES:
        builder.add_edge(branch, END)

    return builder.compile(checkpointer=checkpointer)
