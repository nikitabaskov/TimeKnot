"""Graph assembly."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from graph import nodes
from graph.llm import LLMClient
from graph.state import DialogState

PARSE_NODE = "parse"


def build_message_graph(llm: LLMClient):
    builder = StateGraph(DialogState)
    builder.add_node(PARSE_NODE, nodes.make_parse_node(llm))
    builder.add_node("create_task", nodes.create_task)
    builder.add_node("list_tasks", nodes.list_tasks)
    builder.add_node("complete_task", nodes.complete_task)
    builder.add_node("smalltalk", nodes.smalltalk)
    builder.add_node("unparsed", nodes.unparsed)

    builder.add_edge(START, PARSE_NODE)
    builder.add_conditional_edges(PARSE_NODE, nodes.route_by_intent, nodes.BRANCH_NODES)
    for branch in nodes.BRANCH_NODES:
        builder.add_edge(branch, END)

    return builder.compile()
