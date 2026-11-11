"""Caracterização de ``OptionModel.data``: cada papel de cada tipo de opção.

Os valores esperados foram medidos no comportamento atual, antes da refatoração de
``data()`` (um ``match`` gigante). A refatoração não pode mudar nenhum deles.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QModelIndex

from kbash.core.parser import parse_script
from kbash.gui.models import OptionModel

SCRIPT = """#!/usr/bin/env bash
#@runtime 1
#@name Modelo
#@option nome type=string label="Nome" required default="x" help="ajuda"
#@option idade type=number label="Idade" min=0 max=120 step=1 default=30
#@option cor type=choice label="Cor" choices="azul,verde" default=verde
#@option arq type=file label="Arquivo" filters="*.txt,*.md" multiple
#@option senha type=password label="Senha" minlen=4 maxlen=8 pattern="^[a-z]+$"
#@option link type=link label="Docs" url="https://example.org"
#@option grupo type=string label="G" group="Avançado"
"""

ESPERADO = [{'optId': 'nome',
  'type': 'string',
  'label': 'Nome',
  'value': 'Ana',
  'choices': [],
  'required': False,
  'error': '',
  'help': 'ajuda',
  'default': 'x',
  'minimum': '',
  'maximum': '',
  'step': '',
  'filters': [],
  'pattern': '',
  'minlen': '',
  'maxlen': '',
  'multiple': False,
  'visible': True,
  'url': '',
  'owner': '',
  'group': ''},
 {'optId': 'idade',
  'type': 'number',
  'label': 'Idade',
  'value': '30',
  'choices': [],
  'required': False,
  'error': '',
  'help': '',
  'default': '30',
  'minimum': '0',
  'maximum': '120',
  'step': '1',
  'filters': [],
  'pattern': '',
  'minlen': '',
  'maxlen': '',
  'multiple': False,
  'visible': True,
  'url': '',
  'owner': '',
  'group': ''},
 {'optId': 'cor',
  'type': 'choice',
  'label': 'Cor',
  'value': 'verde',
  'choices': ['azul', 'verde'],
  'required': False,
  'error': '',
  'help': '',
  'default': 'verde',
  'minimum': '',
  'maximum': '',
  'step': '',
  'filters': [],
  'pattern': '',
  'minlen': '',
  'maxlen': '',
  'multiple': False,
  'visible': True,
  'url': '',
  'owner': '',
  'group': ''},
 {'optId': 'arq',
  'type': 'file',
  'label': 'Arquivo',
  'value': '',
  'choices': [],
  'required': False,
  'error': '',
  'help': '',
  'default': '',
  'minimum': '',
  'maximum': '',
  'step': '',
  'filters': ['*.txt', '*.md'],
  'pattern': '',
  'minlen': '',
  'maxlen': '',
  'multiple': False,
  'visible': True,
  'url': '',
  'owner': '',
  'group': ''},
 {'optId': 'senha',
  'type': 'password',
  'label': 'Senha',
  'value': '',
  'choices': [],
  'required': False,
  'error': '',
  'help': '',
  'default': '',
  'minimum': '',
  'maximum': '',
  'step': '',
  'filters': [],
  'pattern': '^[a-z]+$',
  'minlen': '4',
  'maxlen': '8',
  'multiple': False,
  'visible': True,
  'url': '',
  'owner': '',
  'group': ''},
 {'optId': 'link',
  'type': 'link',
  'label': 'Docs',
  'value': '',
  'choices': [],
  'required': False,
  'error': '',
  'help': '',
  'default': '',
  'minimum': '',
  'maximum': '',
  'step': '',
  'filters': [],
  'pattern': '',
  'minlen': '',
  'maxlen': '',
  'multiple': False,
  'visible': True,
  'url': 'https://example.org',
  'owner': '',
  'group': ''},
 {'optId': 'grupo',
  'type': 'string',
  'label': 'G',
  'value': '',
  'choices': [],
  'required': False,
  'error': '',
  'help': '',
  'default': '',
  'minimum': '',
  'maximum': '',
  'step': '',
  'filters': [],
  'pattern': '',
  'minlen': '',
  'maxlen': '',
  'multiple': False,
  'visible': True,
  'url': '',
  'owner': '',
  'group': 'Avançado'}]


@pytest.fixture(scope="module")
def app(qt_core_app):
    return qt_core_app


def _modelo(tmp_path: Path) -> OptionModel:
    script = tmp_path / "modelo.sh"
    script.write_text(SCRIPT, encoding="utf-8")
    modelo = OptionModel()
    modelo.load(parse_script(script), {"nome": "Ana"})
    return modelo


def test_todos_os_papeis_de_todas_as_linhas(app, tmp_path: Path) -> None:
    modelo = _modelo(tmp_path)
    papeis = {nome.decode(): papel for papel, nome in OptionModel._NAMES.items()}
    assert modelo.rowCount() == len(ESPERADO)
    for linha, esperado in enumerate(ESPERADO):
        indice = modelo.index(linha, 0)
        for nome, valor in esperado.items():
            papel = papeis[nome]
            assert modelo.data(indice, papel) == valor, (linha, nome)


def test_indice_invalido_e_fora_do_intervalo_devolvem_none(app, tmp_path: Path) -> None:
    modelo = _modelo(tmp_path)
    assert modelo.data(QModelIndex(), OptionModel.OptId) is None
    assert modelo.data(modelo.index(0, 0), OptionModel.Visible) is True
    # uma linha além do fim: o índice é inválido para o modelo
    assert modelo.data(modelo.index(len(ESPERADO), 0), OptionModel.OptId) is None


def test_sem_script_nao_ha_dados(app) -> None:
    assert OptionModel().data(QModelIndex(), OptionModel.OptId) is None
