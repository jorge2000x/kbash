# CLAUDE.md — regras para o agente neste repositório

Regras gerais de desenvolvimento estão em `AGENTS.md`. A spec é `SPEC.md`:
as regras de IA são §14 e a verificação formal do `core/` é §16. Em caso de
conflito, vale a spec, e a mudança dela é proposta ao humano, não feita
por conta própria.

Regra de ouro: **humano aprova a spec; máquina verifica; IA só implementa.**

## Regras obrigatórias

1. Não edite `tests/` nem `INVARIANTS.md` no mesmo commit que `src/`.
   Teste novo ou alterado vai num commit próprio, antes ou depois do código.
2. Função pública nova: type hints completos e pelo menos um contrato
   (`require`/`ensure` de `core/contratos.py`) ou uma propriedade Hypothesis.
3. Proibido para fazer o portão passar:
   - `# type: ignore` sem código de erro e motivo;
   - `except Exception: pass`;
   - reduzir `max_examples` ou desligar uma propriedade;
   - remover `assert`.
   Se um teste parece errado, pare e explique; não o enfraqueça.
4. Mutante sobrevivente (`mutmut results` com `survived` ou `no tests`)
   deve ser corrigido com teste que o mate antes de seguir. Um mutante
   equivalente recebe `# pragma: no mutate` com o motivo ao lado.

## Antes de implementar

Use este prompt-base (ou equivalente) para qualquer tarefa no `core/`:

> Antes de implementar, liste invariantes e propriedades de X. Escreva
> testes de propriedade e tipos, mostre-os falhando, depois implemente até
> passarem. Não altere os testes.

## Portão

`tools/verificar.sh` roda tudo o que o CI roda: `ruff`, `pyright`, `pytest`
do core, `crosshair` e `mutmut`. Uma tarefa só está pronta com ele verde.
