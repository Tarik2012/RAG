import logging

from tree_sitter import Language, Parser
import tree_sitter_python

logger = logging.getLogger(__name__)

_PY_LANGUAGE = Language(tree_sitter_python.language())


def find_symbol_usages(code: str, symbol: str) -> list[dict]:
    """Parsea codigo Python con tree-sitter y devuelve los usos REALES del simbolo
    (identificadores en el AST), excluyendo comentarios y strings.
    Devuelve lista de {line, text} con la linea (1-indexed) y el texto de esa linea."""
    parser = Parser(_PY_LANGUAGE)
    tree = parser.parse(code.encode("utf-8"))
    lines = code.split("\n")
    usages = []
    seen = set()

    def walk(node):
        # 'identifier' son nombres reales en el AST (no comentarios ni strings)
        if node.type == "identifier":
            text = code[node.start_byte:node.end_byte]
            if text == symbol:
                line_no = node.start_point[0] + 1  # tree-sitter es 0-indexed
                if line_no not in seen:
                    seen.add(line_no)
                    line_text = (
                        lines[node.start_point[0]].strip()
                        if node.start_point[0] < len(lines)
                        else ""
                    )
                    usages.append({"line": line_no, "text": line_text})
        for child in node.children:
            walk(child)

    walk(tree.root_node)
    return sorted(usages, key=lambda u: u["line"])
