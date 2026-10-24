"""Propriedades do ambiente das ações (INVARIANTS.md, seção Ações; SPEC §4.8, §7.6).

``run_action`` roda bash de verdade e tem casos unitários em test_actions_run.py.
Aqui só o que é puro: o ambiente montado a partir dos valores da tela.
"""

from __future__ import annotations

from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from kbash.core.actions import action_env
from kbash.core.model import Option, Script

HELPERS = Path("/nao-existe/rt.sh")


def _script() -> Script:
    return Script(
        path=Path("x.kbash"),
        sha256="",
        runtime_version=1,
        name="x",
        id="x",
        options=(
            Option(id="dir", type="string", label="D", default="padrao"),
            Option(id="nivel", type="string", label="N", default="baixo", needs_step="passo"),
            Option(id="sup", type="paragraph", label="texto"),
        ),
    )


VALORES = st.dictionaries(st.sampled_from(["dir", "nivel"]), st.text(max_size=20), max_size=2)
SELECAO = st.lists(st.sampled_from(["passo", "outro"]), unique=True, max_size=2)


@settings(max_examples=200)
@given(VALORES, SELECAO)
def test_opt_para_toda_opcao(valores: dict[str, str], selecao: list[str]) -> None:
    env = action_env(_script(), valores, selecao, helpers=HELPERS)
    assert "OPT_DIR" in env and "OPT_NIVEL" in env
    assert "OPT_SUP" not in env  # paragraph não tem valor (§4.3)


@settings(max_examples=200)
@given(VALORES, SELECAO)
def test_oculta_usa_default(valores: dict[str, str], selecao: list[str]) -> None:
    env = action_env(_script(), valores, selecao, helpers=HELPERS)
    if "passo" not in selecao:
        assert env["OPT_NIVEL"] == "baixo"
    else:
        assert env["OPT_NIVEL"] == valores.get("nivel", "baixo")
