#!/usr/bin/env bash
# Exemplo do BashRT: exercita TODOS os tipos de opção (§4.3) e de prompt (§8.4).
#
# Seguro: só echo e mktemp; nada é instalado. Valide com:
#   rt check examples/all-options.sh
# Rode sem GUI (responde tudo com os padrões):
#   rt run --headless --yes examples/all-options.sh
#
#@runtime 1
#@name Todos os tipos de opção
#@description Demonstração de todos os widgets e prompts do runtime.
#@version 1.0.0
#@author Equipe BashRT
#@icon applications-development

# -- texto e escolha ------------------------------------------------------
#@option intro type=paragraph label="Este exemplo mostra todos os tipos de opção. Parágrafos e links só exibem: não geram OPT_*."
#@option docs_link type=link label="Documentação do exemplo" url="https://example.org/bashrt"
#@option user_name type=string label="Seu nome" required=true default="Ana Silva" pattern="^[a-zA-Z ]+$" minlen=2 maxlen=30 help="Só letras e espaços"
#@option editor type=choice label="Editor" choices="vim,nano,micro" default=nano
#@option plugins type=multi label="Plugins" choices="lua,python,git" default=lua
#@option token type=password label="Token de acesso"
#@option telemetry type=bool label="Enviar telemetria" default=false

# -- arquivos e pastas ----------------------------------------------------
#@option dir type=path label="Pasta de destino" default="$HOME/dev"
#@option avatar type=file label="Foto de perfil" filters="*.png,*.jpg"
#@option docs type=file label="Documentos" multiple=true help="Pode escolher vários"

# -- números e data/hora --------------------------------------------------
#@option retries type=number label="Tentativas" min=1 max=10 default=3
#@option volume type=slider label="Volume" min=0 max=100 step=5 default=50
#@option deadline type=date label="Prazo" default="2026-12-31"
#@option alarm type=time label="Horário" default="08:30"

# -- texto longo e condicional --------------------------------------------
#@option notes type=text label="Observações"
#@option mode type=choice label="Modo" choices="simple,advanced" default=simple
#@option advanced_opt type=string label="Opção avançada" show_if="mode=advanced"

#@step show_options
#@title Mostrar opções
#@desc Imprime cada OPT_* (senha nunca aparece no log).
#@group Opções
show_options() {
    rt_log "nome=[$OPT_USER_NAME] editor=[$OPT_EDITOR] plugins=[$OPT_PLUGINS]"
    rt_log "telemetria=[$OPT_TELEMETRY] dir=[$OPT_DIR]"
    rt_log "tentativas=[$OPT_RETRIES] volume=[$OPT_VOLUME]"
    rt_log "prazo=[$OPT_DEADLINE] hora=[$OPT_ALARM] modo=[$OPT_MODE]"
    rt_log "foto=[$OPT_AVATAR] docs=[$OPT_DOCS]"
    rt_log "notas=[$OPT_NOTES] avancada=[$OPT_ADVANCED_OPT]"
    rt_log "token=[oculto de propósito: senha nunca vai para o log]"
}

#@step ask_everything
#@title Perguntar tudo
#@desc Um prompt de cada kind (§8.4), incluindo os novos.
#@group Prompts
#@depends show_options
ask_everything() {
    if rt_confirm "Continuar a demonstração?" y; then
        rt_log "confirm: sim"
    else
        rt_log "confirm: não"
    fi

    local nome numero prazo hora foto texto
    nome=$(rt_input "Seu nome" "$OPT_USER_NAME")
    numero=$(rt_number "Tentativas" "$OPT_RETRIES" 1 10)
    prazo=$(rt_date "Prazo" "$OPT_DEADLINE")
    hora=$(rt_time "Hora" "$OPT_ALARM")
    foto=$(rt_file "Foto" "$OPT_AVATAR" "*.png" "*.jpg")
    texto=$(rt_text "Observações" "$OPT_NOTES")
    rt_log "input=[$nome] number=[$numero] date=[$prazo] time=[$hora]"
    rt_log "file=[$foto] text=[$texto]"

    local segredo editor plugins
    segredo=$(rt_secret "Token (não aparece no log)")
    editor=$(rt_choice "Editor" vim nano micro)
    plugins=$(rt_multi "Plugins" lua python git)
    rt_log "secret=[oculto] choice=[$editor]"
    rt_log "multi=[$plugins]"

    rt_textbox "Sobre este exemplo" "Este diálogo só informa (kdialog --textbox): fechar responde ok."

    local win i
    win=$(rt_progresswin_start 5 "Demonstrando progresso")
    for i in 1 2 3 4 5; do
        sleep 0.2
        rt_progresswin_update "$win" "$i" "passo $i de 5"
    done
    rt_progresswin_done "$win"
    rt_log "demonstração concluída"
}
