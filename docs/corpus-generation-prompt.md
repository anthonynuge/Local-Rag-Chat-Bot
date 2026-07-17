# Corpus — Generation Prompt

Paste the block below into a coding agent to generate the starter corpus — the
fictional "Northwind Robotics" internal wiki this project retrieves over. See
[spec.md](spec.md#sample-knowledge-base) for why the corpus is fictional (kept
outside model training data so retrieval, not recall, is what's tested).

---

## Prompt

> You are generating a **sample internal knowledge base** for a local RAG
> (retrieval-augmented generation) demo. Create files for a **fictional
> company, "Northwind Robotics"** — a made-up mid-size company that builds
> warehouse automation robots. Everything must be **invented** (names, dates,
> policies, tools, numbers) so it does not overlap with real-world facts.
>
> **Output location:** write the files into `backend/data/sample/`.
>
> **Create exactly these 6 files — a mix of `.md` and `.txt`, of varying
> length** (the pipeline must handle both formats and short/long documents):
>
> | File | Format | Length | Contents |
> |------|--------|--------|----------|
> | `company-overview.md` | Markdown, `##` sections | medium (~400 words) | what Northwind does, mission, product lines (e.g. the "Warehouse Pilot" AMR), org structure, office locations, founding year |
> | `onboarding.md` | Markdown, `##` sections | long (~700 words) | new-hire first week: accounts to request, laptop setup, who to contact, required training, internal tools |
> | `pto-policy.md` | Markdown, `##` sections | medium (~350 words) | PTO accrual rate, how to request, approval, company holidays, carryover, sick leave |
> | `deploy-runbook.md` | Markdown, `##` sections | long (~600 words) | deploy command, environments (staging/prod), rollback procedure, on-call rotation, incident paging |
> | `security-policy.txt` | **Plain text, no headings** | medium (~300 words) | passwords/MFA, VPN requirement for production, data classification, laptop encryption, reporting a security incident |
> | `faq.txt` | **Plain text, `Q:` / `A:` lines** | short (~200 words) | 6–8 short Q&A: expensing, remote work, parking, Slack channels, IT help |
>
> **Formatting requirements (important for the RAG chunker):**
> - In the `.md` files, use `##` section headings generously — the pipeline is
>   heading-aware and splits on them, so each `##` should be a self-contained
>   topic of roughly 100–350 words. Each `.md` file starts with a single `#` H1.
> - The `.txt` files have **no Markdown headings** — plain paragraphs (or `Q:`/
>   `A:` lines for the FAQ). These test the pipeline's plain-text path.
> - Keep prose plain and factual, like a real internal wiki. No marketing fluff.
> - Put **concrete, checkable facts** in the text — specific numbers, names, and
>   procedures — so a reader can ask a precise question and verify the answer.
>   Examples of the *style* (invent your own values): "PTO accrues at 1.5 days
>   per month," "deploys run via `northwind deploy --env prod`," "VPN (NorthVPN)
>   is required for all production access," "on-call is a weekly rotation, page
>   via PagerDuty."
>
> **Deliberate coverage boundaries (for testing refusal):**
> - Do **not** include: employee salaries or compensation numbers, company
>   financials/stock, or competitor information. These gaps are intentional — the
>   demo asks questions like *"How much does a senior engineer earn?"* (in-domain
>   but undocumented) and *"What's the capital of France?"* (general knowledge)
>   to confirm the assistant **refuses instead of hallucinating**. Keep the
>   corpus strictly about Northwind Robotics; do not reference any real company.
>
> **Consistency:** reuse the same invented names, tools, and dates across files
> (e.g. the same CTO name in `company-overview.md` and `deploy-runbook.md`) so
> the corpus feels like one real company.
>
> Write all 6 files now.

---

## After generation — quick sanity check

- 6 files in `backend/data/sample/`: 4 `.md` + 2 `.txt`, of varying length.
- Each `.md` has an `#` H1 and multiple `##` sections; the `.txt` files have
  none (plain text) — this exercises both chunking paths.
- Spot-check a few facts are concrete enough to ask about (PTO accrual rate,
  deploy command).
- Confirm the excluded topics (salaries, financials, competitors) are absent —
  those drive the refusal test (spec A3).
