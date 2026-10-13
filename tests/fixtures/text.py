MINIMAL = """\
#!/usr/bin/env bash
#@runtime 1
#@name Mínimo

#@step ola
#@title Saudação
ola() { echo "olá"; }
"""

NO_RUNTIME = """\
#!/usr/bin/env bash
#@name Sem runtime

#@step ola
ola() { echo "olá"; }
"""

FUTURE_RUNTIME = """\
#@runtime 99
#@name Do futuro

#@step ola
ola() { echo "olá"; }
"""

NO_NAME = """\
#@runtime 1

#@step ola
ola() { echo "olá"; }
"""

DUPLICATE_STEP = """\
#@runtime 1
#@name Duplicados

#@step ola
ola() { echo "um"; }

#@step ola
ola() { echo "dois"; }
"""

DUPLICATE_OPTION = """\
#@runtime 1
#@name Duplicados

#@option nome type=string
#@option nome type=string

#@step ola
ola() { echo "olá"; }
"""

OPTION_STEP_ID_CLASH = """\
#@runtime 1
#@name Choque

#@option editor type=string
#@step editor
editor() { echo "oi"; }
"""

MISSING_FUNCTION = """\
#@runtime 1
#@name Sem função

#@step ola
ola() { echo "olá"; }

#@step fantasma
outra_funcao() { :; }
"""

BAD_DEPENDS = """\
#@runtime 1
#@name Dependência inexistente

#@step ola
#@depends fantasma
ola() { echo "olá"; }
"""

CYCLE = """\
#@runtime 1
#@name Ciclo

#@step a
#@depends b
a() { echo a; }

#@step b
#@depends a
b() { echo b; }
"""

CHOICE_NO_CHOICES = """\
#@runtime 1
#@name Choice sem escolhas

#@option editor type=choice
#@step ola
ola() { echo "$OPT_EDITOR"; }
"""

DEFAULT_OUTSIDE_CHOICES = """\
#@runtime 1
#@name Default inválido

#@option editor type=choice choices="vim,nano" default=emacs
#@step ola
ola() { echo "$OPT_EDITOR"; }
"""

UNKNOWN_DIRECTIVE = """\
#@runtime 1
#@name Diretiva do futuro
#@frobnicate sim

#@step ola
ola() { echo "olá"; }
"""

LOOSE_TOP_LEVEL = """\
#@runtime 1
#@name Solto no topo

#@step ola
ola() { echo "olá"; }

echo "comando solto"
date >/dev/null
"""

BLOCK_WITHOUT_FUNCTION = """\
#@runtime 1
#@name Bloco órfão

#@step ola
echo "não sou função"
"""

LATE_ANNOTATION = """\
#@runtime 1
#@name Anotação atrasada

echo "antes"

#@step ola
ola() { echo "olá"; }
"""

OPTION_MULTILINE = """\
#@runtime 1
#@name Opções multilinha

#@option editor
#@label "Editor"
#@choices "vim,nano"
#@default nano

#@option nome type=string required=true
#@help "Usado no git"

#@step ola
ola() { echo "$OPT_EDITOR $OPT_NOME"; }
"""

ATTRIBUTES = """\
#@runtime 1
#@name Atributos
#@id com.exemplo.attrs
#@description Uma linha.
#@description Outra linha.
#@version 2.1.0
#@author Fulano
#@icon computer
#@requires curl,git
#@strict false

#@option editor type=choice label="Editor" choices="vim,nano" default=nano help="Usado pelo git"
#@option name type=string label="Seu nome" required=true
#@option token type=password label="Token"
#@option dir type=path label="Pasta" default="$HOME/dev"
#@option plugins type=multi label="Plugins" choices="a,b,c" default=a
#@option telemetry type=bool label="Telemetria" default=false

#@step update_index
#@title Atualizar índice
#@desc Primeira linha.
#@desc Segunda linha.
#@group Preparação
#@default on
#@root true
#@timeout 900
#@on_error continue
update_index() { :; }

#@step install_tools
#@title Instalar ferramentas
#@group Ferramentas
#@default off
#@depends update_index
#@required
install_tools() { :; }
"""
