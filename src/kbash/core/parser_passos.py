"""Montagem dos passos e ações (`#@step`/`#@action`) e checagem de ciclos de dependência."""

from __future__ import annotations


from .model import (
    ON_ERROR_VALUES,
    Action,
    Step,
    is_valid_id,
)

from .parser_base import (
    ACTION_IGNORED,
    FALSY,
    TRUTHY,
    _Block,
    _ParserBase,
    _flag,
    _unquote,
)


class _PassosMixin(_ParserBase):
    """§4.4/§4.8/§4.6: montagem de `#@step`/`#@action` e checagem de ciclos."""

    def _build_steps(self) -> list[Step]:
        steps: list[Step] = []
        for block in self.blocks:
            if block.kind != "step":
                continue
            steps.append(self._build_step(block))
        return steps

    def _build_actions(self) -> list[Action]:
        return [self._build_action(block) for block in self.blocks if block.kind == "action"]

    def _build_action(self, block: _Block) -> Action:
        """§4.8 — ação: função, título, botão, grupo, root e timeout (padrão 60 s)."""
        function = (block.get("function") or block.id).strip()
        defined = block.attrs.get("__defined__")
        if function == block.id and defined is not None and defined != block.id:
            self._error(
                f"ação {block.id!r}: a função definida é {defined!r},"
                " o id deve ser igual ao nome da função (ou use #@function)",
                block.line,
            )
        if function not in self.functions:
            self._error(
                f"função {function!r} da ação {block.id!r} não encontrada no script", block.line
            )
        for key in ACTION_IGNORED:
            if block.get(key) is not None:
                self.diag.warning(
                    f"#@{key} não vale em #@action {block.id!r}; será ignorado",
                    block.attr_line(key),
                )
        timeout = 60
        timeout_raw = block.get("timeout")
        if timeout_raw is not None:
            try:
                parsed = int(timeout_raw.strip())
            except ValueError:
                parsed = 0
            if parsed > 0:
                timeout = parsed
            else:
                self.diag.warning(
                    f"#@timeout {timeout_raw!r} inválido na ação {block.id!r}; usando 60 s",
                    block.attr_line("timeout"),
                )
        raw_group = block.get("group")
        group = _unquote(raw_group.strip()) if raw_group else None
        return Action(
            id=block.id,
            function=function,
            title=_unquote((block.get("title") or block.id).strip()),
            description="\n".join(part for part in block.descs if part),
            button=_unquote((block.get("button") or "Executar").strip()) or "Executar",
            group=group or None,
            root=_flag(block.get("root"), False),
            timeout=timeout,
            line=block.line,
        )

    def _build_step(self, block: _Block) -> Step:
        # A ordem dos avisos e do primeiro erro é o contrato (caracterizado em
        # tests/test_passos_e_faixas_tabela.py).
        function = self._funcao_do_passo(block)
        depends = self._depends_do_passo(block)
        timeout = self._timeout_do_passo(block)
        on_error = self._on_error_do_passo(block)
        self._avisar_default_do_passo(block)
        group_raw = block.get("group")
        return Step(
            id=block.id,
            function=function,
            title=_unquote((block.get("title") or block.id).strip()),
            description="\n".join(part for part in block.descs if part),
            group=_unquote(group_raw.strip()) if group_raw else None,
            default=_flag(block.get("default")),
            required=_flag(block.get("required"), False),
            depends=depends,
            root=_flag(block.get("root"), False),
            timeout=timeout,
            on_error=on_error,
            line=block.line,
        )

    def _funcao_do_passo(self, block: _Block) -> str:
        function = (block.get("function") or block.id).strip()
        defined = block.attrs.get("__defined__")
        if function == block.id and defined is not None and defined != block.id:
            # §4.4 — o id deve ser igual ao nome da função (ou use function=)
            self._error(
                f"step {block.id!r}: a função definida é {defined!r},"
                " o id deve ser igual ao nome da função (ou use #@function)",
                block.line,
            )
        if function not in self.functions:
            self._error(
                f"função {function!r} do step {block.id!r} não encontrada no script", block.line
            )
        return function

    def _depends_do_passo(self, block: _Block) -> tuple[str, ...]:
        depends_raw = block.get("depends") or ""
        depends = tuple(
            item for item in (part.strip() for part in depends_raw.split(",")) if item
        )
        for dependency in depends:
            if not is_valid_id(dependency):
                # Equivalente: uma dependência inválida nunca é um step existente, e
                # _check_needs_step levanta ValidationError antes de qualquer aviso chegar
                # ao resultado. O corpo abaixo não é observável.
                message = (  # pragma: no mutate
                    f"dependência {dependency!r} de {block.id!r} "  # pragma: no mutate
                    "não segue [a-z][a-z0-9_]*"  # pragma: no mutate
                )
                self.diag.warning(  # pragma: no mutate
                    message,  # pragma: no mutate
                    block.attr_line("depends"),  # pragma: no mutate
                )
        return depends

    def _timeout_do_passo(self, block: _Block) -> int | None:
        timeout_raw = block.get("timeout")
        if timeout_raw is None:
            return None
        try:
            timeout = int(timeout_raw.strip())
        except ValueError:
            self.diag.warning(
                f"#@timeout {timeout_raw!r} inválido; step sem timeout",
                block.attr_line("timeout"),
            )
            return None
        if timeout <= 0:
            self.diag.warning(
                f"#@timeout {timeout} precisa ser > 0; step sem timeout",
                block.attr_line("timeout"),
            )
            return None
        return timeout

    def _on_error_do_passo(self, block: _Block) -> str:
        on_error = (block.get("on_error") or "stop").strip() or "stop"
        if on_error not in ON_ERROR_VALUES:
            self.diag.warning(
                f"#@on_error {on_error!r} inválido (use stop|continue); usando 'stop'",
                block.attr_line("on_error"),
            )
            return "stop"
        return on_error

    def _avisar_default_do_passo(self, block: _Block) -> None:
        default_raw = block.get("default")
        if default_raw is not None and default_raw.strip().lower() not in TRUTHY | FALSY:
            self.diag.warning(
                f"#@default {default_raw!r} inválido (use on|off)", block.attr_line("default")
            )

    def _check_cycles(self, steps: list[Step]) -> None:
        graph = {step.id: [d for d in step.depends] for step in steps}
        by_id = {step.id: step for step in steps}
        # aponta a diretiva #@depends, não o início do bloco (§4.6)
        lines = {
            block.id: block.attr_line("depends")
            for block in self.blocks
            if block.kind == "step" and block.get("depends")
        }
        for step in steps:
            for dependency in step.depends:
                if dependency not in by_id:
                    self._error(
                        f"#@depends {dependency!r} do step {step.id!r} aponta para"
                        " um step inexistente",
                        lines.get(step.id, step.line),
                    )
        state: dict[str, int] = {}

        def visit(node: str, stack: list[str]) -> None:
            if state.get(node) == 2:
                return
            if state.get(node) == 1:
                cycle = [*stack[stack.index(node):], node]
                self._error("ciclo nas dependências: " + " -> ".join(cycle), by_id[node].line)
            state[node] = 1
            for dependency in graph.get(node, ()):
                visit(dependency, [*stack, node])
            state[node] = 2

        for step in steps:
            visit(step.id, [])
