#!/usr/bin/env bash
# Exemplo do BashRT: instala ferramentas e configura o ambiente de development.
# Roda de verdade: use `bashrt check examples/setup-dev.sh` antes.
#
# Este script é seguro: nada é instalado no sistema. Ele escreve apenas dentro de
# $RT_WORKDIR (um diretório temporário criado pelo runtime) e mostra todas as
# funcionalidades do protocolo (§8.4).
#@runtime 1
#@name Configurar ambiente de desenvolvimento
#@description Instala ferramentas básicas e configura o git.
#@version 1.0.0
#@author Equipe BashRT
#@icon applications-development

#@option user_name type=string label="Nome para o git" required=true help="Usado no git config"
#@option editor type=choice label="Editor padrão" choices="vim,nano,micro" default=nano
#@option dir type=path label="Pasta de destino" default="$HOME/dev"
#@option plugins type=multi label="Plugins do editor" choices="lua,python,git" default=lua
#@option telemetry type=bool label="Enviar telemetria" default=false

# Funções auxiliares: código de nível superior idealmente é só definição (§4.5).
tem_ferramenta() {
    command -v "$1" >/dev/null 2>&1
}

relatorio() {
    rt_log "ferramentas: $*"
}

#@step check_tools
#@title Verificar ferramentas
#@desc Vê o que já está instalado na máquina.
#@group Preparação
check_tools() {
    rt_progress 10 "Procurando ferramentas…"

    local encontradas=() faltando=() ferramenta
    for ferramenta in bash git curl tar make; do
        if tem_ferramenta "$ferramenta"; then
            encontradas+=("$ferramenta")
        else
            faltando+=("$ferramenta")
        fi
    done

    relatorio "encontradas: ${encontradas[*]:-nenhuma}"
    if [ ${#faltando[@]} -gt 0 ]; then
        rt_warn "faltando: ${faltando[*]}"
    fi

    rt_set found_count "${#encontradas[@]}"
    rt_progress 100 "Verificação concluída"
}

#@step create_workspace
#@title Criar pasta de trabalho
#@desc Cria a pasta de destino dentro de um diretório temporário.
#@group Preparação
#@depends check_tools
create_workspace() {
    local destino="$RT_WORKDIR/$(basename "$OPT_DIR")"
    mkdir -p "$destino"

    rt_progress 30 "Criando $destino"
    {
        echo "# Scratch do $OPT_USER_NAME"
        echo "criado em $(date --iso-8601=seconds)"
    } > "$destino/README.md"

    rt_set workspace "$destino"
    rt_notify "Pasta criada: $destino"
    rt_progress 100
}

#@step config_git
#@title Configurar o git
#@desc Escreve um .gitconfig de exemplo (nada é alterado no sistema).
#@group Configuração
#@depends create_workspace
#@root true
config_git() {
    #(root true é apenas uma etiqueta para a GUI avisar; a elevação está desligada
    # por enquanto — ver core/executor.py:PRIVILEGE_ELEVATION)

    rt_progress 20 "Escrevendo .gitconfig de exemplo"
    local destino="$RT_VAR_WORKSPACE/gitconfig-exemplo"
    cat > "$destino" <<EOF
[user]
	name = $OPT_USER_NAME
[core]
	editor = $OPT_EDITOR
[extensions]
	plugins = ${OPT_PLUGINS}
[telemetry]
	enabled = $OPT_TELEMETRY
EOF
    rt_progress 80 "Revisando"

    if rt_confirm "Definir esse editor como padrão do git?" y; then
        echo "  editor definido: $OPT_EDITOR"
    else
        echo "  editor mantido como está"
    fi

    local apelido
    apelido=$(rt_input "Apelido para commits" "$OPT_USER_NAME")
    echo "  apelido: $apelido"

    rt_set gitconfig "$destino"
    rt_notify "Git configurado em $destino"
    rt_progress 100
}

#@step summary
#@title Resumo
#@desc Mostra o que foi feito e onde.
#@group Configuração
#@depends config_git
summary() {
    echo
    echo "── resumo ──────────────────────────────"
    echo "  nome:      $OPT_USER_NAME"
    echo "  editor:    $OPT_EDITOR (${OPT_PLUGINS})"
    echo "  pasta:     $RT_VAR_WORKSPACE"
    echo "  gitconfig: $RT_VAR_GITCONFIG"
    echo "  telemetria: $OPT_TELEMETRY"
    echo "──────────────────────────────────────────"
    rt_notify "Ambiente pronto"
}
