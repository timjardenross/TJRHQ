from pathlib import Path
from unittest.mock import patch

from src.agents.article_agent import ArticleAgent


def _fake_generate_text(prompt):
    # Echo the section body back unchanged so tests don't depend on / pay for
    # the real expansion model; expansion behavior itself is covered by the
    # word-target unit tests below.
    return prompt.split("Section:\n", 1)[1]


def test_generate_article(brief, tmp_path):
    with patch("src.agents.article_agent.generate_text", side_effect=_fake_generate_text):
        result = ArticleAgent().generate(brief, tmp_path)
    md_path, html_path = (Path(f) for f in result["files"])

    assert md_path.exists() and html_path.exists()
    markdown = md_path.read_text()
    assert brief.headline in markdown
    assert "WHAT ARE THE 12 SYSTEMS?" in markdown
    assert "THE PROMISE" in markdown
    assert "<html" in html_path.read_text().lower()


def test_expand_if_short_skips_sections_at_or_near_target():
    from src.agents.article_agent import _expand_if_short
    body = " ".join(["word"] * 200)
    with patch("src.agents.article_agent.generate_text") as mock_gen:
        result = _expand_if_short("Section", body, word_target=200)
    assert result == body
    mock_gen.assert_not_called()


def test_expand_if_short_expands_sections_well_under_target():
    from src.agents.article_agent import _expand_if_short
    body = " ".join(["word"] * 50)
    with patch("src.agents.article_agent.generate_text", return_value="expanded text") as mock_gen:
        result = _expand_if_short("Section", body, word_target=300)
    assert result == "expanded text"
    mock_gen.assert_called_once()


def test_expand_if_short_noop_when_no_target():
    from src.agents.article_agent import _expand_if_short
    with patch("src.agents.article_agent.generate_text") as mock_gen:
        result = _expand_if_short("Section", "short body", word_target=None)
    assert result == "short body"
    mock_gen.assert_not_called()
