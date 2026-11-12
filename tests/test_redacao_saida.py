"""Redação de senhas e normalização de saída (ponto 1 e 2 da análise de segurança/UX).

* valores de opções ``password`` não aparecem em linhas de log nem na saída de ações;
* ``\\r`` numa linha mostra só o estado final (barras de progresso de apt/curl);
* ``TERM=dumb`` e ``DEBIAN_FRONTEND=noninteractive`` são padrões, sem sobrescrever o usuário.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from fixtures.paths import HELPERS
from kbash.core.events import LogLine
from kbash.core.executor import Executor
from kbash.core.parser import parse_script
from kbash.core.planner import build_plan
from kbash.core.redacao import MASCARA, redige


# -- redige: unidade e propriedade -----------------------------------------
def test_redige_troca_segredo_pela_mascara() -> None:
    assert redige("senha=s3nha!", ["s3nha!"]) == f"senha={MASCARA}"


def test_redige_ignora_segredo_vazio() -> None:
    assert redige("texto", [""]) == "texto"


def test_redige_mascara_o_mais_longo_primeiro() -> None:
    # "ab" dentro de "abc": o mais longo sai inteiro, sem sobrar "c" de um segredo maior
    assert redige("abc", ["ab", "abc"]) == MASCARA


@settings(max_examples=300, deadline=None)
@given(
    texto=st.text(alphabet="abcxyz 0123", max_size=60),
    segredos=st.lists(st.text(alphabet="abcxyz0123", min_size=1, max_size=5), max_size=4),
)
def test_propriedade_segredo_nunca_sobra_no_texto(texto: str, segredos: list[str]) -> None:
    """Propriedade: nenhum segredo (não vazio, sem caracteres da máscara) sobrevive."""
    saida = redige(texto, segredos)
    for segredo in segredos:
        assert segredo not in saida


# -- executor: log com senha, \r e padrões de ambiente ---------------------
def _executor(path: Path, body: str, options_text: str = "") -> tuple[Executor, list[str]]:
    path.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name T\n" + options_text + "#@step um\n" + body,
        encoding="utf-8",
    )
    script = parse_script(path)
    textos: list[str] = []
    executor = Executor(
        script,
        build_plan(script),
        helpers=HELPERS,
        log_sink=lambda event: textos.append(event.text) if isinstance(event, LogLine) else None,
    )
    return executor, textos


def test_log_do_step_nao_mostra_valor_de_senha(tmp_path: Path) -> None:
    executor, textos = _executor(
        tmp_path / "senha.kbash",
        'um() { echo "a senha e $OPT_SENHA"; }\n',
        '#@option senha type=password label="Senha" default=s3nha-secreta\n',
    )
    executor.run()
    assert any("a senha e " in texto for texto in textos)
    assert not any("s3nha-secreta" in texto for texto in textos)


def test_cr_mostra_so_o_estado_final_da_linha(tmp_path: Path) -> None:
    corpo = "um() { printf '10%%\\r50%%\\r100%%\\n'; echo fim; }\n"
    executor, textos = _executor(tmp_path / "cr.kbash", corpo)
    executor.run()
    assert "100%" in textos
    assert "fim" in textos


def test_cr_lf_no_fim_da_linha_nao_perde_o_texto(tmp_path: Path) -> None:
    executor, textos = _executor(tmp_path / "crlf.kbash", "um() { printf 'linha\\r\\n'; }\n")
    executor.run()
    assert "linha" in textos


@pytest.mark.parametrize(("chave", "padrao"), [("TERM", "dumb"), ("DEBIAN_FRONTEND", "noninteractive")])
def test_padrao_de_ambiente_quando_ausente(tmp_path: Path, monkeypatch, chave: str, padrao: str) -> None:
    monkeypatch.delenv(chave, raising=False)
    executor, textos = _executor(tmp_path / f"{chave}.kbash", f'um() {{ echo "v=${{{chave}}}"; }}\n')
    executor.run()
    assert f"v={padrao}" in textos


def test_padrao_de_ambiente_nao_sobrescreve_o_usuario(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TERM", "xterm-256color")
    executor, textos = _executor(tmp_path / "term.kbash", 'um() { echo "v=$TERM"; }\n')
    executor.run()
    assert "v=xterm-256color" in textos


# -- ações: a saída também é redigida -------------------------------------
def test_saida_de_acao_nao_mostra_senha(tmp_path: Path) -> None:
    from kbash.core.actions import run_action

    path = tmp_path / "acao.kbash"
    path.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name A\n"
        '#@option senha type=password label="Senha" default=ouro-123\n'
        "#@action mostra\nmostra() { echo \"senha=$OPT_SENHA\"; }\n",
        encoding="utf-8",
    )
    script = parse_script(path)
    action = script.action("mostra")
    assert action is not None
    result = run_action(script, action, {"senha": "ouro-123"}, None, helpers=HELPERS, workdir=str(tmp_path))
    assert result.status == "ok"
    assert "ouro-123" not in result.output
    assert MASCARA in result.output
