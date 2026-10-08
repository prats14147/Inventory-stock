"""Tests for Upgrade #2: TF-IDF vector retrieval over project docs.

Retrieval must rank by term importance (not raw overlap), stay
deterministic, and return no evidence for gibberish or thin single-term
questions -- the chat layer treats [] as "say you don't know".
"""

from app.services import project_knowledge_service as pk


def test_reorder_formula_question_finds_evidence():
    results = pk.retrieve("How is the reorder quantity calculated?")
    assert results, "expected documentation evidence for the reorder formula"
    assert all({"source", "section", "text"} <= set(item) for item in results)


def test_model_metrics_question_finds_ml_docs():
    results = pk.retrieve("What is sMAPE and how good is the model?")
    assert results
    sources = " ".join(item["source"] for item in results)
    assert "limitations.md" in sources or "architecture.md" in sources


def test_install_question_finds_readme():
    results = pk.retrieve("How do I install and run this?")
    assert results
    assert results[0]["source"] == "README.md"


def test_gibberish_returns_no_evidence():
    assert pk.retrieve("asdkjasd random gibberish xyzzy") == []


def test_thin_single_term_question_returns_no_evidence():
    # Same strictness as the legacy floor: one bare term is not evidence.
    assert pk.retrieve("What is sMAPE?") == []


def test_retrieval_is_deterministic():
    first = pk.retrieve("What does the live simulator do?")
    second = pk.retrieve("What does the live simulator do?")
    assert [item["text"] for item in first] == [item["text"] for item in second]


def test_limit_is_respected():
    results = pk.retrieve("sales inventory forecast reorder stock", limit=1)
    assert len(results) <= 1
