"""Phase 2: Corrective RAG with LangGraph.

Implements a graph that retrieves chunks, grades them for relevance, optionally
rewrites the query, and generates an answer using only relevant chunks.

The grader uses doc_type guidance to route to authoritative sources.

Usage:
  python rag_graph.py

Accepts interactive queries. Run four acceptance tests:
  (a) "Can I have two dogs?"
  (b) "Can I rent out my unit?"
  (c) "Can I run a business from my house?"
  (d) "What did the property inspection find?"
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import START, StateGraph
from openai import OpenAI
from store import search


class State(TypedDict):
    """State maintained throughout the graph."""
    question: str  # Current question (may be rewritten)
    original_question: str  # Original user query
    chunks: list[dict]  # Retrieved chunks
    relevant_indices: list[int]  # Chunk indices marked relevant by grader (0-indexed)
    sufficient: bool  # Whether grader found sufficient context
    answer: str  # Final answer
    rewrite_count: int  # Number of query rewrites attempted
    messages: list[dict]  # Conversation history (last 2 Q&A pairs)
    trace: list[str]  # Path trace: ["retrieve", "grade(insufficient)", "rewrite(...)"]


client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key=os.getenv("LM_STUDIO_API_KEY", "default-key"),
)

GRADING_PROMPT = """You are an expert HOA document classifier. Given a question and a list of chunks,
decide which chunks are relevant to answering the question.

CRITICAL GUIDANCE:
- Governing chunks (CC&Rs, Bylaws, Operating Rules) are AUTHORITATIVE for rules about what owners
  may or may not do. These are the primary source for operational/conduct questions.
  EXAMPLE: "Can I run a business?" requires governing chunks that discuss business restrictions.
- Advisory chunks describe general California law or market trends, NOT this association's specific
  rules. They are relevant only if the question asks about state law or broader context.
- Report chunks (Property Inspection, Pest, Roof, Title, etc.) describe property condition, findings,
  defects, or state of repair. They are ESSENTIAL for questions about:
  - Property inspection results or findings
  - Roof condition or repairs
  - Pest damage or issues
  - Property defects or concerns
  - Title issues
  EXAMPLE: "What did the property inspection find?" MUST use Report chunks like Property Inspection Report.pdf.

DECISION RULES:
1. If the question mentions "inspection", "findings", "condition", "defects", "damage", or "repair" →
   PRIORITIZE report chunks. Include them even if advisory chunks rank higher semantically.
2. If the question asks about owner rules or restrictions → prioritize governing chunks.
3. If multiple chunks are relevant, include them ALL to maximize answer completeness.

Return ONLY a JSON array of 0-indexed chunk indices (no markdown, no explanation):
[0, 2, 4]

Or empty array if no chunks are relevant:
[]"""


def retrieve(state: State) -> State:
    """Retrieve top-k chunks for the current question."""
    chunks = search(state["question"], k=8)
    state["chunks"] = chunks
    state["trace"].append("retrieve")
    return state


def grade(state: State) -> State:
    """Grade chunks for relevance using the LLM.

    The grader returns:
      {relevant: [indices], sufficient: bool}

    We parse defensively, stripping markdown fences and whitespace.
    """
    if not state["chunks"]:
        state["relevant_indices"] = []
        state["sufficient"] = False
        state["trace"].append("grade(no_chunks)")
        return state

    # Build chunk descriptions for the grader
    chunk_descs = []
    for i, chunk in enumerate(state["chunks"]):
        source = chunk.get("source", "Unknown")
        doc_type = chunk.get("doc_type", "—")
        pages = f"{chunk.get('page_start', '?')}-{chunk.get('page_end', '?')}"
        text = chunk.get("text", "")

        chunk_descs.append(
            f"[{i}] {source} [{doc_type}] (p{pages})\n    {text}"
        )

    chunks_block = "\n\n".join(chunk_descs)

    # Call LLM for grading
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": GRADING_PROMPT},
            {
                "role": "user",
                "content": f"Question: {state['original_question']}\n\nChunks:\n{chunks_block}",
            },
        ],
        temperature=0,
    )

    grade_text = response.choices[0].message.content

    # Strip <think> tags BEFORE parsing JSON
    grade_text = re.sub(r"<think>.*?</think>", "", grade_text, flags=re.DOTALL)
    grade_text = grade_text.strip()
    if grade_text.startswith("```"):
        grade_text = re.sub(r"```json?\n?", "", grade_text)
        grade_text = re.sub(r"\n?```", "", grade_text)
    grade_text = grade_text.strip()

    try:
        # Parse as direct array (not object with "relevant" field)
        relevant_indices = json.loads(grade_text)
        if not isinstance(relevant_indices, list):
            relevant_indices = []
    except json.JSONDecodeError:
        # Fallback: assume no relevant chunks
        relevant_indices = []

    # Compute sufficiency client-side: any relevant chunks means sufficient context
    sufficient = len(relevant_indices) > 0

    state["relevant_indices"] = relevant_indices
    state["sufficient"] = sufficient

    if sufficient:
        state["trace"].append("grade(sufficient)")
    else:
        state["trace"].append("grade(insufficient)")

    return state


def rewrite(state: State) -> State:
    """Rewrite the question using formal HOA/legal vocabulary.

    Rewrites are for search optimization, but the generate node will
    answer relative to the original question.
    """
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {
                "role": "system",
                "content": (
                    "Rewrite this question using formal HOA/legal document vocabulary. "
                    "Use terms like: lease, rental, assessment, Owner, Lot, Common Area, "
                    "Bylaws, CC&Rs, covenant, restriction, Board, member. "
                    "Return ONLY the rewritten query, no explanation."
                ),
            },
            {"role": "user", "content": state["question"]},
        ],
        temperature=0,
    )

    rewritten = response.choices[0].message.content.strip()

    # Strip <think> tags BEFORE using as search query
    rewritten = re.sub(r"<think>.*?</think>", "", rewritten, flags=re.DOTALL)
    rewritten = rewritten.strip()

    state["question"] = rewritten
    state["rewrite_count"] += 1
    state["trace"].append(f"rewrite('{rewritten[:50]}...')")

    return state


def generate(state: State) -> State:
    """Generate an answer using only chunks marked relevant by the grader.

    If no chunks were marked relevant, use all retrieved chunks as a fallback
    and instruct the model to be honest about incomplete coverage.
    """
    # Select relevant chunks (or all if none marked relevant)
    if state["relevant_indices"]:
        relevant_chunks = [state["chunks"][i] for i in state["relevant_indices"] if i < len(state["chunks"])]
    else:
        relevant_chunks = state["chunks"]
        incomplete_note = " (Note: The grader found limited relevant context. The answer may be incomplete.)"

    if not state["relevant_indices"]:
        incomplete_note = " The documents may not fully address this question, so state what they do and don't cover."
    else:
        incomplete_note = ""

    # DEBUG: Log what we're sending to LLM
    print(f"\n[DEBUG GENERATE] relevant_indices={state['relevant_indices']}, using {len(relevant_chunks)} chunks")

    # Build context block from relevant chunks
    # Use simple formatting to avoid confusing LLM with structured metadata
    context_lines = ["RELEVANT DOCUMENTS:\n"]
    for i, chunk in enumerate(relevant_chunks, 1):
        source = chunk.get("source", "Unknown")
        pages = f"{chunk.get('page_start', '?')}-{chunk.get('page_end', '?')}"
        sections = chunk.get("sections", [])
        doc_type = chunk.get("doc_type", "—")

        section_str = "—"
        if sections:
            section_str = f"§{sections[0]}"  # Just the first section

        context_lines.append(f"Source: {source} (pages {pages})")
        if section_str != "—":
            context_lines.append(f"Sections: {section_str}")
        context_lines.append(chunk.get('text', ''))
        context_lines.append("---\n")

    context_block = "\n".join(context_lines)

    # DEBUG: Log what's in the context
    if "no business of any kind" in context_block.lower():
        print("[DEBUG GENERATE] ✓ Business prohibition found in context")
    else:
        print("[DEBUG GENERATE] ✗ Business prohibition NOT in context")
    print(f"[DEBUG GENERATE] Context length: {len(context_block)} chars\n")

    # Build system prompt
    system_prompt = f"""You are an HOA document assistant. Answer questions ONLY using the provided context.

For every claim, cite the source: (document name, §section if present, pages).
Example: "According to the CC&Rs §4.12 (pages 30–31), owners must..."

Choose ONE of these:
1. If the documents contain relevant information, provide a direct answer citing sources.
2. If the documents do NOT contain relevant information, respond with ONLY: "The documents don't address this question."

Do NOT mix both. Do not speculate or use external knowledge. Stay strictly within the provided chunks."""

    # Include conversation history if available
    messages = [{"role": "system", "content": system_prompt}]
    if state["messages"]:
        messages.extend(state["messages"][-4:])  # Last 2 Q&A pairs

    # DEBUG: Print system prompt
    print(f"[DEBUG GENERATE] System Prompt:\n{system_prompt}\n")

    # Add current question
    user_message = f"{context_block}\n\nQuestion: {state['original_question']}"
    messages.append({
        "role": "user",
        "content": user_message,
    })

    # DEBUG: Save full message to file for inspection
    with open("/tmp/debug_message.txt", "w") as f:
        f.write("=== FULL USER MESSAGE ===\n")
        f.write(user_message)
        f.write("\n\n=== SYSTEM PROMPT ===\n")
        f.write(system_prompt)

    # Call LLM
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        temperature=0,
    )

    answer_text = response.choices[0].message.content

    # Strip <think> blocks
    answer_text = re.sub(r"<think>.*?</think>", "", answer_text, flags=re.DOTALL)
    answer_text = answer_text.strip()

    state["answer"] = answer_text

    # Update conversation history
    state["messages"].append({"role": "user", "content": state["original_question"]})
    state["messages"].append({"role": "assistant", "content": answer_text})

    state["trace"].append("generate")
    return state


def should_rewrite(state: State) -> str:
    """Conditional edge: decide whether to rewrite or generate."""
    if state["sufficient"]:
        return "generate"
    elif state["rewrite_count"] < 2:
        return "rewrite"
    else:
        return "generate"


def build_graph():
    """Build and return the compiled RAG graph."""
    graph_builder = StateGraph(State)

    # Add nodes
    graph_builder.add_node("retrieve", retrieve)
    graph_builder.add_node("grade", grade)
    graph_builder.add_node("rewrite", rewrite)
    graph_builder.add_node("generate", generate)

    # Define edges
    graph_builder.add_edge(START, "retrieve")
    graph_builder.add_edge("retrieve", "grade")
    graph_builder.add_conditional_edges("grade", should_rewrite, {"generate": "generate", "rewrite": "rewrite"})
    graph_builder.add_edge("rewrite", "retrieve")

    # Compile with memory
    memory = MemorySaver()
    return graph_builder.compile(checkpointer=memory)


def format_sources(chunks: list[dict], relevant_indices: list[int] = None) -> str:
    """Format chunks for output, marking relevant ones."""
    lines = ["SOURCES:"]
    for i, chunk in enumerate(chunks):
        marker = " ✓" if relevant_indices and i in relevant_indices else ""
        source = chunk.get("source", "Unknown")
        pages = f"{chunk.get('page_start', '?')}-{chunk.get('page_end', '?')}"
        doc_type = chunk.get("doc_type", "—")

        lines.append(f"  {i + 1}. {source} (p{pages}) [{doc_type}]{marker}")

    return "\n".join(lines)


def main() -> None:
    """Interactive CLI for the RAG graph."""
    graph = build_graph()

    print("HOA RAG Chatbot (with corrective loop)")
    print("Type 'quit' or 'exit' to stop.\n")

    thread_id = "cli"

    while True:
        try:
            question = input("You: ").strip()
            if not question:
                continue
            if question.lower() in ("quit", "exit"):
                break

            print()

            # Initialize state
            initial_state: State = {
                "question": question,
                "original_question": question,
                "chunks": [],
                "relevant_indices": [],
                "sufficient": False,
                "answer": "",
                "rewrite_count": 0,
                "messages": [],
                "trace": [],
            }

            # Run graph
            final_state = graph.invoke(initial_state, {"configurable": {"thread_id": thread_id}})

            # Print results
            print(f"Assistant: {final_state['answer']}\n")
            print("=" * 80)
            print(format_sources(final_state["chunks"], final_state["relevant_indices"]))
            print(f"\nTrace: {' -> '.join(final_state['trace'])}")
            print("=" * 80)
            print()

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"Error: {e}\n")


if __name__ == "__main__":
    main()
