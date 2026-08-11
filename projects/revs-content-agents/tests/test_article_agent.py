from pathlib import Path

from src.agents.article_agent import ArticleAgent


def test_generate_article(brief, tmp_path):
    result = ArticleAgent().generate(brief, tmp_path)
    md_path, html_path = (Path(f) for f in result["files"])

    assert md_path.exists() and html_path.exists()
    markdown = md_path.read_text()
    assert brief.headline in markdown
    assert "WHAT ARE THE 12 SYSTEMS?" in markdown
    assert "THE PROMISE" in markdown
    assert "<html" in html_path.read_text().lower()
