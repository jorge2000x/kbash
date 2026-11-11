"""Léxico mínimo de Bash para o parser (§4): aspas, escapes, comentários e heredocs.

Não é um parser de Bash. Responde, linha a linha, só o que o kbash precisa:

- ``code``: o texto sem comentário (aspas e escapes preservados);
- ``brace_delta``: saldo de ``{``/``}`` fora de aspas e comentários;
- ``literal``: a linha é corpo de heredoc ou continua uma string aberta
  numa linha anterior. Ela não é código nem anotação (``#@`` ali é texto).

Limites conhecidos: continuação com barra no fim da linha não é juntada, e
numa linha literal o ``code`` vem vazio (só ``brace_delta`` é útil).
"""

from __future__ import annotations

import re
from collections import deque
from dataclasses import dataclass

#: ``<<X``, ``<<-X``, ``<<'X'``, ``<<"X"``; ``<<<`` (here-string) fica de fora.
HEREDOC_RE = re.compile(r"""<<(-?)[ \t]*(?:'([^'\n]+)'|"([^"\n]+)"|\\?([A-Za-z_][A-Za-z0-9_]*))""")

#: caractere que fecha cada tipo de aspa
_FECHO = {"'": "'", "$'": "'", '"': '"'}
#: antes de `#`, um comentário só começa no início de palavra
_ANTES_DE_COMENTARIO = " \t;&|()<>"


@dataclass(frozen=True)
class ScannedLine:
    code: str
    brace_delta: int
    literal: bool


class ShellLexer:
    """Estado entre linhas: aspa aberta e heredocs à espera do terminador."""

    def __init__(self) -> None:
        self._quote: str | None = None
        self._heredocs: deque[tuple[str, bool]] = deque()

    def feed(self, raw: str) -> ScannedLine:
        """Classifica a próxima linha do arquivo, na ordem em que aparecem."""
        if self._heredocs:
            delimiter, strip_tabs = self._heredocs[0]
            candidate = raw.lstrip("\t") if strip_tabs else raw
            if candidate == delimiter:
                self._heredocs.popleft()
            return ScannedLine(code="", brace_delta=0, literal=True)

        literal = self._quote is not None
        parts: list[str] = []
        delta = 0
        index, size = 0, len(raw)
        while index < size:
            char = raw[index]
            if self._quote is not None:
                if char == "\\" and self._quote != "'" and index + 1 < size:
                    parts.append(raw[index : index + 2])
                    index += 2
                    continue
                if char == _FECHO[self._quote]:
                    self._quote = None
                parts.append(char)
                index += 1
                continue
            if char == "\\" and index + 1 < size:
                parts.append(raw[index : index + 2])
                index += 2
                continue
            if char == "#" and (index == 0 or raw[index - 1] in _ANTES_DE_COMENTARIO):
                break
            if char in ("'", '"'):
                self._quote = "$'" if char == "'" and index > 0 and raw[index - 1] == "$" else char
            elif raw.startswith("<<<", index):
                parts.append("<<<")
                index += 3
                continue
            elif raw.startswith("<<", index):
                match = HEREDOC_RE.match(raw, index)
                if match is not None:
                    delimiter = match.group(2) or match.group(3) or match.group(4)
                    self._heredocs.append((delimiter, match.group(1) == "-"))
                    parts.append(match.group(0))
                    index = match.end()
                    continue
            elif char == "{":
                delta += 1
            elif char == "}":
                delta -= 1
            parts.append(char)
            index += 1

        return ScannedLine(code="" if literal else "".join(parts), brace_delta=delta, literal=literal)
