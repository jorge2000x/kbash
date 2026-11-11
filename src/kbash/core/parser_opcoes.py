"""Validação e montagem das opções (`#@option`): tipos, escolhas, faixas, textos e `show_if`."""

from __future__ import annotations

import re

from .model import (
    NON_VALUE_TYPES,
    OPTION_TYPES,
    is_allowed_link,
    Option,
    Step,
    is_valid_date,
    is_valid_id,
    is_ascii_digits,
    is_valid_number,
    is_valid_time,
)

from .parser_base import (
    FALSY,
    TRUTHY,
    _Block,
    _ParserBase,
    _flag,
    _lista_separada_por_virgula,
    _sem_aspas,
    _tokenize,
    _unquote,
)


class _OpcoesMixin(_ParserBase):
    """§4.3: validação e montagem de `#@option`, `range`, `texto` e `show_if`."""

    def _build_options(self) -> list[Option]:
        options: list[Option] = []
        for block in self.blocks:
            if block.kind != "option":
                continue
            option = self._build_option(block)
            options.append(option)
        return options

    def _build_option(self, block: _Block) -> Option:
        # A ordem dos avisos e do primeiro erro é o contrato: cada passo fica na sequência.
        kind = self._tipo_da_opcao(block)
        label = _unquote((block.get("label") or block.id).strip())
        default_raw = block.get("default")
        default = _unquote(default_raw.strip()) if default_raw is not None else None
        choices = _lista_separada_por_virgula(block.get("choices"))
        required = _flag(block.get("required"), False)
        help_text = " ".join(_tokenize(block.get("help") or "", block.line, self.path))
        if kind in NON_VALUE_TYPES:
            return self._opcao_de_exibicao(block, kind, label, help_text)
        self._checar_escolhas(block, kind, default, choices)
        self._avisar_bool(block, kind, default, required)
        minimum, maximum, step = self._parse_range(block, kind)
        filters = _lista_separada_por_virgula(block.get("filters"))
        self._avisar_filters(block, kind, filters)
        if kind in ("number", "slider"):
            self._check_numeric_default(block, default, minimum, maximum)
        self._checar_data_e_hora(block, kind, default)
        pattern, minlen, maxlen, multiple = self._parse_text_checks(block, kind, default)
        show_if = self._parse_show_if(block)
        return Option(
            id=block.id,
            type=kind,
            label=label,
            default=default,
            choices=choices,
            required=required,
            help=help_text,
            minimum=minimum,
            maximum=maximum,
            step=step,
            filters=filters,
            pattern=pattern,
            minlen=minlen,
            maxlen=maxlen,
            multiple=multiple,
            show_if=show_if,
            needs_step=self._parse_needs_step(block),
            group=self._parse_group(block),
            line=block.line,
        )

    def _tipo_da_opcao(self, block: _Block) -> str:
        """``type=`` da opção; tipo desconhecido vira ``string`` com aviso."""
        kind = (block.get("type") or "string").strip() or "string"
        if kind not in OPTION_TYPES:
            self.diag.warning(
                f"type={kind!r} desconhecido em #@option {block.id!r}; usando 'string'",
                block.attr_line("type"),
            )
            return "string"
        return kind

    def _opcao_de_exibicao(
        self, block: _Block, kind: str, label: str, help_text: str
    ) -> Option:
        """§4.3: paragraph/link só exibem texto; não têm valor, então pulam as checagens."""
        url = self._check_display_option(block, kind)
        if kind == "link":
            label = _unquote((block.get("label") or url).strip())
        return Option(
            id=block.id,
            type=kind,
            label=label,
            help=help_text,
            group=self._parse_group(block),
            url=url,
            show_if=self._parse_show_if(block),
            needs_step=self._parse_needs_step(block),
            line=block.line,
        )

    def _checar_escolhas(
        self, block: _Block, kind: str, default: str | None, choices: tuple[str, ...]
    ) -> None:
        if kind not in ("choice", "multi"):
            return
        if not choices:
            self._error(f"#@option {block.id!r} type={kind} exige choices", block.line)
        if default and default not in choices:
            self._error(
                f"default={default!r} de #@option {block.id!r} não está em choices"
                f" ({', '.join(choices)})",
                block.attr_line("default"),
            )

    def _avisar_bool(
        self, block: _Block, kind: str, default: str | None, required: bool
    ) -> None:
        if kind == "bool" and default is not None and default.strip().lower() not in TRUTHY | FALSY:
            self.diag.warning(
                f"default={default!r} de #@option {block.id!r} (bool) não é booleano",
                block.attr_line("default"),
            )
        if required and kind == "bool":
            self.diag.warning(
                f"#@option {block.id!r} é required mas do tipo bool", block.attr_line("required")
            )

    def _avisar_filters(self, block: _Block, kind: str, filters: tuple[str, ...]) -> None:
        if filters and kind != "file":
            self.diag.warning(
                f"filters de #@option {block.id!r} só vale para type=file",
                block.attr_line("filters"),
            )

    def _checar_data_e_hora(self, block: _Block, kind: str, default: str | None) -> None:
        if kind == "date" and default and not is_valid_date(default):
            self._error(
                f"default={default!r} de #@option {block.id!r} não é data ISO (AAAA-MM-DD)",
                block.attr_line("default"),
            )
        if kind == "time" and default and not is_valid_time(default):
            self._error(
                f"default={default!r} de #@option {block.id!r} não é hora (HH:MM)",
                block.attr_line("default"),
            )

    def _parse_group(self, block: _Block) -> str | None:
        """§4.8.1 — ``group=`` da opção geral. Com ``needs_step`` vira aviso e é ignorado."""
        raw = block.get("group")
        if raw is None or not _unquote(raw.strip()):
            return None
        if block.get("needs_step"):
            self.diag.warning(
                f"group em #@option {block.id!r} ignorado: a opção fica na linha do step",
                block.attr_line("group"),
            )
            return None
        return _unquote(raw.strip())

    def _parse_needs_step(self, block: _Block) -> str | None:
        """``needs_step=<id>``: id do step a que a opção pertence (ou ``None``)."""
        raw = block.get("needs_step")
        if raw is None or not raw.strip():
            return None
        return raw.strip()

    def _check_needs_step(self, options: list[Option], steps: list[Step]) -> None:
        """Ligação opção → step: o step precisa existir."""
        step_ids = {step.id for step in steps}
        lines = {
            block.id: block.attr_line("needs_step")
            for block in self.blocks
            if block.kind == "option" and block.get("needs_step")
        }
        for option in options:
            if option.needs_step is not None and option.needs_step not in step_ids:
                self._error(
                    f"needs_step de #@option {option.id!r} aponta para step inexistente "
                    f"{option.needs_step!r}",
                    lines.get(option.id, option.line),
                )

    def _check_display_option(self, block: _Block, kind: str) -> str:
        """§4.3: valida ``paragraph`` (precisa de ``label``) e ``link`` (precisa de
        ``url`` http/https). Devolve a ``url`` ("" para ``paragraph``)."""
        url = _unquote((block.get("url") or "").strip())
        if kind == "paragraph" and not (block.get("label") or "").strip():
            self._error(
                f"#@option {block.id!r} type=paragraph exige label (o texto mostrado)",
                block.line,
            )
        if kind == "link":
            if not url:
                self._error(f"#@option {block.id!r} type=link exige url", block.line)
            elif not is_allowed_link(url):
                self._error(
                    f"url={url!r} de #@option {block.id!r} precisa começar com http:// ou https://",
                    block.attr_line("url"),
                )
        elif block.get("url") is not None:
            self.diag.warning(
                f"url de #@option {block.id!r} só vale para type=link",
                block.attr_line("url"),
            )
        for attr in ("default", "required", "choices", "filters", "multiple", "pattern",
                     "minlen", "maxlen", "min", "max", "step"):
            if block.get(attr) is not None:
                self.diag.warning(
                    f"{attr}= de #@option {block.id!r} não se aplica a type={kind} (ignorado)",
                    block.attr_line(attr),
                )
        return url

    def _parse_show_if(self, block: _Block) -> tuple[tuple[str, str], ...]:
        """§4.3: `show_if="outra=valor,outra2=valor2"` → pares `(id, valor)`."""
        raw = block.get("show_if")
        if raw is None:
            return ()
        pairs: list[tuple[str, str]] = []
        for part in _unquote(raw.strip()).split(","):
            item = part.strip()
            if not item:
                continue
            if "=" not in item:
                self._error(
                    f"show_if={item!r} de #@option {block.id!r} precisa ser id=valor",
                    block.attr_line("show_if"),
                )
                continue
            ref_id, _, expected = item.partition("=")
            ref_id, expected = ref_id.strip(), expected.strip()
            if not ref_id or not is_valid_id(ref_id):
                self._error(
                    f"show_if referencia id inválido {ref_id!r} em #@option {block.id!r}",
                    block.attr_line("show_if"),
                )
                continue
            pairs.append((ref_id, expected))
        return tuple(pairs)

    def _parse_range(self, block: _Block, kind: str) -> tuple[str | None, str | None, str | None]:
        """§4.3: `min`/`max`/`step` de `number`/`slider` (strings numéricas ou `None`).

        O `slider` sem faixa usa `0`/`100`/`1` (SPEC.md §4.3).
        """
        if kind not in ("number", "slider"):
            self._avisar_faixa_sem_uso(block)
            return None, None, None
        minimum, maximum, step = self._faixa_crua(block, kind)
        self._checar_formato_da_faixa(block, minimum, maximum, step)
        self._checar_ordem_da_faixa(block, minimum, maximum, step)
        return minimum or None, maximum or None, step or None

    def _avisar_faixa_sem_uso(self, block: _Block) -> None:
        if any(block.get(name) is not None for name in ("min", "max", "step")):
            self.diag.warning(
                f"min/max/step de #@option {block.id!r} só vale para type=number/slider",
                block.line,
            )

    @staticmethod
    def _faixa_crua(block: _Block, kind: str) -> tuple[str | None, str | None, str | None]:
        """Os três valores sem aspas; o `slider` sem faixa usa `0`/`100`/`1`."""
        minimum = _sem_aspas(block.get("min"))
        maximum = _sem_aspas(block.get("max"))
        step = _sem_aspas(block.get("step"))
        if kind == "slider":
            minimum = minimum or "0"
            maximum = maximum or "100"
            step = step or "1"
        return minimum, maximum, step

    def _checar_formato_da_faixa(
        self, block: _Block, minimum: str | None, maximum: str | None, step: str | None
    ) -> None:
        for name, bound in (("min", minimum), ("max", maximum), ("step", step)):
            if bound not in (None, "") and not is_valid_number(bound):
                self._error(
                    f"{name}={bound!r} de #@option {block.id!r} não é número",
                    block.attr_line(name),
                )

    def _checar_ordem_da_faixa(
        self, block: _Block, minimum: str | None, maximum: str | None, step: str | None
    ) -> None:
        if step not in (None, "") and float(step) <= 0:
            self._error(
                f"step={step!r} de #@option {block.id!r} precisa ser > 0",
                block.attr_line("step"),
            )
        numbers = [float(bound) for bound in (minimum, maximum) if bound not in (None, "")]
        if len(numbers) == 2 and numbers[0] > numbers[1]:
            self._error(
                f"min={minimum!r} maior que max={maximum!r} em #@option {block.id!r}",
                block.attr_line("min"),
            )

    def _check_numeric_default(
        self,
        block: _Block,
        default: str | None,
        minimum: str | None,
        maximum: str | None,
    ) -> None:
        """§4.3: `default` de `number`/`slider` precisa ser numérico e caber na faixa."""
        if not default:
            return
        if not is_valid_number(default):
            self._error(
                f"default={default!r} de #@option {block.id!r} não é número",
                block.attr_line("default"),
            )
            return
        value = float(default)
        if minimum not in (None, "") and value < float(minimum):
            self._error(
                f"default={default!r} de #@option {block.id!r} abaixo de min={minimum!r}",
                block.attr_line("default"),
            )
        if maximum not in (None, "") and value > float(maximum):
            self._error(
                f"default={default!r} de #@option {block.id!r} acima de max={maximum!r}",
                block.attr_line("default"),
            )

    def _parse_text_checks(
        self, block: _Block, kind: str, default: str | None
    ) -> tuple[str, str | None, str | None, bool]:
        """§4.3: `pattern`/`minlen`/`maxlen` (`string`/`password`/`text`) e
        `multiple` (`file`). Devolve `(pattern, minlen, maxlen, multiple)`."""
        raw_pattern = block.get("pattern")
        pattern = _unquote(raw_pattern.strip()) if raw_pattern is not None else ""
        raw_minlen = block.get("minlen")
        raw_maxlen = block.get("maxlen")
        minlen = _unquote(raw_minlen.strip()) if raw_minlen is not None else None
        maxlen = _unquote(raw_maxlen.strip()) if raw_maxlen is not None else None
        multiple = _flag(block.get("multiple"), False)
        if kind in ("string", "password", "text"):
            self._checar_pattern(block, pattern, default)
            self._checar_limites_de_texto(block, minlen, maxlen, default)
        else:
            if raw_pattern is not None or raw_minlen is not None or raw_maxlen is not None:
                self.diag.warning(
                    f"pattern/minlen/maxlen de #@option {block.id!r} só vale para string/password/text",
                    block.line,
                )
            pattern, minlen, maxlen = "", None, None
        if multiple and kind != "file":
            self.diag.warning(
                f"multiple de #@option {block.id!r} só vale para type=file",
                block.attr_line("multiple"),
            )
            multiple = False
        return pattern, minlen, maxlen, multiple

    def _checar_pattern(self, block: _Block, pattern: str, default: str | None) -> None:
        """A regex compila e, se houver `default`, ele casa com ela."""
        if not pattern:
            return
        try:
            re.compile(pattern)
        except re.error as exc:
            self._error(
                f"pattern={pattern!r} de #@option {block.id!r} é regex inválida: {exc}",
                block.attr_line("pattern"),
            )
        if default and not re.fullmatch(pattern, default):
            self._error(
                f"default={default!r} de #@option {block.id!r} não casa com pattern",
                block.attr_line("default"),
            )

    def _checar_limites_de_texto(
        self,
        block: _Block,
        minlen: str | None,
        maxlen: str | None,
        default: str | None,
    ) -> None:
        """`minlen`/`maxlen` são inteiros >= 0, min <= max, e o `default` cabe neles."""
        self._checar_tamanhos(block, minlen, maxlen)
        if default:
            self._checar_default_no_tamanho(block, default, minlen, maxlen)

    def _checar_tamanhos(self, block: _Block, minlen: str | None, maxlen: str | None) -> None:
        for name, bound in (("minlen", minlen), ("maxlen", maxlen)):
            if bound is not None and (not is_ascii_digits(bound) or int(bound) < 0):
                self._error(
                    f"{name}={bound!r} de #@option {block.id!r} precisa ser inteiro >= 0",
                    block.attr_line(name),
                )
        if (minlen is not None and maxlen is not None
                and is_ascii_digits(minlen) and is_ascii_digits(maxlen)
                and int(minlen) > int(maxlen)):
            self._error(
                f"minlen={minlen!r} maior que maxlen={maxlen!r} em #@option {block.id!r}",
                block.attr_line("minlen"),
            )

    def _checar_default_no_tamanho(
        self, block: _Block, default: str, minlen: str | None, maxlen: str | None
    ) -> None:
        if minlen is not None and is_ascii_digits(minlen) and len(default) < int(minlen):
            self._error(
                f"default de #@option {block.id!r} menor que minlen={minlen!r}",
                block.attr_line("default"),
            )
        if maxlen is not None and is_ascii_digits(maxlen) and len(default) > int(maxlen):
            self._error(
                f"default de #@option {block.id!r} maior que maxlen={maxlen!r}",
                block.attr_line("default"),
            )

    def _check_show_if(self, options: list[Option]) -> None:
        """§4.3/§4.6: `show_if` só referencia opção existente, sem ciclo."""
        by_id = {option.id: option for option in options}
        lines = {
            block.id: block.attr_line("show_if")
            for block in self.blocks
            if block.kind == "option" and block.get("show_if")
        }
        for option in options:
            for ref_id, _expected in option.show_if:
                if ref_id == option.id:
                    self._error(
                        f"show_if de #@option {option.id!r} referencia a si mesma",
                        lines.get(option.id, option.line),
                    )
                elif ref_id not in by_id:
                    self._error(
                        f"show_if de #@option {option.id!r} aponta para opção inexistente {ref_id!r}",
                        lines.get(option.id, option.line),
                    )
        graph = {option.id: [ref for ref, _ in option.show_if] for option in options}
        state: dict[str, int] = {}

        def visit(node: str, stack: list[str]) -> None:
            if state.get(node) == 2:
                return
            if state.get(node) == 1:
                cycle = [*stack[stack.index(node):], node]
                self._error(
                    "ciclo em show_if: " + " -> ".join(cycle),
                    lines.get(stack[-1], by_id[node].line),
                )
                return
            state[node] = 1
            for dependency in graph.get(node, ()):
                if dependency in graph:
                    visit(dependency, [*stack, node])
            state[node] = 2

        for option in options:
            visit(option.id, [])
