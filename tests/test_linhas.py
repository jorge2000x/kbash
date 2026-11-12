"""Limite de bytes por linha nos leitores de stream (bug 9): IPC e log do executor.

Uma linha sem quebra não pode crescer sem limite na memória. Linha acima do limite é
descartada (IPC) ou truncada com marcador (log); a linha seguinte sempre passa.
"""

from __future__ import annotations

import io
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from kbash.core.linhas import LeitorDeLinhas, linhas_limitadas


def test_linha_dentro_do_limite_passa() -> None:
    leitor = LeitorDeLinhas(limite=10)
    assert leitor.alimenta("oi\nlá\n".encode()) == [b"oi", "lá".encode()]
    assert leitor.descartadas == 0


def test_linha_acima_do_limite_e_descartada_e_a_seguinte_passa() -> None:
    leitor = LeitorDeLinhas(limite=5)
    assert leitor.alimenta(b"123456789\nok\n") == [b"ok"]
    assert leitor.descartadas == 1


def test_linha_longa_quebrada_em_pedacos_nao_cresce_na_memoria() -> None:
    leitor = LeitorDeLinhas(limite=5)
    for _ in range(1000):
        assert leitor.alimenta(b"x" * 100) == []
    assert len(leitor._resto) <= 5  # o invariante de memória é o ponto do teste
    assert leitor.alimenta(b"fim\nok\n") == [b"ok"]  # "fim" é o final da linha longa
    assert leitor.descartadas == 1


def test_linha_parcial_no_fim_sai_so_em_fecha() -> None:
    leitor = LeitorDeLinhas(limite=10)
    assert leitor.alimenta(b"sem fim") == []
    assert leitor.fecha() == [b"sem fim"]
    assert leitor.fecha() == []


def test_fecha_ignora_pendente_so_com_espacos() -> None:
    leitor = LeitorDeLinhas(limite=10)
    leitor.alimenta(b"   ")
    assert leitor.fecha() == []


def test_fecha_descarta_resto_longo() -> None:
    leitor = LeitorDeLinhas(limite=3)
    leitor.alimenta(b"abcdefgh")
    assert leitor.fecha() == []
    assert leitor.descartadas == 1


@settings(max_examples=200, deadline=None)
@given(
    linhas=st.lists(st.binary(max_size=30).filter(lambda b: b"\n" not in b), max_size=15),
    cortes=st.lists(st.integers(min_value=0, max_value=600), max_size=20),
)
def test_resultado_independe_de_como_o_stream_e_fatiado(linhas: list[bytes], cortes: list[int]) -> None:
    """Propriedade: com limite folgado, o fatiamento do stream não muda as linhas."""
    data = b"".join(linha + b"\n" for linha in linhas)
    esperado = list(linhas)

    leitor = LeitorDeLinhas(limite=10_000)
    obtidas: list[bytes] = []
    inicio = 0
    for corte in sorted(set(cortes)):
        pos = min(corte, len(data))
        if pos > inicio:
            obtidas.extend(leitor.alimenta(data[inicio:pos]))
            inicio = pos
    obtidas.extend(leitor.alimenta(data[inicio:]))
    obtidas.extend(leitor.fecha())

    assert obtidas == esperado
    assert leitor.descartadas == 0


def test_stream_longo_e_truncado_com_marcador_de_descarte() -> None:
    fluxo = io.BytesIO(b"a" * 50 + b"\n" + b"curta\n")
    partes = list(linhas_limitadas(fluxo, limite=10))
    assert partes[0] == (b"a" * 10, True)
    assert partes[-1] == (b"curta\n", False)


def test_stream_linha_no_limite_exato_nao_e_truncada() -> None:
    fluxo = io.BytesIO(b"abcdefghi\n")  # 10 bytes com \n, limite 10
    assert list(linhas_limitadas(fluxo, limite=10)) == [(b"abcdefghi\n", False)]


def test_log_do_executor_trunca_linha_gigante(tmp_path: Path) -> None:
    from fixtures.paths import HELPERS

    from kbash.core.events import LogLine
    from kbash.core.executor import Executor
    from kbash.core.linhas import MAX_LOG_LINE
    from kbash.core.parser import parse_script
    from kbash.core.planner import build_plan

    script_path = tmp_path / "gigante.sh"
    script_path.write_text(
        "#!/usr/bin/env bash\n#@runtime 1\n#@name G\n#@step um\n"
        "um() { head -c 300000 /dev/zero | tr '\\0' x; echo; echo fim-da-saida; }\n",
        encoding="utf-8",
    )
    script = parse_script(script_path)
    textos: list[str] = []
    executor = Executor(
        script,
        build_plan(script),
        helpers=HELPERS,
        log_sink=lambda event: textos.append(event.text) if isinstance(event, LogLine) else None,
    )
    executor.run()
    assert any(texto.endswith("[linha truncada]") for texto in textos)
    assert all(len(texto) <= MAX_LOG_LINE + len(" [linha truncada]") for texto in textos)
    assert "fim-da-saida" in textos
