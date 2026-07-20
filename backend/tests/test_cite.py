"""Citation repair: markers that name the wrong packed chunk get repointed."""
from rag import cite


def _citations():
    return [
        {"id": 1, "source": "rangers.md", "heading": "Command", "text": "The incident commander is Chief Ranger Ruben Ortega."},
        {"id": 2, "source": "fees.md", "heading": "Passes", "text": "A vehicle day pass is $22."},
        {"id": 3, "source": "trails.md", "heading": "Routes", "text": "The Gorge Rim Loop is 6.2 km."},
    ]


def test_wrong_marker_repointed_to_the_supporting_chunk():
    answer = "The incident commander is Chief Ranger Ruben Ortega [3]."
    fixed, changes = cite.fix(answer, _citations())
    assert [(3, "trails.md", "rangers.md")] == changes
    # marker [3] now resolves to the file that actually contains the name
    assert next(c for c in fixed if c["id"] == 3)["source"] == "rangers.md"


def test_correct_citation_left_alone():
    answer = "A vehicle day pass is $22 [2]."
    fixed, changes = cite.fix(answer, _citations())
    assert changes == []
    assert fixed == _citations()


def test_ambiguous_claim_left_alone():
    # two chunks support the number equally -> no unique better source, no change
    citations = [
        {"id": 1, "source": "a.md", "heading": "", "text": "the fee is $22"},
        {"id": 2, "source": "b.md", "heading": "", "text": "the fee is $22"},
        {"id": 3, "source": "c.md", "heading": "", "text": "nothing relevant here"},
    ]
    fixed, changes = cite.fix("The fee is $22 [3].", citations)
    assert changes == []
    assert fixed == citations


def test_refusal_untouched():
    fixed, changes = cite.fix("I don't have that information.", _citations())
    assert changes == []
    assert fixed == _citations()
