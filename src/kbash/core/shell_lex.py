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
            self._consome_corpo_de_heredoc(raw)
            return ScannedLine(code="", brace_delta=0, literal=True)
        literal = self._quote is not None
        parts, delta = self._varre(raw)
        return ScannedLine(code="" if literal else "".join(parts), brace_delta=delta, literal=literal)

    # -- internos -------------------------------------------------------
    def _consome_corpo_de_heredoc(self, raw: str) -> None:
        delimiter, strip_tabs = self._heredocs[0]
        candidate = raw.lstrip("\t") if strip_tabs else raw
        if candidate == delimiter:
            self._heredocs.popleft()

    def _varre(self, raw: str) -> tuple[list[str], int]:
        parts: list[str] = []
        delta = 0
        index = 0
        while index < len(raw):
            quote = self._quote
            if quote is not None:
                index = self._dentro_de_aspas(raw, index, parts, quote)
            elif raw[index] == "#" and (index == 0 or raw[index - 1] in _ANTES_DE_COMENTARIO):
                break
            else:
                index, step = self._fora_de_aspas(raw, index, parts)
                delta += step
        return parts, delta

    def _dentro_de_aspas(self, raw: str, index: int, parts: list[str], quote: str) -> int:
        char = raw[index]
        if char == "\\" and quote != "'" and index + 1 < len(raw):
            parts.append(raw[index : index + 2])
            return index + 2
        if char == _FECHO[quote]:
            self._quote = None
        parts.append(char)
        return index + 1

    def _fora_de_aspas(self, raw: str, index: int, parts: list[str]) -> tuple[int, int]:
        char = raw[index]
        if char == "\\" and index + 1 < len(raw):
            parts.append(raw[index : index + 2])
            return index + 2, 0
        if char in ("'", '"'):
            self._quote = "$'" if char == "'" and index > 0 and raw[index - 1] == "$" else char
        elif raw.startswith("<<", index):
            after = self._heredoc(raw, index, parts)
            if after is not None:
                return after, 0
        parts.append(char)
        return index + 1, _saldo_de_chave(char)

    def _heredoc(self, raw: str, index: int, parts: list[str]) -> int | None:
        """Trata ``<<`` no índice: devolve o índice depois do operador, ou None."""
        if raw.startswith("<<<", index):
            parts.append("<<<")
            return index + 3
        match = HEREDOC_RE.match(raw, index)
        if match is None:
            return None
        delimiter = match.group(2) or match.group(3) or match.group(4)
        self._heredocs.append((delimiter, match.group(1) == "-"))
        parts.append(match.group(0))
        return match.end()


def _saldo_de_chave(char: str) -> int:
    if char == "{":
        return 1
    if char == "}":
        return -1
    return 0
