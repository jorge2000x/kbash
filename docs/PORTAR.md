# Portar um script bash para o BashRT

Guia prático: pegue um script bash que já funciona no terminal e transforme-o
em um script anotado que o `rt` executa com interface gráfica. A referência
completa do formato está no `SPEC.md`; aqui está o caminho para chegar lá.

Um script anotado continua sendo bash válido. Você pode rodá-lo no terminal
com `bash script.sh`, e as anotações `#@...` são só comentários para o bash.

---

## 1. Visão geral

Um script comum faz tudo de uma vez, de cima para baixo. No BashRT o runtime
é quem controla a execução: ele escolhe os **steps** (funções), pergunta as
**opções** antes de começar e mostra o progresso. Então a conversão tem três
movimentos:

1. **Quebrar** o fluxo em funções (cada uma vira um step).
2. **Trocar** as perguntas do terminal (`read`, `select`, `echo`) pelos helpers `rt_*`.
3. **Anotar** o cabeçalho, as opções e os steps com `#@`.

---

## 2. Regra de ouro: só definições no topo

Cada step roda em um processo novo que faz `source` do script **inteiro** e
depois chama a função (SPEC §4.5). Então código solto no topo do arquivo roda
uma vez por step.

Errado:

```bash
#!/usr/bin/env bash
mkdir -p "$HOME/projeto"          # roda em todo step!
instalar_tudo
```

Certo:

```bash
#!/usr/bin/env bash
instalar_tudo() { mkdir -p "$HOME/projeto"; ... }
```

Se o script também precisa rodar sozinho no terminal, proteja a chamada final:

```bash
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    instalar_tudo "$@"
fi
```

Quando o runtime faz `source`, `BASH_SOURCE[0]` é o arquivo e `$0` é `bash`:
a chamada não roda. Quando você executa `bash script.sh`, roda.

---

## 3. O cabeçalho

Antes de tudo, o cabeçalho (SPEC §4.2):

```bash
#!/usr/bin/env bash
#@runtime 1
#@name Instalar ambiente de desenvolvimento
#@description Instala ferramentas básicas e configura o git.
#@version 1.0.0
#@requires git,curl
```

- `#@runtime 1` e `#@name` são obrigatórios.
- `#@requires` lista comandos que precisam existir no `PATH`. Se um faltar, o
  runtime avisa antes de começar, sem rodar nada.

---

## 4. Parâmetros viram opções

Se o script recebe argumentos (`$1`, `--nome=...`) ou lê variáveis de ambiente
de configuração, isso vira **opção**. O runtime pergunta na tela e exporta cada
valor como `OPT_<ID>` para todos os steps.

Antes:

```bash
NOME="${1:?uso: script.sh NOME}"
EDITOR_PADRAO="${EDITOR_PADRAO:-nano}"
```

Depois:

```bash
#@option nome type=string label="Seu nome" required=true
#@option editor type=choice label="Editor" choices="vim,nano" default=nano
```

Dentro das funções, use `"$OPT_NOME"` e `"$OPT_EDITOR"`.

Tipos disponíveis: `string`, `password`, `bool`, `choice`, `multi`, `path`,
`file`, `number`, `slider`, `date`, `time`, `text` (multilinha), e os dois que só
exibem: `paragraph` (um texto na tela) e `link` (um botão que abre um endereço
http/https). Veja a tabela completa no SPEC §4.3.

Dica: para mostrar instruções antes das opções, use um `paragraph`, e não um
`help=` longo.

---

## 5. Cada etapa vira um step

Um bloco que o usuário pode marcar ou desmarcar vira uma função anotada com
`#@step`. As anotações ficam em linhas seguidas, logo acima da função:

```bash
#@step atualizar_indice
#@title Atualizar índice de pacotes
#@desc Roda apt-get update.
#@root true
atualizar_indice() {
    apt-get update
}

#@step instalar_ferramentas
#@title Instalar ferramentas
#@group Ferramentas
#@depends atualizar_indice
instalar_ferramentas() {
    apt-get install -y git curl
}
```

- `#@depends` faz o runtime marcar a dependência automaticamente.
- `#@default off` deixa o step desmarcado por padrão.
- `#@required` torna o step obrigatório (sempre marcado).
- `#@on_error continue` segue para o próximo step mesmo se este falhar.
- `#@timeout 900` encerra o step após 900 s.

O nome do step (`#@step nome`) tem que ser igual ao nome da função, ou use
`#@step id` seguido de `function=nome`.

Os steps só são executados na ordem em que aparecem no arquivo, respeitando as
dependências.

---

## 6. Troque o terminal pelos helpers `rt_*`

Esta é a parte que mais muda. Os helpers abrem diálogos na GUI e, no terminal,
caem no comportamento normal (SPEC §8.4).

| No terminal | No BashRT |
|---|---|
| `read -p "Nome: " nome` | `nome=$(rt_input "Nome" "$OPT_NOME")` |
| `read -s -p "Senha: " senha` | `senha=$(rt_secret "Senha")` (nunca vai para o log) |
| `read -p "Continuar? (s/n) " r` | `if rt_confirm "Continuar?" y; then ...; fi` |
| `select e in vim nano; do ...` | `editor=$(rt_choice "Editor" vim nano)` |
| escolher vários itens | `itens=$(rt_multi "Plugins" lua python git)` (um por linha) |
| número validado | `n=$(rt_number "Tentativas" 3 1 10)` |
| data / hora | `d=$(rt_date "Prazo" 2026-12-31)` / `h=$(rt_time "Hora" 08:30)` |
| escolher arquivo | `f=$(rt_file "Foto" "" "*.png" "*.jpg")` |
| texto longo | `t=$(rt_text "Observações")` |
| mostrar um aviso longo | `rt_textbox "Atenção" "$texto"` |
| `echo "..."` | segue funcionando (vai para o log); `rt_log` tem o mesmo efeito |
| `echo "..." >&2` | `rt_warn "..."` ou `rt_error "..."` (nível no log) |
| `echo "concluído"` avisando o usuário | `rt_notify "Concluído"` (toast na tela) |
| `exit 1` com mensagem | `rt_fail "mensagem"` (registra o motivo e sai com 1) |
| "rodando 3 de 10…" | `rt_progress 30 "passo 3 de 10"` |
| progresso sem total conhecido | `rt_progress - "trabalhando…"` |
| janela de progresso dirigida pelo script | `win=$(rt_progresswin_start 10 "Copiando")`, depois `rt_progresswin_update "$win" "$i"` e `rt_progresswin_done "$win"` |
| guardar um valor para outro step | `rt_set chave valor` e, no step seguinte, `rt_get chave` |

Pontos de atenção:

- **Cancelar encerra o step.** Quando o usuário cancela um `rt_confirm` ou
  qualquer outro prompt, o helper encerra o step com código 130. Não tente
  "engolir" esse cancelamento com `|| true`.
- **`rt_input` e similares imprimem o valor.** Por isso se usa `$(...)`.
- **A ordem das perguntas importa.** Cada prompt aparece na tela quando o step
  chega nele. Pergunte no step em que o dado é usado, e não no topo do script.

---

## 7. Remova o que não cabe na GUI

Alguns hábitos do terminal não funcionam dentro do runtime:

- **Entrada padrão (`stdin`) é `/dev/null`.** Um `read` solto não espera o
  usuário: falha. Troque por `rt_input` ou por uma opção.
- **Programas interativos em tela cheia** (`vim`, `less`, `htop`, `dialog`,
  `whiptail`, `ncurses`) não têm terminal. Substitua pelos helpers ou faça a
  ação sem interação (flags como `-y`, `--no-pager`, `DEBIAN_FRONTEND=noninteractive`).
- **Cores ANSI** são removidas do log na v1 (SPEC §15). Escreva texto puro.
- **`sudo` dentro do script não funciona**: não há TTY para pedir a senha. A
  elevação ainda está desligada (SPEC §9.2). Por enquanto, rode a parte que
  precisa de root como usuário comum, ou documente o `sudo` como pré-requisito.
  Marque o step com `#@root true` para que a intenção fique registrada.
- **Processos em segundo plano (`&`)** são encerrados junto com o step ao
  cancelar, porque o runtime mata o grupo de processos.
- **`kdialog`, `zenity` e afins** chamados diretamente não devem ser usados:
  os helpers `rt_*` já são o diálogo, com a aparência do runtime.

---

## 8. Exemplo completo: antes e depois

Antes (`instalar.sh`, um script comum):

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Instalador do ambiente"
read -p "Seu nome para o git: " nome
select editor in vim nano; do break; done

apt-get update
apt-get install -y git curl
git config --global user.name "$nome"
git config --global core.editor "$editor"
echo "Pronto."
```

Depois (`instalar.sh`, anotado):

```bash
#!/usr/bin/env bash
#@runtime 1
#@name Configurar ambiente
#@description Instala git e curl e configura o git.
#@version 1.0.0
#@requires apt-get,git

#@option intro type=paragraph label="Este instalador usa apt e altera a configuração global do git."
#@option nome type=string label="Seu nome para o git" required=true
#@option editor type=choice label="Editor padrão" choices="vim,nano" default=nano

#@step atualizar_indice
#@title Atualizar índice de pacotes
#@root true
atualizar_indice() {
    rt_progress - "apt-get update"
    apt-get update
}

#@step instalar_ferramentas
#@title Instalar git e curl
#@root true
#@depends atualizar_indice
instalar_ferramentas() {
    apt-get install -y git curl
}

#@step configurar_git
#@title Configurar o git
#@depends instalar_ferramentas
configurar_git() {
    git config --global user.name "$OPT_NOME"
    git config --global core.editor "$OPT_EDITOR"
    rt_notify "Git configurado"
}

```

O que mudou:
- `set -euo pipefail` saiu: o runtime já aplica `errexit` e `pipefail` a cada
  step (`#@strict`, padrão `true`).
- `read` e `select` viraram opções na tela de opções.
- O `echo "Pronto."` virou `rt_notify`.
- O trabalho ficou em três steps, e o usuário escolhe o que rodar.
- Não há chamada final no topo: o script só define funções, e o runtime escolhe
  quais rodar. Se você quiser que ele rode sozinho no terminal, use a guarda do §2.

Confira com o runtime:

```bash
rt check instalar.sh          # valida anotações, ids e referências
rt plan instalar.sh --opt nome="Ana Silva"
rt run --headless --yes --opt nome="Ana Silva" instalar.sh   # roda sem GUI
```

---

## 9. Checklist antes de distribuir

- [ ] `rt check` passa sem erros; os warnings foram lidos e aceitos.
- [ ] O topo do arquivo só tem definições (sem comandos soltos).
- [ ] Cada `read`, `select`, `echo ... >&2` e `exit` foi trocado pelo helper certo.
- [ ] Todo parâmetro de entrada virou `#@option`, com `required` quando for o caso.
- [ ] Os `#@step` estão logo acima das funções, com o nome igual ao da função.
- [ ] Dependências entre steps estão em `#@depends`.
- [ ] Nenhum `sudo` dentro dos steps; passos de root estão marcados com `#@root true`.
- [ ] Senhas usam `rt_secret` ou `type=password`.
- [ ] `rt run --headless --yes` com os valores de exemplo termina com código 0.
- [ ] A GUI foi aberta, e o fluxo foi testado de ponta a ponta, incluindo cancelar.

Um script completo com todos os tipos de opção e de prompt está em
`examples/all-options.sh`. Use-o como referência de sintaxe.
