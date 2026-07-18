"""pack() [CORE]: never exceed INPUT_BUDGET, reject oversized questions,
context in rank order, oldest history dropped first."""
import pytest

from rag import budget, config

SYSTEM = "Answer only from the context."


def _chunk(text, source="doc.md", heading="H"):
    return {"source": source, "heading": heading, "text": text}


def _turns(n_pairs, words_each=50):
    """n_pairs of (user, assistant) history turns, oldest first."""
    history = []
    for i in range(n_pairs):
        history.append({"role": "user", "content": f"question {i} " + "u " * words_each})
        history.append({"role": "assistant", "content": f"answer {i} " + "a " * words_each})
    return history


def test_oversized_question_rejected():
    huge_question = "why " * config.INPUT_BUDGET  # alone bigger than the whole budget
    with pytest.raises(ValueError):
        budget.pack(SYSTEM, huge_question, [], [])


def test_never_exceeds_input_budget_under_pressure():
    # way more context and history than can ever fit
    ranked = [_chunk("filler words " * 300, source=f"f{i}.md") for i in range(40)]
    history = _turns(30, words_each=200)

    messages, citations, report = budget.pack(SYSTEM, "what is the policy?", ranked, history)

    used = report["system"] + report["context"] + report["history"] + report["question"]
    assert used <= config.INPUT_BUDGET
    assert report["context"] <= config.CONTEXT_BUDGET
    # system prompt and question survived packing
    assert messages[0]["role"] == "system" and SYSTEM in messages[0]["content"]
    assert messages[-1]["role"] == "user"
    assert messages[-1]["content"].startswith("what is the policy?")


def test_context_packs_in_rank_order():
    ranked = [_chunk(f"chunk number {i} " * 30, source=f"f{i}.md") for i in range(5)]

    _, citations, _ = budget.pack(SYSTEM, "q?", ranked, [])

    # citation ids are 1..n and follow the given rank order
    assert [c["id"] for c in citations] == list(range(1, len(citations) + 1))
    assert [c["source"] for c in citations] == [f"f{i}.md" for i in range(len(citations))]


def test_oldest_history_dropped_first():
    # each pair ~400 tokens; context eats most of the budget so only some pairs fit
    ranked = [_chunk("context filler " * 800)]
    history = _turns(30, words_each=200)

    messages, _, report = budget.pack(SYSTEM, "q?", ranked, history)

    kept_history = messages[1:-1]  # between system and the final question
    assert 0 < len(kept_history) < len(history), "test needs partial history to mean anything"
    # what survived is the NEWEST tail of the conversation, in original order
    assert kept_history == history[-len(kept_history):]
    # dropped whole pairs: kept history starts with a user turn
    assert kept_history[0]["role"] == "user"


def test_cite_reminder_rides_with_question_only_when_context_packed():
    # with packed context: reminder appended after the question
    messages, _, _ = budget.pack(SYSTEM, "q?", [_chunk("some text " * 30)], [])
    assert messages[-1]["content"].startswith("q?")
    assert config.CITE_REMINDER in messages[-1]["content"]

    # no context to cite -> plain question, no reminder to hallucinate against
    messages, _, _ = budget.pack(SYSTEM, "q?", [], [])
    assert messages[-1] == {"role": "user", "content": "q?"}


def test_citations_only_for_packed_chunks():
    small_cap_chunks = [_chunk("word " * 350, source=f"f{i}.md") for i in range(20)]

    messages, citations, report = budget.pack(SYSTEM, "q?", small_cap_chunks, [])

    # every citation's block made it into the system message; none beyond the cap
    assert 0 < len(citations) < 20
    for citation in citations:
        assert f'[{citation["id"]}]' in messages[0]["content"]
