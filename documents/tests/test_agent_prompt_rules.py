from pathlib import Path


def test_agent_prompt_includes_tool_selection_rules():
    source = Path("documents/views.py").read_text(encoding="utf-8")

    assert "for SECURITY or VULNERABILITIES of ONE specific file, prefer run_static_analysis" in source
    assert "For SECURITY of the WHOLE project, do NOT scan file by file." in source
    assert "direct the user to the full-project audit flow ('audita todo el proyecto')" in source
    assert "NEVER claim a project is secure based on partial scans." in source
    assert "For LEGACY code, explanation, style, architecture, or general quality, prefer read_full_file" in source
    assert "use find_references with the symbol name" in source
