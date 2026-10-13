#!/usr/bin/env bash
# rt.sh — helpers do BashRT injetados em cada step (SPEC.md §8.4).
#
# Requisitos (SPEC.md §8.4):
#   * bash puro: sem jq, python ou qualquer outra dependência externa;
#   * escapador JSON próprio;
#   * ids de requisição únicos;
#   * funciona fora do runtime (fallback de terminal) quando RT_IPC não existe.
#
# Este arquivo é *sourced* pelo comando do §7.1; não deve ser executado.

# ---------------------------------------------------------------------------
# Estado interno
# ---------------------------------------------------------------------------

_RT_SEQ=0
_RT_FD=0                 # 1 quando o transporte IPC está ativo
declare -A _RT_ASSOC=()

rt__loaded() { [ -n "${RT_HELPER_VERSION:-}" ]; }

rt__ipc_open() {
    [ "$_RT_FD" = 1 ] && return 0
    if [ -n "${RT_IPC:-}" ] && [ -p "${RT_IPC}/out" ] && [ -p "${RT_IPC}/in" ]; then
        # §8.1 — o runtime abriu os dois FIFOs com O_RDWR, então não há bloqueio
        # nem EOF aqui. O helper apenas conecta os descritores.
        exec 3>"${RT_IPC}/out" 4<"${RT_IPC}/in" || return 1
        _RT_FD=1
        return 0
    fi
    return 1
}

# Abre o transporte se possível; qualquer script roda mesmo sem runtime.
rt__ipc_open || true

# ---------------------------------------------------------------------------
# Escapadores
# ---------------------------------------------------------------------------

# §8.4 — escapa \, ", \n, \r, \t e remove controles restantes.
rt__escape() {
    local s=${1-}
    s=${s//\\/\\\\}
    s=${s//\"/\\\"}
    s=${s//$'\n'/\\n}
    s=${s//$'\r'/\\r}
    s=${s//$'\t'/\\t}
    s=${s//[[:cntrl:]]/}
    printf '%s' "$s"
}

# §8.3 — desfaz o escape do runtime com printf '%b'.
rt__unescape() {
    printf '%b' "${1-}"
}

rt__json_array() {
    local out="" first=1 item
    for item in "$@"; do
        if [ "$first" -eq 1 ]; then first=0; else out+=","; fi
        out+="\"$(rt__escape "$item")\""
    done
    printf '[%s]' "$out"
}

rt__bool() {
    case "${1-}" in
        1 | true | on | yes | y | sim | Y | True | TRUE) printf 'true' ;;
        *) printf 'false' ;;
    esac
}

# §8.1 — mensagem deve ter menos de 4096 bytes; truncamos com folga.
rt__truncate() {
    local s=${1-}
    if [ ${#s} -gt 1000 ]; then
        s="${s:0:1000}"
    fi
    rt__escape "$s"
}

rt__id() {
    # §8.4 — ids únicos: $$-$RANDOM-contador
    _RT_SEQ=$(( _RT_SEQ + 1 ))
    printf '%s-%s-%s\n' "$$" "$RANDOM" "$_RT_SEQ"
}

# ---------------------------------------------------------------------------
# Transporte
# ---------------------------------------------------------------------------

rt__send() {  # $1 = linha JSON já montada
    [ "$_RT_FD" = 1 ] || return 1
    printf '%s\n' "$1" >&3
}

# Lê a resposta do runtime; devolve "<status>\t<valor>" já desserializado.
rt__reply() {  # $1 = id da requisição
    local id=$1 line
    [ "$_RT_FD" = 1 ] || return 1
    while IFS= read -r line <&4; do
        case $line in
            "$id"$'\t'*)
                printf '%s' "${line#*$'\t'}"
                return 0
                ;;
        esac
    done
    return 1
}

rt__abort() {  # §8.4 — cancelamento encerra o step com 130
    printf '%s\n' "execução cancelada pelo usuário" >&2
    exit 130
}

# Fallback de terminal: mostra a pergunta no stderr (stdout fica limpo).
rt__ask_terminal() {  # $1 = pergunta, $2 = valor padrão, $3 = "secret" → imprime o valor
    local prompt=${1-} fallback=${2-} secret=${3-} answer
    if [ -t 2 ]; then
        printf '%s' "$prompt" >&2
    fi
    if [ "$secret" = secret ]; then
        if IFS= read -rs answer; then
            [ -n "$answer" ] || answer=$fallback
        else
            printf '\n' >&2
            answer=$fallback
        fi
    elif IFS= read -r answer; then
        [ -n "$answer" ] || answer=$fallback
    else
        # stdin indisponível (ex.: runtime sem IPC): usa o padrão
        printf '\n' >&2
        answer=$fallback
    fi
    printf '%s' "$answer"
}

# ---------------------------------------------------------------------------
# Log e notificação
# ---------------------------------------------------------------------------

rt_log()   { _rt_log_line info  "$@"; }
rt_warn()  { _rt_log_line warn  "$@"; }
rt_error() { _rt_log_line error "$@"; }

_rt_log_line() {
    local level=$1; shift
    local text
    text=$(rt__truncate "$*")
    if rt__send "{\"t\":\"log\",\"level\":\"${level}\",\"text\":\"${text}\"}"; then
        return 0
    fi
    case $level in
        error) printf '%s\n' "$*" >&2 ;;
        warn) printf '%s\n' "$*" >&2 ;;
        *) printf '%s\n' "$*" ;;
    esac
}

rt_notify() {
    local text
    text=$(rt__truncate "$*")
    if rt__send "{\"t\":\"notify\",\"text\":\"${text}\"}"; then
        return 0
    fi
    printf '%s\n' "$*"
}

# ---------------------------------------------------------------------------
# Progresso
# ---------------------------------------------------------------------------

# rt_progress <0-100|-> ["texto"]   (§8.4)
rt_progress() {
    local value=${1-} text=${2-} json_value
    if [ "$value" = "-" ] || [ -z "$value" ]; then
        json_value="null"
    elif [[ $value =~ ^[0-9]+$ ]]; then
        # §8.2 — value é fração 0.0–1.0
        json_value=$(printf '%d.%d' $(( value / 100 )) $(( (value % 100) * 10 )))
    else
        rt_warn "rt_progress: valor inválido: $value"
        return 0
    fi
    if rt__send "{\"t\":\"progress\",\"value\":${json_value},\"text\":\"$(rt__truncate "$text")\"}"; then
        return 0
    fi
    printf '[progresso %s] %s\n' "$value" "$text"
}

# ---------------------------------------------------------------------------
# Perguntas
# ---------------------------------------------------------------------------

# rt_confirm "pergunta" [y|n]  → 0 (sim) / 1 (não)
rt_confirm() {
    local text=${1-} default=${2-n} id reply status value
    if [ "$_RT_FD" != 1 ]; then
        local hint="[y/N]"
        [ "$default" = "y" ] && hint="[Y/n]"
        local answer
        answer=$(rt__ask_terminal "${text} ${hint} " "$default")
        case ${answer,,} in
            y | yes | s | sim | 1 | true) return 0 ;;
            *) return 1 ;;
        esac
    fi
    id=$(rt__id)
    rt__send "{\"t\":\"confirm\",\"id\":\"${id}\",\"text\":\"$(rt__truncate "$text")\",\"default\":$(rt__bool "$default")}" || return 1
    reply=$(rt__reply "$id") || rt__abort
    status=${reply%%$'\t'*}
    value=${reply#*$'\t'}
    if [ "$status" = "cancel" ]; then
        rt__abort
    fi
    case $(rt__unescape "$value") in
        y | yes | s | sim | 1 | true) return 0 ;;
        *) return 1 ;;
    esac
}

# rt_input "rótulo" [padrão] → imprime o valor
rt_input() { _rt_ask input "$@"; }
# rt_secret "rótulo" → imprime o valor; nunca é logado
rt_secret() { _rt_ask secret "$@"; }

_rt_ask() {
    local kind=$1 label=${2-} fallback=${3-} id reply status value secret=false
    # §8.2 — rt_secret é o mesmo "input" com secret=true
    [ "$kind" = secret ] && secret=true
    kind=input
    if [ "$_RT_FD" != 1 ]; then
        if [ "$kind" = secret ]; then
            rt__ask_terminal "${label}: " "$fallback" secret
            return 0
        fi
        rt__ask_terminal "${label}${fallback:+ [$fallback]}: " "$fallback"
        return 0
    fi
    id=$(rt__id)
    rt__send "{\"t\":\"${kind}\",\"id\":\"${id}\",\"label\":\"$(rt__truncate "$label")\",\"default\":\"$(rt__truncate "$fallback")\",\"secret\":${secret}}" || return 1
    reply=$(rt__reply "$id") || rt__abort
    status=${reply%%$'\t'*}
    value=${reply#*$'\t'}
    if [ "$status" = "cancel" ]; then
        rt__abort
    fi
    rt__unescape "$value"
}

# rt_choice "rótulo" a b c → imprime a escolha
rt_choice() { _rt_pick choice false "$@"; }
# rt_multi "rótulo" a b c → imprime as escolhas, uma por linha
# (§8.2: multi é flag de "choice", não um t próprio — mandar
# t="multi" faz o runtime ignorar a mensagem e responder cancel)
rt_multi() { _rt_pick choice true "$@"; }

_rt_pick() {
    local kind=$1 multi=$2 label=${3-}
    shift 3
    local -a choices=("$@")
    if [ "$_RT_FD" != 1 ]; then
        local item answer n=0
        for item in "${choices[@]}"; do
            n=$((n + 1))
            printf '  %d) %s\n' "$n" "$item" >&2
        done
        answer=$(rt__ask_terminal "${label}: " "")
        if [ -n "$answer" ]; then
            for item in "${choices[@]}"; do
                [ "$item" = "$answer" ] && printf '%s' "$answer" && return 0
            done
            # aceita número também, como o menu original (1-4)
            if [[ "$answer" =~ ^[0-9]+$ ]] && [ "$answer" -ge 1 ] && [ "$answer" -le "${#choices[@]}" ]; then
                printf '%s' "${choices[$((answer - 1))]}"
                return 0
            fi
        fi
        [ ${#choices[@]} -gt 0 ] && printf '%s' "${choices[0]}"
        return 0
    fi
    local id reply status value
    id=$(rt__id)
    rt__send "{\"t\":\"${kind}\",\"id\":\"${id}\",\"label\":\"$(rt__truncate "$label")\",\"choices\":$(rt__json_array "${choices[@]}"),\"multi\":${multi}}" || return 1
    reply=$(rt__reply "$id") || rt__abort
    status=${reply%%$'\t'*}
    value=${reply#*$'\t'}
    if [ "$status" = "cancel" ]; then
        rt__abort
    fi
    rt__unescape "$value"
}

# Aguarda a resposta de uma requisição já enviada: aborta em cancel (§7.4),
# imprime o valor desserializado. Só os helpers novos usam; os antigos
# mantêm o bloco inline original.
_rt_request() {  # $1 = id da requisição
    local id=$1 reply status value
    reply=$(rt__reply "$id") || rt__abort
    status=${reply%%$'\t'*}
    value=${reply#*$'\t'}
    if [ "$status" = "cancel" ]; then
        rt__abort
    fi
    rt__unescape "$value"
}

# rt_number "rótulo" [padrão] [min] [max] → imprime o número
rt_number() {
    local label=${1-} fallback=${2-} min=${3-} max=${4-} id bounds="" answer ok
    if [ "$_RT_FD" != 1 ]; then
        if [ -n "$min" ] || [ -n "$max" ]; then bounds=" (${min:-…}–${max:-…})"; fi
        while :; do
            answer=$(rt__ask_terminal "${label}${fallback:+ [$fallback]}${bounds}: " "$fallback")
            [ -z "$answer" ] && { printf '%s' "$fallback"; return 0; }
            [[ "$answer" =~ ^-?[0-9]+(\.[0-9]+)?$ ]] || { printf 'digite um número\n' >&2; continue; }
            # faixa só com inteiros: bash puro não compara decimal sem externo
            ok=1
            if [[ "$min" =~ ^-?[0-9]+$ && "$answer" =~ ^-?[0-9]+$ ]] && [ "$answer" -lt "$min" ]; then
                printf 'mínimo: %s\n' "$min" >&2; ok=0
            fi
            if [[ "$max" =~ ^-?[0-9]+$ && "$answer" =~ ^-?[0-9]+$ ]] && [ "$answer" -gt "$max" ]; then
                printf 'máximo: %s\n' "$max" >&2; ok=0
            fi
            [ "$ok" -eq 1 ] && { printf '%s' "$answer"; return 0; }
        done
    fi
    id=$(rt__id)
    rt__send "{\"t\":\"number\",\"id\":\"${id}\",\"label\":\"$(rt__truncate "$label")\",\"default\":\"$(rt__truncate "$fallback")\",\"min\":\"$(rt__escape "$min")\",\"max\":\"$(rt__escape "$max")\"}" || return 1
    _rt_request "$id"
}

# rt_date "rótulo" [padrão-AAAA-MM-DD] → imprime em ISO (kdialog --calendar)
rt_date() {
    local label=${1-} fallback=${2-} id answer has_dated=false
    if [ "$_RT_FD" != 1 ]; then
        date -d "2000-01-01" "+%F" >/dev/null 2>&1 && has_dated=true
        while :; do
            answer=$(rt__ask_terminal "${label}${fallback:+ [$fallback]} (AAAA-MM-DD): " "$fallback")
            [ -z "$answer" ] && { printf '%s' "$fallback"; return 0; }
            if [[ "$answer" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] \
                && { [ "$has_dated" = false ] || date -d "$answer" "+%F" >/dev/null 2>&1; }; then
                printf '%s' "$answer"
                return 0
            fi
            printf 'data inválida (use AAAA-MM-DD)\n' >&2
        done
    fi
    id=$(rt__id)
    rt__send "{\"t\":\"date\",\"id\":\"${id}\",\"label\":\"$(rt__truncate "$label")\",\"default\":\"$(rt__truncate "$fallback")\"}" || return 1
    _rt_request "$id"
}

# rt_time "rótulo" [padrão-HH:MM] → imprime HH:MM (24h)
rt_time() {
    local label=${1-} fallback=${2-} id answer
    if [ "$_RT_FD" != 1 ]; then
        while :; do
            answer=$(rt__ask_terminal "${label}${fallback:+ [$fallback]} (HH:MM): " "$fallback")
            [ -z "$answer" ] && { printf '%s' "$fallback"; return 0; }
            if [[ "$answer" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
                printf '%s' "$answer"
                return 0
            fi
            printf 'hora inválida (use HH:MM)\n' >&2
        done
    fi
    id=$(rt__id)
    rt__send "{\"t\":\"time\",\"id\":\"${id}\",\"label\":\"$(rt__truncate "$label")\",\"default\":\"$(rt__truncate "$fallback")\"}" || return 1
    _rt_request "$id"
}

# rt_file "rótulo" [padrão] [filtro...] → imprime o caminho do arquivo
rt_file() {
    local label=${1-} fallback=${2-} id answer
    shift 2 || shift "$#"
    local -a filters=("$@")
    if [ "$_RT_FD" != 1 ]; then
        answer=$(rt__ask_terminal "${label}${fallback:+ [$fallback]}: " "$fallback")
        printf '%s' "$answer"
        return 0
    fi
    id=$(rt__id)
    rt__send "{\"t\":\"file\",\"id\":\"${id}\",\"label\":\"$(rt__truncate "$label")\",\"default\":\"$(rt__truncate "$fallback")\",\"choices\":$(rt__json_array "${filters[@]}")}" || return 1
    _rt_request "$id"
}

# rt_text "rótulo" [padrão] → texto multilinha; termina com linha só com ponto
rt_text() {
    local label=${1-} fallback=${2-} id line lines=""
    if [ "$_RT_FD" != 1 ]; then
        printf '%s (termine com uma linha só com ponto)\n' "$label" >&2
        while IFS= read -r line; do
            [ "$line" = "." ] && break
            lines+="${line}"$'\n'
        done
        lines=${lines%$'\n'}
        [ -z "$lines" ] && printf '%s' "$fallback" || printf '%s' "$lines"
        return 0
    fi
    id=$(rt__id)
    rt__send "{\"t\":\"text\",\"id\":\"${id}\",\"label\":\"$(rt__truncate "$label")\",\"default\":\"$(rt__truncate "$fallback")\"}" || return 1
    _rt_request "$id"
}

# rt_textbox "título" "texto" → mostra texto longo só-leitura; Enter fecha
rt_textbox() {
    local title=${1-} content=${2-} id
    if [ "$_RT_FD" != 1 ]; then
        printf '%s\n' "$content" >&2
        rt__ask_terminal "(Enter para continuar) " "" >/dev/null
        return 0
    fi
    # o conteúdo vai inline (cap de 200KB com nota); fechar = ok, sem valor
    if [ ${#content} -gt 200000 ]; then
        content="${content:0:200000}…[truncado]"
    fi
    id=$(rt__id)
    rt__send "{\"t\":\"textbox\",\"id\":\"${id}\",\"text\":\"$(rt__escape "$content")\",\"label\":\"$(rt__truncate "$title")\"}" || return 1
    _rt_request "$id" >/dev/null
}

# rt_progresswin_start max "rótulo" → abre a janela de progresso (kdialog --progressbar)
rt_progresswin_start() {
    local max=${1-} label=${2-} id
    if [ "$_RT_FD" != 1 ]; then
        printf '↳ %s (0/%s)\n' "$label" "$max" >&2
        return 0
    fi
    id=$(rt__id)
    rt__send "{\"t\":\"progresswin\",\"id\":\"${id}\",\"op\":\"start\",\"value\":0,\"max\":\"$(rt__escape "$max")\",\"text\":\"$(rt__truncate "$label")\"}" || return 1
    printf '%s' "$id"
}

# rt_progresswin_update id n ["rótulo"] → atualiza a janela (id do _start)
rt_progresswin_update() {
    local id=${1-} value=${2-} label=${3-}
    if [ "$_RT_FD" != 1 ]; then
        printf '↳ %s %s\n' "$value" "$label" >&2
        return 0
    fi
    rt__send "{\"t\":\"progresswin\",\"id\":\"${id}\",\"op\":\"update\",\"value\":\"$(rt__escape "$value")\",\"text\":\"$(rt__truncate "$label")\"}" || return 1
}

# rt_progresswin_done id → fecha a janela
rt_progresswin_done() {
    local id=${1-}
    [ "$_RT_FD" != 1 ] && return 0
    rt__send "{\"t\":\"progresswin\",\"id\":\"${id}\",\"op\":\"done\"}" || return 1
}

# ---------------------------------------------------------------------------
# Variáveis e falha
# ---------------------------------------------------------------------------

# rt_set chave valor → RT_VAR_<CHAVE> disponível nos steps seguintes (§7.2)
rt_set() {
    local key=${1-} value=${2-}
    if [ -z "$key" ]; then
        rt_error "rt_set: chave obrigatória"
        return 1
    fi
    _RT_ASSOC["$key"]=$value
    if [[ $key =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
        export "RT_VAR_${key^^}=$value"
    fi
    if rt__send "{\"t\":\"set\",\"key\":\"$(rt__truncate "$key")\",\"value\":\"$(rt__truncate "$value")\"}"; then
        return 0
    fi
    return 0
}

# rt_fail "mensagem" → registra o motivo e sai com 1
rt_fail() {
    local text
    text=$(rt__truncate "$*")
    rt__send "{\"t\":\"fail\",\"text\":\"${text}\"}" || printf '%s\n' "$*" >&2
    exit 1
}

# rt_get chave → valor definido por rt_set (ou variável RT_VAR_<CHAVE> do §7.2)
rt_get() {
    local key=${1-} upper ref
    upper=${key^^}
    ref="RT_VAR_${upper}"
    # +x e não -n: chave definida com valor vazio é válida (ex.: FRM
    # desligado); só chave inexistente dá 1
    if [ -n "${!ref+x}" ]; then
        printf '%s' "${!ref}"
        return 0
    fi
    if [ -n "${_RT_ASSOC[$key]+x}" ]; then
        printf '%s' "${_RT_ASSOC[$key]}"
        return 0
    fi
    return 1
}

RT_HELPER_VERSION=1
export RT_HELPER_VERSION
