#!/usr/bin/env bash
# Sober Optimizer v2 — reescrito para o BashRT atual.
#
# O que mudou em relação à v1 de terminal puro:
# - perfil, backup e FRM viraram opções tipadas do formulário (`#@option`):
#   choice, bool, path condicional (`show_if`), number com faixa;
# - FRM usa `rt_number` (sem loop manual de validação);
# - salvamento mostra `rt_progresswin_*` (estilo kdialog --progressbar);
# - resumo final via `rt_textbox`;
# - 4 steps encadeados (`depends`) em vez de 1 função gigante;
# - cores e banner só no terminal (no app o log fica sem escapes ANSI).
#
# Roda sozinho no terminal E dentro do app `rt` (fallbacks embutidos).
#@runtime 1
#@name Sober Optimizer
#@description Configura o Sober (Roblox): perfis prontos ou ajuste fino, com backup opcional.
#@version 2.0.0
#@icon applications-games
#@strict true

#@option profile type=choice label="Perfil" choices="Recommended,Maximum FPS,Quality,Custom" default=Recommended help="Preset aplicado; Custom abre o ajuste fino"
#@option backup type=bool label="Backup antes de salvar" default=true
#@option backup_dir type=path label="Pasta do backup" default="$HOME" show_if="backup=1"
#@option graphics_mode type=choice label="Gráficos (Custom)" choices="performance,balanced" default=balanced show_if="profile=Custom"
#@option frm_enabled type=bool label="Override de FRM (Custom)" default=false show_if="profile=Custom"
#@option frm_value type=number label="Nível do FRM (Custom)" min=1 max=21 default=3 show_if="profile=Custom,frm_enabled=1" help="1 = mín (mais FPS), 21 = máx (mais qualidade)"
#@option discord_rpc type=bool label="Discord RPC (Custom)" default=false show_if="profile=Custom"
#@option discord_join type=bool label="Botão join (Custom)" default=false show_if="profile=Custom,discord_rpc=1"
#@option gamemode type=bool label="GameMode (Custom)" default=true show_if="profile=Custom"
#@option gamepad type=bool label="Gamepad (Custom)" default=false show_if="profile=Custom"

# Dentro do app, o runtime injeta os helpers `rt_*`. Sozinho no terminal,
# tenta um `rt.sh` ao lado do script; sem ele, avisa em vez de quebrar mudo.
if ! declare -F rt_confirm >/dev/null 2>&1; then
    _dir="$(dirname "${BASH_SOURCE[0]:-$0}")"
    if [ -f "$_dir/rt.sh" ]; then
        # shellcheck disable=SC1090
        source "$_dir/rt.sh"
    else
        echo "Faltam os helpers rt_*: execute com 'rt run $0'." >&2
        exit 2
    fi
    unset _dir
fi

# Fora do runtime não há OPT_* — assume os padrões do formulário.
if [ "${RT_MODE:-}" != "step" ]; then
    : "${OPT_PROFILE:=Recommended}"
    : "${OPT_BACKUP:=1}"
    : "${OPT_BACKUP_DIR:=$HOME}"
    : "${OPT_GRAPHICS_MODE:=balanced}"
    : "${OPT_FRM_ENABLED:=0}"
    : "${OPT_FRM_VALUE:=3}"
    : "${OPT_DISCORD_RPC:=0}"
    : "${OPT_DISCORD_JOIN:=0}"
    : "${OPT_GAMEMODE:=1}"
    : "${OPT_GAMEPAD:=0}"
fi

# Cores só com TTY: no app o stdout vai para o painel de log e os
# escapes sujariam cada linha (eram visíveis como `[0;35m` etc.).
if [ -t 1 ]; then
    RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
    CYAN='\033[0;36m'; MAGENTA='\033[0;35m'; BLUE='\033[0;34m'
    WHITE='\033[1;37m'; NC='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''
    MAGENTA=''; BLUE=''; WHITE=''; NC=''
fi

CONFIG_DEST="$HOME/.var/app/org.vinegarhq.Sober/config/sober/config.json"

DEFAULT_GRAPHICS_MODE="balanced"
DEFAULT_FRM_FLAG="FFlagExample"
DEFAULT_FRM_VALUE=""
DEFAULT_DISCORD_RPC=false
DEFAULT_DISCORD_JOIN=false
DEFAULT_GAMEMODE=true
DEFAULT_GAMEPAD=false

CONFIG_HEADER='// !!! STOP !!!
// This file is not meant to be edited by hand unless you know what you are doing. You are encouraged to use the settings menu instead (Right click Sober in your apps menu, then hit "Settings")
// You can prevent Sober from launching by improperly formatting this file'"'"'s JSON, or possibly mess up the Roblox engine by toggling certain flags intended for Roblox engineers.
// Incase you mess up, you can reset this file by deleting it. It will be recreated the next time you launch Sober.
// -------------------------------------------
// Documentation is available at https://vinegarhq.org/Sober/Configuration/index.html - We encourage you to read it before toggling anything.'

print_banner() {
    [ -t 1 ] || return 0
    echo -e "${MAGENTA}"
    echo "  ██████╗  ██████╗ ██████╗ ███████╗██████╗ "
    echo "  ██╔════╝██╔═══██╗██╔══██╗██╔════╝██╔══██╗"
    echo "  ███████╗██║   ██║██████╔╝█████╗  ██████╔╝"
    echo "  ╚════██║██║   ██║██╔══██╗██╔══╝  ██╔══██╗"
    echo "  ███████║╚██████╔╝██████╔╝███████╗██║  ██║"
    echo "  ╚══════╝ ╚═════╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝"
    echo -e "${CYAN}"
    echo "  ██████╗ ██████╗ ████████╗██╗███╗   ███╗██╗███████╗███████╗██████╗ "
    echo "  ██╔══██╗██╔══██╗╚══██╔══╝██║████╗ ████║██║╚══███╔╝██╔════╝██╔══██╗"
    echo "  ██║  ██║██████╔╝   ██║   ██║██╔████╔██║██║  ███╔╝ █████╗  ██████╔╝"
    echo "  ██║  ██║██╔═══╝    ██║   ██║██║╚██╔╝██║██║ ███╔╝  ██╔══╝  ██╔══██╗"
    echo "  ██████╔╝██║        ██║   ██║██║ ╚═╝ ██║██║███████╗███████╗██║  ██║"
    echo "  ╚═════╝ ╚═╝        ╚═╝   ╚═╝╚═╝     ╚═╝╚═╝╚══════╝╚══════╝╚═╝  ╚═╝"
    echo -e "${NC}"
}

ask_yn() {
    # Dentro do app abre o diálogo; sozinho, cai para `read -p`.
    rt_confirm "$1"
}

read_current_config() {
    if [ ! -f "$CONFIG_DEST" ]; then
        return
    fi
    _cfg_graphics=$(grep -o '"graphics_optimization_mode": *"[^"]*"' "$CONFIG_DEST" | grep -o '"[^"]*"$' | tr -d '"' || true)
    _cfg_frm=$(grep -o '"DFIntDebugFRMQualityLevelOverride": *[0-9]*' "$CONFIG_DEST" | grep -o '[0-9]*$' || true)
    _cfg_discord_rpc=$(grep -o '"discord_rpc_enabled": *[a-z]*' "$CONFIG_DEST" | grep -o '[a-z]*$' || true)
    _cfg_discord_join=$(grep -o '"discord_rpc_show_join_button": *[a-z]*' "$CONFIG_DEST" | grep -o '[a-z]*$' || true)
    _cfg_gamemode=$(grep -o '"enable_gamemode": *[a-z]*' "$CONFIG_DEST" | grep -o '[a-z]*$' || true)
    _cfg_gamepad=$(grep -o '"allow_gamepad_permission": *[a-z]*' "$CONFIG_DEST" | grep -o '[a-z]*$' || true)
}

backup_config() {
    local backup_dest="$1/sober-config.json.backup-$(date +%Y%m%d-%H%M%S)"

    if cp -- "$CONFIG_DEST" "$backup_dest"; then
        echo -e "${GREEN}✔ Backup created at:${NC}"
        echo -e "${WHITE}  $backup_dest${NC}"
        return 0
    fi

    echo -e "${RED}Could not create the backup. Configuration was not saved.${NC}"
    return 1
}

apply_profile() {
    case "$PROFILE" in
        Recommended)
            GRAPHICS_MODE="performance"
            FRM_ENABLED=true
            FRM_VALUE=3
            DISCORD_RPC=true
            DISCORD_JOIN=true
            GAMEMODE=true
            GAMEPAD=false
            ;;
        "Maximum FPS")
            GRAPHICS_MODE="performance"
            FRM_ENABLED=true
            FRM_VALUE=1
            DISCORD_RPC=false
            DISCORD_JOIN=false
            GAMEMODE=true
            GAMEPAD=false
            ;;
        Quality)
            GRAPHICS_MODE="balanced"
            FRM_ENABLED=false
            FRM_VALUE=10
            DISCORD_RPC=true
            DISCORD_JOIN=true
            GAMEMODE=true
            GAMEPAD=false
            ;;
    esac

    CHANGED=false
    if [ "$GRAPHICS_MODE" != "$CUR_GRAPHICS" ]; then CHANGED=true; fi
    if [ "$FRM_ENABLED" = true ] && [ "$FRM_VALUE" != "$CUR_FRM" ]; then CHANGED=true; fi
    if [ "$FRM_ENABLED" = false ] && [ -n "$CUR_FRM" ]; then CHANGED=true; fi
    if [ "$DISCORD_RPC" != "$CUR_DISCORD_RPC" ]; then CHANGED=true; fi
    if [ "$DISCORD_JOIN" != "$CUR_DISCORD_JOIN" ]; then CHANGED=true; fi
    if [ "$GAMEMODE" != "$CUR_GAMEMODE" ]; then CHANGED=true; fi
    if [ "$GAMEPAD" != "$CUR_GAMEPAD" ]; then CHANGED=true; fi
}

#@step read_current
#@title Ler configuração atual
#@desc Lê o config.json existente e guarda os valores para os próximos steps.
#@group Preparação
read_current() {
    print_banner
    read_current_config

    rt_set cur_graphics "${_cfg_graphics:-$DEFAULT_GRAPHICS_MODE}"
    rt_set cur_frm "${_cfg_frm:-}"
    rt_set cur_discord_rpc "${_cfg_discord_rpc:-$DEFAULT_DISCORD_RPC}"
    rt_set cur_discord_join "${_cfg_discord_join:-$DEFAULT_DISCORD_JOIN}"
    rt_set cur_gamemode "${_cfg_gamemode:-$DEFAULT_GAMEMODE}"
    rt_set cur_gamepad "${_cfg_gamepad:-$DEFAULT_GAMEPAD}"
    if [ -f "$CONFIG_DEST" ]; then
        rt_set has_config 1
    else
        rt_set has_config 0
    fi
    rt_log "config atual lida"
}

#@step backup_files
#@title Backup da configuração
#@desc Copia o config.json atual (só se existir e o backup estiver ligado).
#@group Preparação
#@depends read_current
backup_files() {
    if [ "$(rt_get has_config)" != "1" ]; then
        rt_log "sem config anterior: nada para copiar"
        return 0
    fi
    if [ "$OPT_BACKUP" != "1" ]; then
        rt_log "backup desligado nas opções"
        return 0
    fi
    backup_config "$OPT_BACKUP_DIR"
}

#@step tune
#@title Ajustar perfil
#@desc Aplica o preset ou abre o ajuste fino interativo.
#@group Ajuste
#@depends backup_files
tune() {
    local CUR_GRAPHICS CUR_FRM CUR_DISCORD_RPC CUR_DISCORD_JOIN CUR_GAMEMODE CUR_GAMEPAD
    CUR_GRAPHICS=$(rt_get cur_graphics)
    CUR_FRM=$(rt_get cur_frm)
    CUR_DISCORD_RPC=$(rt_get cur_discord_rpc)
    CUR_DISCORD_JOIN=$(rt_get cur_discord_join)
    CUR_GAMEMODE=$(rt_get cur_gamemode)
    CUR_GAMEPAD=$(rt_get cur_gamepad)

    PROFILE="$OPT_PROFILE"
    GRAPHICS_MODE="$CUR_GRAPHICS"
    FRM_VALUE="${CUR_FRM:-1}"
    FRM_ENABLED=false
    [ -n "$CUR_FRM" ] && FRM_ENABLED=true
    DISCORD_RPC="$CUR_DISCORD_RPC"
    DISCORD_JOIN="$CUR_DISCORD_JOIN"
    GAMEMODE="$CUR_GAMEMODE"
    GAMEPAD="$CUR_GAMEPAD"

    rt_log "perfil: $PROFILE"

    if [ "$PROFILE" != "Custom" ]; then
        apply_profile
    else
        CHANGED=false
    fi

    if [ "$PROFILE" = "Custom" ]; then
        # tudo veio do formulário (opções com show_if): aqui só
        # compara com o atual para detectar mudança
        GRAPHICS_MODE="$OPT_GRAPHICS_MODE"
        if [ "$OPT_FRM_ENABLED" = "1" ]; then
            FRM_ENABLED=true
            FRM_VALUE="$OPT_FRM_VALUE"
        else
            FRM_ENABLED=false
        fi
        if [ "$OPT_DISCORD_RPC" = "1" ]; then
            DISCORD_RPC=true
            if [ "$OPT_DISCORD_JOIN" = "1" ]; then
                DISCORD_JOIN=true
            else
                DISCORD_JOIN=false
            fi
        else
            DISCORD_RPC=false
            DISCORD_JOIN=false
        fi
        if [ "$OPT_GAMEMODE" = "1" ]; then GAMEMODE=true; else GAMEMODE=false; fi
        if [ "$OPT_GAMEPAD" = "1" ]; then GAMEPAD=true; else GAMEPAD=false; fi

        CHANGED=false
        if [ "$GRAPHICS_MODE" != "$CUR_GRAPHICS" ]; then CHANGED=true; fi
        if [ "$FRM_ENABLED" = true ] && [ "$FRM_VALUE" != "$CUR_FRM" ]; then CHANGED=true; fi
        if [ "$FRM_ENABLED" = false ] && [ -n "$CUR_FRM" ]; then CHANGED=true; fi
        if [ "$DISCORD_RPC" != "$CUR_DISCORD_RPC" ]; then CHANGED=true; fi
        if [ "$DISCORD_JOIN" != "$CUR_DISCORD_JOIN" ]; then CHANGED=true; fi
        if [ "$GAMEMODE" != "$CUR_GAMEMODE" ]; then CHANGED=true; fi
        if [ "$GAMEPAD" != "$CUR_GAMEPAD" ]; then CHANGED=true; fi
    fi

    rt_set graphics_mode "$GRAPHICS_MODE"
    rt_set frm_enabled "$FRM_ENABLED"
    rt_set frm_value "$FRM_VALUE"
    rt_set discord_rpc "$DISCORD_RPC"
    rt_set discord_join "$DISCORD_JOIN"
    rt_set gamemode "$GAMEMODE"
    rt_set gamepad "$GAMEPAD"
    if $CHANGED; then
        rt_set changed 1
    else
        rt_set changed 0
    fi
}

#@step save
#@title Revisar e salvar
#@desc Mostra o resumo, confirma e grava o config.json.
#@group Aplicar
#@depends tune
save() {
    if [ "$(rt_get changed)" != "1" ]; then
        echo -e "${GREEN}✔ No changes detected. Config is already up to date!${NC}\n"
        return 0
    fi

    print_field() {
        local label="$1" new="$2" cur="$3"
        if [ "$new" != "$cur" ]; then
            echo -e "${BLUE}║${NC}  $label : ${RED}$cur${NC} → ${GREEN}$new${NC}"
        else
            echo -e "${BLUE}║${NC}  $label : ${WHITE}$new${NC}"
        fi
    }

    summary() {
        echo "Sober Configuration — summary"
        print_field "Graphics mode  " "$(rt_get graphics_mode)"   "$(rt_get cur_graphics)"
        if [ "$(rt_get frm_enabled)" = true ]; then
            print_field "FRM Override   " "$(rt_get frm_value)"    "$(rt_get cur_frm)"
        else
            echo -e "${BLUE}║${NC}  FRM Override   : ${WHITE}disabled${NC}"
        fi
        print_field "Discord RPC    " "$(rt_get discord_rpc)"     "$(rt_get cur_discord_rpc)"
        print_field "Join Button    " "$(rt_get discord_join)"     "$(rt_get cur_discord_join)"
        print_field "GameMode       " "$(rt_get gamemode)"         "$(rt_get cur_gamemode)"
        print_field "Gamepad        " "$(rt_get gamepad)"          "$(rt_get cur_gamepad)"
    }

    echo -e "${BLUE}╔═════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${WHITE}                Summary                  ${BLUE}║${NC}"
    echo -e "${BLUE}╠═════════════════════════════════════════╣${NC}"
    summary
    echo -e "${BLUE}╚═════════════════════════════════════════╝${NC}\n"

    rt_textbox "Summary" "$(summary | sed 's/\x1b\[[0-9;]*m//g')"
    # default sim: em --yes o salvar acontece (só a escolha explícita pula)
    rt_confirm "Save configuration?" y || return 0

    if [ ! -d "$(dirname "$CONFIG_DEST")" ]; then
        echo -e "${YELLOW}Creating directory...${NC}"
        mkdir -p "$(dirname "$CONFIG_DEST")"
    fi

    local win
    win=$(rt_progresswin_start 3 "Saving configuration")
    if [ "$(rt_get frm_enabled)" = true ]; then
        FFLAGS_BLOCK="\"fflags\": {
        \"DFIntDebugFRMQualityLevelOverride\": $(rt_get frm_value)
    }"
    else
        FFLAGS_BLOCK="\"fflags\": {
        \"FFlagExample\": true
    }"
    fi
    rt_progresswin_update "$win" 1 "Writing file"

    {
        echo "$CONFIG_HEADER"
        cat <<EOF
{
    "allow_gamepad_permission": $(rt_get gamepad),
    "close_on_leave": false,
    "discord_rpc_enabled": $(rt_get discord_rpc),
    "discord_rpc_show_join_button": $(rt_get discord_join),
    "enable_gamemode": $(rt_get gamemode),
    "enable_hidpi": false,
    $FFLAGS_BLOCK,
    "graphics_optimization_mode": "$(rt_get graphics_mode)",
    "server_location_indicator_enabled": false,
    "touch_mode": "off",
    "use_console_experience": false,
    "use_libsecret": false,
    "use_opengl": false
}
EOF
    } > "$CONFIG_DEST"
    rt_progresswin_update "$win" 2 "Verifying"
    [ -s "$CONFIG_DEST" ] || rt_fail "config vazio após salvar"
    rt_progresswin_update "$win" 3 "Done"
    rt_progresswin_done "$win"

    echo -e "\n${GREEN}✔ Configuration saved successfully to:${NC}"
    echo -e "${WHITE}  $CONFIG_DEST${NC}\n"
    rt_notify "Configuração do Sober salva"
}

if [ "${RT_MODE:-}" != "step" ]; then
while true; do
    clear
    print_banner
    echo -e "${BLUE}╔═════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║${WHITE}        Sober Optimizer Installer        ${BLUE}║${NC}"
    echo -e "${BLUE}╠═════════════════════════════════════════╣${NC}"
    echo -e "${BLUE}║  ${GREEN}1)${WHITE} Configure and apply optimizations    ${BLUE}║${NC}"
    echo -e "${BLUE}║  ${RED}2)${WHITE} Exit                                 ${BLUE}║${NC}"
    echo -e "${BLUE}╚═════════════════════════════════════════╝${NC}"
    echo -e "${YELLOW}"
    read -p "  Select an option: " option
    echo -e "${NC}"

    case $option in
        1)
            read_current
            backup_files
            tune
            save
            ;;
        2)
            echo -e "${RED}Exiting.${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid option. Please try again.${NC}"
            ;;
    esac
done
fi
