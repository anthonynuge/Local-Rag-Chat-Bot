"""6K context budget: fit system prompt + context + history + question in INPUT_BUDGET.

Priority order:
1. System prompt and the current question always fit — or the request is
   rejected outright (never silently truncated).
2. Retrieved context packs in rank order into its slice (CONTEXT_BUDGET).
3. History fills whatever room remains, most-recent turn pairs first;
   oldest pairs are dropped whole.
"""
from rag import config
from rag.chunk import n_tokens


def pack(system, question, ranked, history):
    """Assemble the chat messages within INPUT_BUDGET.

    Returns (messages, citations, report). Raises ValueError when system +
    question alone exceed the budget — main.py maps that to a 400
    (api-contract.md): reject, never truncate.
    """
    # The cite reminder is appended to the question only when context gets
    # packed, but its room is reserved up front — reserving after packing
    # would let a borderline prompt overflow the budget.
    reminder = "\n\n" + config.CITE_REMINDER
    system_tokens = n_tokens(system)
    question_tokens = n_tokens(question) + n_tokens(reminder)
    if system_tokens + question_tokens > config.INPUT_BUDGET:
        raise ValueError(
            f"question too large: system+question is {system_tokens + question_tokens} tokens, "
            f"input budget is {config.INPUT_BUDGET}"
        )

    # --- Context: add chunks in rank order until the context slice is full.
    context_cap = min(config.CONTEXT_BUDGET, config.INPUT_BUDGET - system_tokens - question_tokens)
    blocks = []
    citations = []
    context_tokens = 0
    for chunk in ranked:
        citation_id = len(citations) + 1
        block = f'[{citation_id}] ({chunk["source"]} — "{chunk["heading"]}")\n{chunk["text"]}'
        if blocks:
            block = "\n\n" + block  # the separator costs tokens too
        block_tokens = n_tokens(block)
        if context_tokens + block_tokens > context_cap:
            break  # rank order is the contract: no lower-ranked chunk jumps a dropped one
        blocks.append(block)
        context_tokens += block_tokens
        citations.append({"id": citation_id, "source": chunk["source"], "heading": chunk["heading"]})

    # --- History: newest turn pairs into what remains; oldest dropped whole.
    history_cap = config.INPUT_BUDGET - system_tokens - question_tokens - context_tokens
    pairs = []
    for i in range(0, len(history), 2):  # [user, assistant, user, ...] -> (user, assistant) pairs
        pairs.append(history[i:i + 2])

    kept = []
    history_tokens = 0
    for pair in reversed(pairs):  # walk newest pair to oldest
        pair_tokens = sum(n_tokens(message["content"]) for message in pair)
        if history_tokens + pair_tokens > history_cap:
            break
        kept = pair + kept  # prepend so kept history stays in chronological order
        history_tokens += pair_tokens

    # --- Assemble: context rides inside the system message; history in between.
    # The cite reminder rides with the question — the system prompt is too far
    # from the generation point for a small model to keep the [n] format once
    # history grows (an uncited answer in history teaches it the wrong style).
    system_content = system
    user_content = question
    if blocks:
        system_content = system + "\n\nContext:\n" + "".join(blocks)
        user_content = question + reminder
    messages = (
        [{"role": "system", "content": system_content}]
        + kept
        + [{"role": "user", "content": user_content}]
    )

    report = {
        "system": system_tokens,
        "context": context_tokens,
        "history": history_tokens,
        "question": question_tokens,
        "input_budget": config.INPUT_BUDGET,
    }
    total = system_tokens + context_tokens + history_tokens + question_tokens
    assert total <= config.INPUT_BUDGET, "packer accounting error"
    return messages, citations, report
