from pathlib import Path


def test_agent_prompt_includes_critical_protections():
    source = Path("documents/views.py").read_text(encoding="utf-8")

    assert "CRITICAL - FILE IDENTITY:" in source
    assert "NEVER answer about one file using" in source
    assert "content from a different file discussed earlier." in source
    assert "Never invent files, functions, or" in source
    assert "facts; if something is not in the files, say so." in source
