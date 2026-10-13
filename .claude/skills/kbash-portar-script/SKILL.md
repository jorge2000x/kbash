---
name: kbash-portar-script
description: Porta um script bash comum para o formato anotado do kbash (opções, steps e helpers rt_*), validando com kbash check e plan.
---

# Portar script bash para kbash

Transforma um script bash comum em um script anotado que o `kbash` executa com interface gráfica. A referência completa é o `SPEC.md` (§4 formato, §8.4 helpers) e o guia `docs/PORTAR.md`.

## Princípios

1. **A lógica do usuário fica intacta.** Só a interação (`read`, `select`, `echo`, `exit`) muda e as anotações `#@` são acrescentadas.
2. **Um arquivo só**, bash com anotações `#@`. Nunca divida o script em vários arquivos.
3. **Só definições no topo.** Cada step faz `source` do script inteiro, então comandos soltos no topo rodam a cada step.
4. **Pergunte só o que muda o resultado.** Se a dúvida não altera o port (por exemplo, a ordem exata de um passo), decida e diga o que decidiu.

## Passo a passo

### 1. Ler e mapear
Leia o script inteiro e liste:
- parâmetros (`$1`, `--nome=...`, variáveis de ambiente de configuração);
- perguntas interativas (`read`, `select`, `read -s`, `[ -t 0 ]`);
- blocos de trabalho que podem ser marcados ou desmarcados;
- uso de `sudo`, `apt`, `systemctl` (precisam de `#@root true`);
- programas interativos (`vim`, `less`, `dialog`, `whiptail`) e `&` em segundo plano;
- `exit N` com mensagem e `echo` de progresso ou de status.

### 2. Cabeçalho
```bash
#!/usr/bin/env bash
#@runtime 1
#@name Nome exibido
#@description Uma frase.
#@version 1.0.0
#@requires cmd1,cmd2
```
`#@runtime 1` e `#@name` são obrigatórios. `#@requires` lista os comandos externos que o script usa.

### 3. Opções (perguntas e parâmetros)
Cada entrada vira `#@option`. O nome da variável é `OPT_` + id em maiúsculas.

| No script original | Opção |
|---|---|
| `read -p "Nome" v` | `type=string` |
| `read -s` (senha) | `type=password` |
| `select` / lista fixa | `type=choice choices="a,b"` |
| várias escolhas | `type=multi choices="a,b,c"` |
| sim/não | `type=bool` |
| número com faixa | `type=number min= max=` (ou `slider`) |
| caminho de pasta | `type=path` |
| arquivo | `type=file filters="*.png,*.jpg"` |
| data ou hora | `type=date` (AAAA-MM-DD) ou `type=time` (HH:MM) |
| texto longo | `type=text` |
| instruções antes das opções | `type=paragraph label="..."` |
| link de ajuda | `type=link url="https://..."` |

- `default=` recebe o valor que o script usa hoje.
- `required=true` quando o script aborta sem o valor.
- `show_if="outra=valor"` quando a opção só faz sentido em certo caso.

### 4. Steps (blocos de trabalho)
Cada bloco que o usuário pode escolher vira uma função com anotações logo acima:
```bash
#@step instalar_pacotes
#@title Instalar pacotes
#@desc Instala git e curl.
#@group Ferramentas
#@root true
#@depends atualizar_indice
instalar_pacotes() {
    apt-get install -y git curl
}
```
- O id do step tem que ser igual ao nome da função (ou use `function=`).
- `#@depends` só para dependência real entre steps.
- `#@default off` para passo opcional; `#@required` para passo obrigatório.
- `#@on_error continue` só se o script original continuava depois de uma falha.
- `#@timeout N` quando o passo pode travar.

### 5. Trocar a interação pelos helpers `rt_*`

| Terminal | kbash |
|---|---|
| `read -p "Nome: " n` | `n=$(rt_input "Nome" "$OPT_NOME")` (ou use a opção) |
| `read -s` | `s=$(rt_secret "Senha")` |
| `read -p "Continuar? (s/n)" r` | `if rt_confirm "Continuar?" y; then ...; fi` |
| `select e in a b` | `e=$(rt_choice "Editor" a b)` |
| número validado | `n=$(rt_number "Tentativas" 3 1 10)` |
| data / hora | `d=$(rt_date "Prazo" 2026-12-31)` / `h=$(rt_time "Hora" 08:30)` |
| arquivo | `f=$(rt_file "Foto" "" "*.png")` |
| texto longo | `t=$(rt_text "Observações")` |
| `echo "..."` de progresso | `rt_progress 50 "..."` ou `rt_log "..."` |
| `echo "..." >&2` | `rt_warn "..."` ou `rt_error "..."` |
| `echo "concluído"` para o usuário | `rt_notify "Concluído"` |
| `exit 1` com mensagem | `rt_fail "mensagem"` |
| guardar valor para outro step | `rt_set chave valor` e `rt_get chave` no step seguinte |

`rt_confirm` e os outros prompts, ao serem cancelados, encerram o step com código 130. **Não use `|| true` para engolir isso.**

### 6. Remover o que não funciona na GUI
- Apague `set -euo pipefail`: o runtime já aplica `errexit` e `pipefail` (`#@strict`, padrão `true`).
- `stdin` é `/dev/null`: nenhum `read` solto.
- `vim`, `less`, `htop`, `dialog`, `whiptail`: substitua pelo helper ou faça a ação sem interação (`-y`, `--no-pager`, `DEBIAN_FRONTEND=noninteractive`).
- `sudo` não funciona ainda (não há como pedir senha). Marque o passo com `#@root true`, avise o usuário e documente o pré-requisito.
- Cores ANSI saem do log: use texto puro.
- Processos em `&` são encerrados junto com o step quando ele é cancelado.
- Não chame `kdialog`, `zenity` ou `whiptail` diretamente.

### 7. Código de nível superior
O topo do arquivo só deve ter definições. Se o script também precisa rodar sozinho no terminal, proteja a chamada final:
```bash
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    main "$@"
fi
```

### 8. Validar (obrigatório antes de entregar)
```bash
bash -n arquivo.kbash                                   # sintaxe bash
kbash check arquivo.kbash                               # anotações, ids, referências (exit 0)
kbash plan arquivo.kbash --opt nome="Ana"               # o que vai rodar
kbash run --headless --yes --opt nome="Ana" arquivo.kbash   # só se o script for seguro de rodar
```
- Não rode scripts que alteram o sistema (apt, rm, configuração global) sem confirmar com o usuário. Em dúvida, pare em `check` e `plan`.
- Erros de validação saem com `arquivo:linha`. Corrija cada um.
- Warnings (diretiva desconhecida, atributo que não se aplica ao tipo) devem ser lidos e resolvidos ou justificados.

### 9. Entregar
- O arquivo novo, com extensão `.kbash` (ou `.sh`, também aceito). Mantenha o original intacto.
- Um resumo curto: o que virou opção, o que virou step, quais helpers substituíram quais construções.
- O que **não** foi portado e por quê (por exemplo, sudo, programa interativo).

## Erros de validação comuns
- `id` duplicado em steps ou opções.
- `#@depends` apontando para step inexistente ou formando ciclo.
- `type=choice` sem `choices`; `default` fora de `choices`.
- `type=paragraph` sem `label`; `type=link` sem `url` http/https.
- `show_if` com referência inexistente ou ciclo.
- Anotações do step fora de linhas consecutivas acima da função.

## Não faça
- Não reescreva a lógica do usuário para "ficar melhor"; só adapte a interação.
- Não renomeie os helpers `rt_*`, as variáveis `RT_*` nem a diretiva `#@runtime`: são a API dos scripts.
- Não crie arquivos auxiliares, configurações ou um segundo script.
