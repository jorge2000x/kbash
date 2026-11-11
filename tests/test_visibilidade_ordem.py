"""Opção oculta não guarda valor, e o resultado não depende da ordem de declaração.

Achado: `validate_options` percorria as opções uma vez. Se `b` depende de `a`
e `a` se torna oculta, `b` podia manter o valor digitado mesmo oculta, quando
`b` era declarada antes de `a`. A resolução precisa chegar a um ponto fixo.
"""

from __future__ import annotations

import itertools
from pathlib import Path

from kbash.core.parser import parse_text
from kbash.core.planner import option_visible, validate_options

HEADER = "#!/bin/bash\n#@runtime 1\n#@name X\n"

# cadeia: r (raiz, sim) -> m (mostra se r=sim) -> f (mostra se m=x)
BLOCOS = {
    "r": "#@option r\n#@type text\n#@default sim\n",
    "m": "#@option m\n#@type text\n#@show_if r=sim\n",
    "f": "#@option f\n#@type text\n#@show_if m=x\n",
}
VALORES = {"r": "nao", "m": "x", "f": "segredo"}


def _script(ordem: tuple[str, ...]):
    return parse_text(HEADER + "".join(BLOCOS[i] for i in ordem) + "\n", Path("/tmp/x.sh")).script


def test_hidden_options_do_not_keep_user_values_in_any_order() -> None:
    for ordem in itertools.permutations(("r", "m", "f")):
        script = _script(ordem)
        plano = validate_options(script, dict(VALORES))
        # r=nao esconde m; m esconde f. Nada oculto pode sobrar com valor digitado.
        assert plano["m"] == "", ordem
        assert plano["f"] == "", ordem
        assert plano["r"] == "nao", ordem


def test_plan_is_the_same_whatever_the_declaration_order() -> None:
    planos = {
        tuple(sorted(validate_options(_script(ordem), dict(VALORES)).items()))
        for ordem in itertools.permutations(("r", "m", "f"))
    }
    assert len(planos) == 1


def test_plan_never_contains_a_hidden_option_with_a_kept_value() -> None:
    for ordem in itertools.permutations(("r", "m", "f")):
        script = _script(ordem)
        plano = validate_options(script, dict(VALORES))
        for option in script.options:
            if option.show_if and not option_visible(script, plano, option, None):
                assert plano[option.id] == (option.default or ""), (ordem, option.id)
