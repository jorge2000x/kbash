# SPEC — kbash

> Runtime com GUI (Qt/QML, Kirigami) que executa scripts bash anotados.
> O script bash é apenas **código-fonte**; quem controla a execução, a interface e a interação com o usuário é o runtime.

Este documento é a fonte da verdade do projeto. Toda tarefa de implementação deve referenciar uma seção daqui. Se o código e o spec divergirem, atualize o spec primeiro.

Os números de seção são estáveis: o código os cita (ex.: `§4.3`, `§8.4`). Não renumerar.

---

## 1. Objetivos e não-objetivos

### Objetivos
- Permitir que um desenvolvedor escreva um script bash comum, com anotações leves, e distribuí-lo como um "instalador" com GUI bonita.
- O usuário final abre o programa, vê o que o script faz, escolhe opções e etapas, executa e acompanha o progresso e o log.
- O runtime executa cada etapa em um subprocesso `bash`, com controle total: ordem, dependências, cancelamento, entrada do usuário, progresso, logs e (futuramente) elevação de privilégio.
- O script continua sendo bash válido e executável sozinho (as anotações são comentários).

### Não-objetivos (v1)
- Não é um interpretador de bash (quem executa é o `bash` do sistema).
- Não suporta Windows/macOS (somente Linux).
- Não suporta terminal interativo completo (PTY/ncurses). Scripts devem usar os helpers `rt_*` para interação.
- Não tem editor de scripts nem loja/repositório de scripts.

---

## 2. Terminologia

| Termo | Significado |
|---|---|
| **Runtime** | O programa (Python + PySide6 + QML) que carrega e executa scripts. |
| **Script** | Arquivo `.sh` anotado. |
| **Step (etapa)** | Função bash anotada que o usuário pode selecionar e executar. |
| **Option (opção)** | Item da tela de opções. A maioria tem valor (vira variável `OPT_*`); `paragraph` e `link` só exibem (§4.3). |
| **Payload** | Script (e assets) empacotados junto com o runtime. |
| **Bundle** | O AppImage distribuído: runtime + payload (§11.1). |
| **IPC** | Canal de comunicação entre o script (helpers `rt_*`) e o runtime (§8). |

---

## 3. Arquitetura

```
┌───────────────────────────── Runtime ─────────────────────────────┐
│  GUI (QML/Kirigami)  ←→  Bridge (Qt)  ←→  Core (Python puro)      │
│                                             ├─ parser             │
│                                             ├─ planner            │
│                                             ├─ executor ──► bash  │
│                                             └─ ipc (FIFOs) ◄──────┘
└───────────────────────────────────────────────────────────────────┘
```

Regras de arquitetura (invioláveis):
1. **`core/` nunca importa Qt.** É Python puro, testável com pytest sem display.
2. O `core` emite **eventos** (dataclasses) para um callback; a GUI converte eventos em sinais Qt via `gui/bridge.py`.
3. A GUI nunca chama `subprocess` nem lê o script diretamente; só fala com o Bridge.
4. Toda decisão de lógica (ordem, dependências, estado, erros) fica no `core`.
5. A GUI usa **componentes-fachada** (`AppWindow`, `Page`, `Card`, `Dialog`…)
   implementados em Kirigami (ver §10.1). Só existe uma implementação.

### Estrutura de pastas (real)

```
kbash/                       # pacote do runtime (o repositório pode ter mais pastas ao redor)
├── SPEC.md                      # este documento
├── AGENTS.md                    # regras para a IA (ver §14)
├── pyproject.toml
├── src/kbash/
│   ├── cli.py, main.py, __main__.py, _startup.py
│   ├── core/                    # Python puro, sem Qt (§3, regra 1)
│   │   ├── model.py             # dataclasses: Option, Step, Script, RunPlan
│   │   ├── parser.py            # extrai anotações (estático, não executa nada)
│   │   ├── planner.py           # seleção, dependências, valores e validação de opções
│   │   ├── executor.py          # roda steps em subprocessos bash
│   │   ├── ipc.py               # FIFOs + protocolo de mensagens
│   │   ├── events.py            # eventos emitidos pelo executor
│   │   ├── ui.py                # Prompt/Answer e provedores terminal/yes/none
│   │   └── errors.py
│   ├── helpers/rt.sh            # funções rt_* injetadas nos steps (bash puro)
│   └── gui/
│       ├── app.py               # QGuiApplication, probe do Kirigami, estilo, fonte
│       ├── bridge.py            # eventos core → sinais Qt; slots para o QML
│       ├── models.py            # StepListModel, OptionModel, LogModel
│       ├── ui_qt.py             # provedor `qt` (§8.5)
│       └── qml/
│           ├── main.qml
│           ├── pages/           # Welcome, Select, Run, Result (módulo `pages`)
│           └── kirigami/kbash/ # fachadas Kirigami (módulo `kbash`)
├── tests/                       # pytest (test_*.py + fixtures/)
├── examples/                    # all-options.sh (todos os tipos), setup-dev.sh, sober-optimizer.sh
└── docs/                        # BREEZE.md, KIRIGAMI-SPIKE.md, PORTAR.md (guia de porte)
```

O repositório também guarda as ferramentas de empacotamento (`tools/`, ao lado de `kbash/`). Ver §11.1.

---

## 4. Formato do script anotado

### 4.1 Regras gerais
- Anotações são linhas de comentário que começam com `#@` (sem espaço entre `#` e `@`).
- Sintaxe: `#@chave valor` — `valor` é tokenizado com regras de shell (aspas simples/duplas, `\` de escape). Atributos usam `nome=valor`.
- Anotações de **cabeçalho** ficam antes da primeira anotação `#@step`/`#@option`.
- Anotações de **step** ficam em linhas consecutivas imediatamente antes da definição da função.
- O parser é **estático**: nunca executa o script. Usa regex/tokenização.
- Uma função é reconhecida por `^\s*(function\s+)?NOME\s*\(\)\s*\{?` ou `^\s*function\s+NOME`.

### 4.2 Cabeçalho

| Diretiva | Obrigatória | Descrição |
|---|---|---|
| `#@runtime 1` | sim | Versão do formato do spec. |
| `#@name Texto` | sim | Título exibido na janela. |
| `#@id com.exemplo.app` | não | ID reverso (log, config, `.desktop`). Padrão: slug do nome. |
| `#@description Texto` | não | Descrição curta exibida na tela inicial. |
| `#@version 1.2.0` | não | Versão do script. |
| `#@author Nome` | não | Autor. |
| `#@icon nome-ou-arquivo` | não | Nome de ícone do tema ou caminho relativo em `assets/`. |
| `#@requires cmd1,cmd2` | não | Comandos que precisam existir no `PATH`; checados antes de executar. |
| `#@strict true\|false` | não | Se `true` (padrão), steps rodam com `set -o errexit -o pipefail`. |

### 4.3 Opções

```bash
#@option editor type=choice label="Editor" choices="vim,nano,micro" default=nano
#@option name   type=string label="Seu nome" required=true
#@option token  type=password label="Token de acesso"
#@option dir    type=path label="Pasta de destino" default="$HOME/dev"
#@option telemetry type=bool label="Enviar telemetria" default=false
#@option retries type=number label="Tentativas" min=1 max=10 default=3
#@option volume type=slider label="Volume" min=0 max=100 step=5 default=50
#@option avatar type=file label="Foto de perfil" filters="*.png,*.jpg"
#@option notes type=text label="Observações"
#@option deadline type=date label="Prazo" default="2026-12-31"
#@option alarm type=time label="Horário" default="08:30"
#@option intro type=paragraph label="Leia antes de continuar: isto só mostra texto."
#@option docs type=link label="Documentação" url="https://example.org/docs"
```

| Atributo | Descrição |
|---|---|
| `id` | Primeiro argumento posicional (`editor`, `name`…). `[a-z][a-z0-9_]*`. |
| `type` | `bool`, `string`, `password`, `choice`, `multi`, `path`, `number`, `slider`, `file`, `text`, `date`, `time`, `paragraph`, `link`. Padrão `string`. `paragraph` e `link` só exibem (abaixo). |
| `label` | Texto exibido. Padrão: o `id`. Em `paragraph` é o próprio texto (**obrigatório**). Em `link` é o rótulo do botão (padrão: a `url`). |
| `url` | Só `link`: endereço `http://` ou `https://` que o botão abre no navegador padrão. Outro esquema (ou ausência) é erro de parse. |
| `default` | Valor inicial. Aceita `$HOME` e `~` (expandidos pelo runtime). Não se aplica a `paragraph`/`link` (vira aviso). |
| `choices` | Lista separada por vírgula (`choice`/`multi`). |
| `min` / `max` / `step` | Faixa e passo (`number`/`slider`; números, `step` > 0). Padrão do `slider`: `0`/`100`/`1`. |
| `filters` | Globs separados por vírgula (`file`, ex. `"*.png,*.jpg"`). Validados e guardados, mas o portal atual abre sem filtro (§10.1). Em `rt_file`, cada glob é um argumento (§8.4). |
| `pattern` | Regex de validação total (`string`/`password`; subconjunto compatível Python↔JS). |
| `minlen` / `maxlen` | Comprimento mínimo/máximo (`string`/`password`/`text`). |
| `multiple` | `true` permite vários arquivos (`file`); vira lista separada por vírgula. |
| `show_if` | Condição de visibilidade: `"outra=valor[,outra2=valor2]"` (AND). Opção oculta some do formulário, usa o `default` e pula o `required`. Vale também para `paragraph` e `link`. |
| `required` | `true` bloqueia "Executar" enquanto vazio. |
| `help` | Texto de ajuda (tooltip/subtítulo). |

Cada opção **com valor** vira variável de ambiente `OPT_<ID em maiúsculas>` em todos os steps. `bool` vira `1`/`0`; `multi` vira valores separados por vírgula; `number`/`slider` vão como texto numérico; `date` vai em ISO (`AAAA-MM-DD`), `time` em `HH:MM` (24h); `file` expande `~`/`$HOME` como `path` (com `multiple`, vários caminhos separados por vírgula); `text` pode conter quebras de linha. Referência inexistente, auto-referência ou ciclo em `show_if` é erro de validação (§4.6).

**`paragraph` e `link` não têm valor.** Não geram `OPT_*`, não entram no plano, não aceitam `--opt` (erro, §6), não são obrigatórios e não têm `default`. Servem para orientar o usuário: `paragraph` mostra o texto; `link` mostra um botão que abre a `url`. O `link` só abre `http`/`https` (também revalidado no runtime, `Bridge.openLink`).

### 4.4 Steps

```bash
#@step install_deps
#@title Instalar dependências
#@desc Instala git, curl e build-essential via apt.
#@group Preparação
#@default on
#@root true
#@timeout 900
#@depends update_index
install_deps() {
  rt_progress - "Instalando pacotes..."
  apt-get install -y git curl build-essential
}
```

| Diretiva | Descrição |
|---|---|
| `#@step id` | Inicia o bloco. `id` deve ser único e igual ao nome da função (ou use `function=nome`). |
| `#@title` | Título exibido. Padrão: o `id`. |
| `#@desc` | Descrição (uma ou mais linhas `#@desc`, concatenadas). |
| `#@group` | Agrupa steps visualmente. |
| `#@default on\|off` | Marcado por padrão? Padrão `on`. |
| `#@required` | Step obrigatório: sempre selecionado, não pode ser desmarcado. |
| `#@depends id1,id2` | Dependências. Marcar este step marca as dependências automaticamente. |
| `#@root true` | Step exige privilégios de root (ver §9.2; hoje desligado). |
| `#@timeout N` | Timeout em segundos (padrão: sem limite). |
| `#@on_error stop\|continue` | O que fazer se este step falhar. Padrão `stop`. |

### 4.5 Regras sobre código de nível superior
Cada step roda em um processo novo que faz `source` do script inteiro e depois chama a função. Portanto:
- Código de nível superior roda **a cada step**. O ideal é ter só definições (funções, variáveis).
- O runtime exporta `RT_MODE=step` para o script poder proteger código de nível superior.
- `kbash check` emite **warning** (heurístico) quando encontra comandos soltos fora de funções.

### 4.6 Validação (erros de parse, todos com número de linha)
- `id` duplicado (steps ou opções)
- Função do step não encontrada
- `depends` apontando para step inexistente ou ciclo nas dependências
- `type=choice` sem `choices`; `default` fora de `choices`
- `type=paragraph` sem `label`; `type=link` sem `url`, ou com `url` que não seja `http`/`https`
- `show_if` com referência inexistente, auto-referência ou ciclo
- Diretiva desconhecida (**warning**, não erro, para compatibilidade futura)
- Atributo que não se aplica ao tipo (ex.: `default` em `paragraph`): **warning**
- `#@runtime` ausente ou de versão maior que a suportada

### 4.7 Exemplo completo

```bash
#!/usr/bin/env bash
#@runtime 1
#@name Configurar ambiente de desenvolvimento
#@description Instala ferramentas básicas e configura o git.
#@version 1.0.0
#@requires curl

#@option user_name type=string label="Nome para o git" required=true
#@option editor type=choice label="Editor padrão" choices="vim,nano" default=nano

#@step update_index
#@title Atualizar índice de pacotes
#@root true
update_index() { apt-get update; }

#@step install_tools
#@title Instalar ferramentas
#@group Ferramentas
#@root true
#@depends update_index
install_tools() {
  rt_progress 10 "Instalando git e curl"
  apt-get install -y git curl
  rt_progress 100
}

#@step config_git
#@title Configurar git
#@group Ferramentas
#@depends install_tools
config_git() {
  git config --global user.name "$OPT_USER_NAME"
  git config --global core.editor "$OPT_EDITOR"
  rt_confirm "Ativar assinatura de commits?" n && git config --global commit.gpgsign true
  rt_notify "Git configurado"
}
```

Um exemplo que cobre todos os tipos de opção e de prompt está em `examples/all-options.sh`.

---

## 5. Modelo de dados (`core/model.py`)

```python
@dataclass(frozen=True)
class Option:
    id: str; type: str; label: str
    default: str | None = None; choices: tuple[str, ...] = ()
    required: bool = False; help: str = ""
    minimum: str | None = None; maximum: str | None = None; step: str | None = None
    filters: tuple[str, ...] = ()
    pattern: str = ""; minlen: str | None = None; maxlen: str | None = None
    multiple: bool = False
    url: str = ""                     # só type=link
    show_if: tuple[tuple[str, str], ...] = ()
    line: int = 0
    @property
    def carries_value(self) -> bool:  # False para paragraph/link (§4.3)
        ...

@dataclass(frozen=True)
class Step:
    id: str; function: str; title: str; description: str
    group: str | None; default: bool; required: bool
    depends: tuple[str, ...]; root: bool
    timeout: int | None; on_error: str   # "stop" | "continue"
    line: int

@dataclass(frozen=True)
class Script:
    path: Path; sha256: str
    runtime_version: int; name: str; id: str
    description: str; version: str; author: str; icon: str | None
    requires: tuple[str, ...]; strict: bool
    options: tuple[Option, ...]; steps: tuple[Step, ...]

@dataclass
class RunPlan:
    script: Script
    selected: list[str]              # ids finais, em ordem topológica
    options: dict[str, str]          # só opções com valor (§4.3)
```

Estados de um step: `pending → running → success | failed | cancelled | skipped`.

---

## 6. Planner (`core/planner.py`)

- `resolve(script, selected_ids) -> Resolution(ids, auto_added)`: adiciona dependências (transitivas) e steps `required`, ordena topologicamente mantendo a ordem de declaração como desempate. `auto_added` diz à GUI o que entrou "por dependência".
- `dependents(script, step_id)` e `can_uncheck` / `set_checked`: desmarcar um step de que outro selecionado depende é bloqueado na GUI.
- `value_options(script)`: as opções com valor. É a única lista usada para valores, erros e o `RunPlan.options`.
- `option_errors` / `validate_options`: `required` preenchidas, `choice`/`multi` dentro de `choices`, número na faixa, data/hora válidas, `pattern`/`minlen`/`maxlen`. Opção oculta por `show_if` não é validada.
- `build_plan(script, selected, options)`: `--opt` com chave desconhecida ou com chave de `paragraph`/`link` é erro.

---

## 7. Executor (`core/executor.py`)

### 7.1 Como um step é executado
Para cada step do plano, em ordem:

```
bash --noprofile --norc -c '
  set -o pipefail; [ "$RT_STRICT" = 1 ] && set -o errexit
  source "$RT_HELPERS"
  source "$RT_SCRIPT"
  "$RT_STEP_FN"
'
```

- Processo iniciado com `start_new_session=True` (grupo próprio para cancelar).
- `stdin` = `/dev/null` (um `read` solto falha em vez de travar; scripts devem usar `rt_input`).
- `stdout` e `stderr` em pipes separados, lidos por threads, linha a linha, emitindo `LogLine(step_id, stream, text)`.
- Encoding UTF-8 com `errors="replace"`. Sequências ANSI são removidas em v1.
- `cwd` = `$HOME`, salvo se o script fizer `cd`.

### 7.2 Variáveis de ambiente injetadas

| Variável | Valor |
|---|---|
| `RT_SCRIPT` | Caminho do script. |
| `RT_HELPERS` | Caminho de `rt.sh`. |
| `RT_ASSETS` | Diretório de assets do payload (vazio no modo dev sem assets). |
| `RT_IPC` | Diretório dos FIFOs (§8.1). Vazio fora da execução real. |
| `RT_STEP_ID`, `RT_STEP_FN` | Step atual. |
| `RT_STRICT` | `1` ou `0`. |
| `RT_MODE` | Sempre `step`. |
| `RT_WORKDIR` | Diretório temporário da execução, removido ao final (ou o cwd, se não houver). |
| `OPT_<ID>` | Valores das opções **com valor** (§4.3). |
| `RT_VAR_<KEY>` | Variáveis definidas por steps anteriores via `rt_set`. |

### 7.3 Eventos emitidos (`core/events.py`)

`RunStarted`, `StepStarted(step_id)`, `StepFinished(step_id, status, exit_code, duration)`, `LogLine(step_id, stream, text)`, `Progress(step_id, value|None, text)`, `PromptRequest(request_id, kind, ...)`, `Notify(text, level)`, `ProgressWin(op, value, maximum, text)`, `RunFinished(status)`.

Progresso geral = `(steps concluídos + progresso do step atual) / total selecionado`.

### 7.4 Falhas, cancelamento, timeout
- Step retorna ≠ 0 → `failed`. Com `on_error=stop` (padrão), os steps restantes ficam `skipped` e a execução termina como `failed`. Com `continue`, segue para o próximo, **exceto** steps que dependem do que falhou (esses ficam `skipped`).
- **Cancelar**: `SIGTERM` no grupo de processos; após 5 s sem sair, `SIGKILL`. Step vira `cancelled`, restantes `skipped`.
- **Timeout**: mesmo procedimento do cancelamento; step vira `failed` com motivo "timeout".
- Prompts pendentes são respondidos com `cancel` ao cancelar.

### 7.5 Pré-checagens
Antes de rodar: `#@requires` (todos no PATH) e opções obrigatórias visíveis. Falhas geram erro na tela de seleção, sem iniciar nada. A checagem de `pkexec` para steps `root` só entra quando a elevação estiver ligada (§9.2).

---

## 8. Protocolo de interação script ↔ runtime

### 8.1 Transporte
Dois FIFOs num diretório `0700` criado por execução (`$XDG_RUNTIME_DIR/<id>-<pid>/`):
- `out` — script → runtime (mensagens JSON, uma por linha)
- `in` — runtime → script (respostas em formato de linha simples)

O runtime abre os dois com `O_RDWR` (evita bloqueio na abertura). O helper `rt.sh` abre os descritores `3` (out) e `4` (in) no início.

> **Por que FIFOs e não FDs herdados?** Steps com `#@root` rodariam via `pkexec`, que não repassa file descriptors extras. FIFOs por caminho funcionam também com elevação, e também com `QProcess`.

Mensagens em `out` devem ter **< 4096 bytes** (atomicidade de escrita em pipe). O helper trunca textos longos. O log normal continua via `stdout`/`stderr`.

### 8.2 Script → runtime (JSON, uma linha)

```json
{"t":"log","level":"info|warn|error","text":"..."}
{"t":"progress","value":0.4,"text":"Baixando..."}      // value null = indeterminado
{"t":"notify","text":"Concluído"}
{"t":"set","key":"repo_dir","value":"/home/x/dev"}
{"t":"confirm","id":"r1","text":"Continuar?","default":true}
{"t":"input","id":"r2","label":"Nome","default":"","secret":false}
{"t":"choice","id":"r3","label":"Editor","choices":["vim","nano"],"multi":false}
{"t":"number","id":"r4","label":"Tentativas","default":"3","min":"1","max":"10"}
{"t":"date","id":"r5","label":"Prazo","default":"2026-12-31"}
{"t":"time","id":"r6","label":"Hora","default":"08:30"}
{"t":"file","id":"r7","label":"Foto","default":"","choices":["*.png"]}
{"t":"text","id":"r8","label":"Notas","default":""}
{"t":"textbox","id":"r9","label":"Aviso","text":"leia isto"}   // informativo: fechar responde ok vazio
{"t":"progresswin","id":"r10","op":"start|update|done","value":30,"max":100,"text":"Copiando..."}
{"t":"fail","text":"Mensagem de erro"}                  // marca falha com motivo
```

`progresswin` é fire-and-forget (como `notify`): não cria pendência nem espera resposta — o script segue executando e manda `update`s. `start` abre a janela (o `id` que ela recebe identifica as mensagens seguintes), `done` fecha. *Cancelar* na janela aborta a execução inteira (saída 130, §7.4).

### 8.3 Runtime → script (uma linha, campos separados por TAB)

```
<id>\t<status>\t<valor>
```
- `status`: `ok` ou `cancel`.
- `valor`: com `\` → `\\`, quebra de linha → `\n`, TAB → `\t` (o helper desfaz com `printf '%b'`).
- `confirm` responde `yes`/`no`; `multi` devolve itens separados por `\n` (escapado).

### 8.4 Helpers em `rt.sh` (API para autores de scripts)

| Função | Comportamento |
|---|---|
| `rt_log "texto"` / `rt_warn` / `rt_error` | Mensagem estruturada no log. |
| `rt_progress <0-100\|-> ["texto"]` | Progresso do step (`-` = indeterminado). |
| `rt_confirm "pergunta" [y\|n]` | Retorna 0 (sim) ou 1 (não). Cancelamento encerra o step com código 130. |
| `rt_input "rótulo" [padrão]` | Imprime o valor em stdout: `nome=$(rt_input "Nome")`. |
| `rt_secret "rótulo"` | Idem, campo de senha (o valor nunca é logado). |
| `rt_choice "rótulo" a b c` | Imprime a escolha. |
| `rt_multi "rótulo" a b c` | Imprime as escolhas, uma por linha. |
| `rt_number "rótulo" [padrão] [min] [max]` | Imprime o número (validado; vazio só se permitido). |
| `rt_date "rótulo" [padrão-AAAA-MM-DD]` | Calendário/entrada de data; imprime em ISO. |
| `rt_time "rótulo" [padrão-HH:MM]` | Entrada de hora; imprime `HH:MM` (24h). |
| `rt_file "rótulo" [padrão] [filtro...]` | Seletor de arquivo; imprime o caminho. Cada filtro é **um argumento**: `rt_file "Foto" "" "*.png" "*.jpg"`. Os filtros viajam no prompt, mas o portal atual não os aplica (§10.1). |
| `rt_text "rótulo" [padrão]` | Texto multilinha; imprime o conteúdo. |
| `rt_textbox "título" "texto"` | Mostra texto longo só-leitura; fechar responde ok. |
| `rt_progresswin_start max "rótulo"` | Abre a janela de progresso dirigido pelo script. **Imprime o `id`** da janela: `win=$(rt_progresswin_start 5 "Copiando")`. |
| `rt_progresswin_update id n ["rótulo"]` | Atualiza a janela `id` com o valor `n` (e o rótulo, se dado). |
| `rt_progresswin_done id` | Fecha a janela `id`. |
| `rt_set chave valor` | Guarda o valor para os steps seguintes e exporta `RT_VAR_CHAVE`. |
| `rt_get chave` | Imprime o valor guardado por `rt_set` (ou `RT_VAR_CHAVE`); retorna 1 se a chave não existir. |
| `rt_notify "texto"` | Notificação/toast na GUI. |
| `rt_fail "mensagem"` | Registra motivo e sai com código 1. |

Requisitos de implementação do `rt.sh`:
- **Bash puro**, sem `jq`, `python` ou outras dependências. Precisa de um escapador JSON próprio (`\`, `"`, `\n`, `\r`, `\t` e controles como `\u00XX`).
- IDs de requisição únicos: `$$-$RANDOM-$contador`.
- Deve funcionar fora do runtime: sem os descritores de IPC, cai para fallback de terminal (`read -p`, `echo`), permitindo rodar o script isolado.

### 8.5 Provedor de UI para interação (estilo *kdialog*)

O runtime **não** desenha a interface das perguntas: ele entrega um `Prompt` a um
*provedor de UI* escolhido em runtime e recebe um `Answer`. A sintaxe vista pelo
autor do script é a do `kdialog` (§8.4), mas **o diálogo é do próprio runtime** — o
script nunca executa um programa externo para obter a resposta, e nenhum helper
externo é chamado pelo runtime. Trocar de implementação não altera o core, o
script ou o resultado.

```python
@dataclass(frozen=True)
class Prompt:                      # core/ui.py — Python puro, sem Qt
    id: str
    kind: Literal["confirm", "input", "choice", "number", "date", "time", "file", "text", "textbox"]
    text: str = ""; label: str = ""; secret: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()
    multi: bool = False

@dataclass(frozen=True)
class Answer:                      # status: "ok" | "cancel"
    status: str
    value: str | bool | tuple[str, ...] = ""

class Ui(Protocol):
    name: str
    def ask(self, prompt: Prompt) -> Answer: ...
    def notify(self, text: str, level: str = "info") -> None: ...
    def close(self) -> None: ...
```

Provedores da v1:

| `name` | Onde vive | Quando usar |
|---|---|---|
| `qt` | `gui/ui_qt.py` | GUI aberta: o diálogo QML responde. `ask()` bloqueia a thread do IPC, nunca a thread da GUI (§10.4). |
| `terminal` | `core/ui.py` | `--headless` com TTY: perguntas no terminal, espelhando o `kdialog`. |
| `yes` | `core/ui.py` | CI e `--yes`: assume o padrão do `Prompt`, sem perguntar. |
| `none` | `core/ui.py` | Sem interface: cancela os prompts pendentes (§7.4). |

Escolha, em ordem de precedência:

1. `--ui <nome>` na CLI;
2. `$KBASH_UI` no ambiente;
3. `auto` (padrão): `qt` se há GUI, `terminal` se `stdin` for um TTY, `yes` caso
   contrário (com aviso — evita travamento em CI).

Regras:
- O `Answer` é normalizado por `core/ipc.py` para a linha `<id>\t<status>\t<valor>` (§8.3);
  a serialização continua sendo responsabilidade do IPC, não do provedor.
- Valores vindos do QML chegam como `QJSValue` (arrays JS não viram `list`
  sozinhos): `gui/ui_qt.py` converte antes de responder.
- Fechar o diálogo sem responder equivale a `cancel` (`bridge.cancelPrompt`;
  §7.4 encerra o step com 130).
- `secret=True` nunca é registrado em log pelo provedor (§9.1).
- Trocar de provedor não muda o resultado do script: o valor vai para o mesmo FIFO.

---

## 9. Segurança

### 9.1 Confiança e integridade
- O parser nunca executa código do script.
- Modo dev (`kbash run arquivo.sh`): exibe caminho e SHA-256 antes de executar.
- Modo bundle: o payload traz `manifest.json` com hash; o runtime verifica antes de abrir a GUI e recusa se divergir. **Não implementado** (§11.2).
- Valores de `rt_secret` e opções `type=password` nunca vão para logs (nem para o arquivo de log persistente).

### 9.2 Elevação de privilégio
- **Desligada por enquanto** (`PRIVILEGE_ELEVATION = False` em `core/executor.py`):
  steps `#@root true` rodam como usuário comum, sem pedir senha e sem `pkexec`.
- Desenho futuro (não implementar sem pedir): steps `#@root true` rodam com
  `pkexec env <vars> bash ...`, repassando só as variáveis `RT_*`/`OPT_*`
  necessárias; a GUI avisa antes de executar quais steps pedem privilégios.
- Scripts **não** devem chamar `sudo` por dentro (não há TTY); documentar em `docs/PORTAR.md`.

### 9.3 Logs persistentes
Planejado: `$XDG_STATE_HOME/<id>/logs/AAAA-MM-DD_HH-MM-SS.log`, com timestamp, step e stream por linha, mantendo os últimos 20. **Não implementado** (Fase 6). Hoje o log só existe na tela e pode ser salvo pelo usuário (*Salvar log*).

---

## 10. GUI

### 10.0 Como o script chega ao runtime (§10.2.0)

Há três caminhos, decididos nesta ordem:

1. **Argumento**: `kbash run arquivo.sh` (ou só `kbash arquivo.sh`, e no AppImage
   `AppImage arquivo.sh`) abre esse script. Com `--headless`, roda no terminal.
2. **Embutido**: sem argumentos, se o bundle tem `$APPDIR/payload/script.sh`
   (o build copia o `PAYLOAD`), abre esse script. É o comportamento do AppImage
   distribuído com um script.
3. **Tela inicial (home)**: sem argumentos e sem script embutido, ou com
   `kbash home` (mesmo com script embutido), abre a home. Lá o usuário escolhe um
   `.sh` pelo seletor do portal (`Escolher script…`) ou arrasta o arquivo para a
   janela. `Bridge.loadScript` valida (`.sh`, legível, parse sem erro) e troca o
   script sem reiniciar o app. Não há execução na home: `Bridge.start` recusa.

Um AppImage sem script embutido (`PAYLOAD= tools/build-appimage.sh ...`) é o
runtime genérico, que abre sempre na home.

### 10.1 Toolkit
- PySide6 **da distro** (no modo dev) + QML, com `import org.kde.kirigami` **sem versão** —
  `3.0` não existe nas builds testadas. No modo dev, o Kirigami precisa estar
  instalado no sistema: `gui/app.py` faz um probe de verdade e erra alto, com
  diagnóstico, se o módulo não carrega. Não há fachada alternativa.
- **Empacotado (AppImage), o Kirigami e o estilo Breeze vão embutidos** (§11.1,
  `docs/BREEZE.md`). O PySide6 do bundle é o `6.10.2` fixado, que casa com o Qt
  dos pacotes Ubuntu usados para as libs KF6.
- Estilo QQC `org.kde.breeze` por padrão (parecer KDE nativo); respeita
  `QT_QUICK_CONTROLS_STYLE` se já definido. Sem o módulo Breeze, cai para `Basic`.
- Fonte base com piso de 11 pt (`FONTE_MINIMA_PT` em `gui/app.py`): sem o tema de
  plataforma do KDE, o Qt cai em ~9 pt e os controles do Kirigami ficam pequenos.
- **Exceção de cor (checkbox):** `gui/qml/kirigami/kbash/AppCheckBox.qml` fixa as
  cores do indicador por pedido do usuário: check **branco** sobre o `highlightColor`
  quando marcado; contorno **preto** quando desmarcado. Não é uma regra geral: as
  outras telas continuam usando `Kirigami.Theme`.
- Nem todo tipo `Kirigami.X` existe: só `ApplicationWindow`, `Page`,
  `PasswordField`, `Dialog`, `Icon`, `Heading`, `InlineMessage`, `Action`,
  `OverlaySheet` (+ `Theme`, `Units`) foram verificados. Botões, campos,
  combos e switches usam QtQuick.Controls nativos (sem `background` nem
  `contentItem` próprios) — o Breeze renderiza nativo. Delegates de
  `Repeater`/`ListView` nunca declaram `modelData` local e nunca usam
  `required` em propriedade alimentada pelo modelo: `required` é avaliado
  antes do contexto do modelo anexar e o delegate nasce vazio em silêncio;
  lê-se `model.<papel>`/`modelData` direto do contexto.
- Papéis existentes em `Kirigami.Theme` (sondados no KF6 6.30): `textColor`,
  `backgroundColor`, `alternateBackgroundColor`, `disabledTextColor`,
  `linkColor`, `visitedLinkColor`, `highlightColor`, `highlightedTextColor`,
  `positiveTextColor`, `neutralTextColor`, `negativeTextColor`, `hoverColor`,
  `focusColor`. **Não existem**: `midColor`, `frameColor`,
  `placeholderTextColor`, `inactiveTextColor`, `buttonBackgroundColor` — não usar
  (viram `Unable to assign [undefined]`).
- **Kirigami embutido e fachadas.** As fachadas são componentes nativos do
  Kirigami quando ele existe na build; os que não existem (`AbstractPageHeader`,
  `ProgressBar`, `AbstractCard.contentColumn`) têm desenho próprio e justificado.
  Ver `docs/KIRIGAMI-SPIKE.md` para o levantamento.
- **Componentes nativos obrigatórios.** Nenhuma tela desenha o contêiner,
  botão, selo, estado vazio ou cabeçalho à mão: tudo passa pelas fachadas. São
  eles: `AbstractCard` (via `contentItem` + `padding`), `Heading`, `Icon`,
  `InlineMessage`, `Dialog`, `Badge`, `PlaceholderMessage`, `PasswordField`,
  `Separator`, `OverlayDrawer`, `ScrollablePage`, `ListSectionHeader`.
- **Política de Layout das fachadas.** Fachada nova **não** embute
  `Layout.fillWidth/fillHeight`: quem usa decide (`AppRadioButton`,
  `AppSlider`, `AppTextArea`, `AppScrollView` nascem sem). As antigas
  (`AppTextField`, `AppComboBox`, `AppCard`, `AppPlaceholder`, `StepRow`,
  `AppProgressBar`, `LogPanel`) trazem por herança histórica e ficam —
  removê-las quebraria todos os chamadores por nada.
- **Largura da página: a coluna precisa de largura explícita.** A tela
  inteira colapsava para ~371 px numa janela de 940 px, com o texto cortado.
  A regra que resolve (e as duas que quebram de novo):
  - a `AppPage` é um `Item` comum, com o `ScrollView` em `anchors.fill`, e a
    coluna de conteúdo tem **`width` calculada** a partir de um `Item`
    intermediário de largura `scroll.availableWidth`; centralizar é com `x`
    calculado, não com `Layout.alignment`;
  - **`Layout.alignment: Qt.AlignHCenter` na coluna a faz medir pelo
    conteúdo**, não pela janela — é o que reproduz a tela estreita;
  - a página **não** declara `implicitWidth` atado ao ScrollView: isso é
    circular (a página mede o filho, o filho mede a página) e o Layout fica
    com 0;
  - a `ApplicationWindow` não põe Layout nos filhos diretos: o conteúdo
    precisa de uma `ColumnLayout` com `anchors.fill: parent` em volta, senão o
    `StackLayout` das telas fica 0x0.
- **A janela não usa o `pageStack`.** A `Kirigami.ApplicationWindow` tem
  `pageStack` (`PageRow`), mas ele é um `ColumnView` que em janela larga
  deixa a tela anterior espremida ao lado da atual e não assenta sozinho. Como
  o fluxo Boas-vindas→Seleção→Execução→Resultado é linear, as telas ficam num
  `StackLayout` dirigido por `bridge.page`, que é previsível e testável.
- **Seleção de arquivos/pastas: XDG portal, não QtQuick.Dialogs.**
  Abrir/salvar arquivos e escolher pastas (`type=file/path`, prompt `file`,
  *Salvar log*) passa pelo `org.freedesktop.portal.FileChooser` no session
  bus (`bridge.pickFolder/pickOpenFile/pickSaveFile` → signal
  `filePicked(token, paths)`): o diálogo nativo do ambiente abre fora do
  processo, com múltipla seleção. Os filtros de `file` **não** passam ao portal
  (o QtDBus não expressa a estrutura `a(sa(su))`): são validados e guardados.
  `path` usa `OpenFile` com `directory=true` (este portal não expõe
  `OpenDirectory`). Sem bus/portal, o pedido falha graciosamente (aviso +
  resultado vazio, sem travar). Motivo da escolha: os diálogos do
  `QtQuick.Dialogs` quebraram sob o Breeze desta build.
- **Links (`type=link`)** abrem por `Bridge.openLink`, que usa
  `QDesktopServices.openUrl` e só aceita `http`/`https` (também recusa no
  runtime o que o parser já recusou).
- Os componentes ficam em `gui/qml/kirigami/kbash/`, importados como módulo `kbash`;
  as telas ficam em `gui/qml/pages/`, importadas como módulo `pages`.
- **Tema claro/escuro: segue o sistema, sem botão para trocar.** `theme.isDark`
  deriva de `Kirigami.Theme.backgroundColor`. Não existe alternância manual em
  tempo de execução: na sonda feita no KF6 6.30 (Qt 6.11), o Kirigami **não expõe
  `Theme.colorScheme`** e **ignora** `QGuiApplication.styleHints().setColorScheme()`.
  Um botão que escrevesse um `forcedScheme` próprio mudaria só o rótulo dele.
  Refazer a sonda ao trocar a versão do Kirigami.
- Cores que o app desenha à mão (toast, selo, painel de log) saem das
  funções de `Theme.qml` (`faint`/`hairline`/`onSurface`) misturadas sobre a
  cor do texto. **Não usar cor fixa** (`#ffffff`, `#000000`): o que é
  legível no tema claro é ilegível no escuro. O toast pinta o fundo com
  `surface` e o texto com a cor do nível — nunca o contrário.
- **Tipografia**: nenhum negrito explícito (`font.bold`). A hierarquia vem dos
  níveis do `Kirigami.Heading` e do texto secundário (`opacity`), como nos apps KDE.
- `AppButton.variant` aceita `default | primary | danger | flat`. O Breeze não
  tem um papel "destrutivo" e §10.1 proíbe `background`/`contentItem`
  próprios, então `danger` reusa o destaque de `primary`; o rótulo é que
  diz o que o botão faz.

### 10.2 Telas

1. **Boas-vindas** — ícone, nome, descrição, versão, autor; botão *Começar*. Sem
   script (home, §10.0), a mesma tela mostra a zona de arrastar e o seletor do portal.
2. **Seleção** — formulário das opções (widget por `type`) e lista de steps agrupados, com checkbox, título, descrição e selos ("requer root", "por dependência", "obrigatório"). `paragraph` aparece como texto e `link` como botão, sem linha `OPT_*`. Botão *Executar* desabilitado até opções obrigatórias válidas.
3. **Execução** — lista de steps com ícone de estado e duração; barra de progresso geral e do step; painel de log monoespaçado (stderr destacado, auto-scroll pausável, copiar); botão *Cancelar*. Prompts aparecem em diálogo modal.
4. **Resultado** — sucesso/falha/cancelado, resumo por step, *Ver log*, *Salvar log*, *Fechar* (e *Tentar novamente* os que falharam).

As quatro telas são declaradas como módulo (`gui/qml/pages/qmldir`) e
instanciadas **uma única vez** num `StackLayout` em `main.qml`, que só troca o
índice com `bridge.page`. Um `Loader` por página destruiria e recriaria a tela
a cada navegação, levando junto o scroll da lista de etapas, o *auto-scroll* do
log e o diálogo de log aberto. `bridge.goToPage` ignora índices fora de
`0..3` e, enquanto a execução está em andamento, ignora qualquer saída da tela
de execução (é onde ficam o log e o *Cancelar*).

O prompt `confirm` mostra **Sim / Não / Cancelar**, no mesmo estilo do
`kdialog --yesno`: "Não" responde `false` (o script recebe `no` e segue o
caminho normal, §8.3) e é distinto de *Cancelar*, que responde a sentinela de
cancelamento (§7.4). O botão destacado é o do default declarado pelo helper
(`rt_confirm "..." y|n`, §8.4).

5. **Gaveta de log** — o painel de log mora numa
`Kirigami.OverlayDrawer` inferior (`modal: false`, não bloqueia o app)
em vez de ocupar a tela de Execução: abre e fecha **só por ação do
usuário** — botão de log no cabeçalho, `Ctrl+L`, botão *Ver log* ou
`bridge.logDrawerOpen`. Nunca abre sozinha (nem no início da execução).
Auto-scroll pausável e *Copiar* viajam junto dentro da gaveta.

### 10.3 Modelos QML (`gui/models.py`)
- `StepListModel` (`QAbstractListModel`): roles `stepId, title, description, group, checked, locked, status, root, duration, required, autoAdded, reason, statusLabel`.
- `OptionModel`: roles `optId, type, label, value, choices, required, error, help, default, minimum, maximum, step, filters, pattern, minlen, maxlen, multiple, visible, url`. Inclui `paragraph`/`link` (sem valor; o QML escolhe o widget pelo `type`).
- `LogModel`: buffer circular (máx. ~20 mil linhas) com **atualização em lote a cada ~50 ms** para a GUI não travar com saída volumosa.
- `SelectedStepsProxy` (`QSortFilterProxyModel` sobre o `StepListModel`): execução e resultado listam só as etapas selecionadas (`checked`).

### 10.4 Acessibilidade e UX
Navegação por teclado, contraste adequado, textos traduzíveis com `qsTr`. Nenhuma operação longa na thread da GUI.

---

## 11. Empacotamento e distribuição

### 11.1 AppImage (implementado)

Alvo: um `.AppImage` x86_64 que abre em qualquer distro com glibc ≥ 2.38, com
visual Breeze, sem depender de nada instalado (só GPU e D-Bus do host).

- **Piso de build**: Ubuntu 26.04 (`resolute`). O binário exige glibc **2.38**
  (libwayland 1.24 e KF6). Build em Ubuntu mais antigo não serve.
- **Python e Qt**: `PySide6 == 6.10.2` (exato), para casar com o Qt 6.10.2 dos
  pacotes Ubuntu. O build **falha cedo** se a versão for outra, porque os
  plugins KF6 exigem o mesmo `qt6-base-private-abi`.
- **Embutido**: o módulo QML e as libs do Kirigami 6.24 e do Breeze 6.6.4
  (`org/kde/breeze`, `org/kde/kirigami`, `org/kde/guiaddons`, `libKF6*`), o
  plugin de tema do Kirigami (cores e fonte do KDE quando houver) e o tema de
  ícones Breeze (lista em `tools/breeze-debs.txt`). Detalhes e medições em
  `docs/BREEZE.md`.
- **Poda**: `tools/prune_unused_libs.py` mantém só as libs alcançadas pelo NEEDED
  a partir do que o app carrega; `tools/prune_stdlib.py` mantém só o fecho de
  imports medido por rastreio real (`tools/stdlib-trace.txt`).
- **ICU filtrado** (opcional, `tools/build-icu-data.sh`): só root/en/pt, com o mesmo
  soname. Sem ele, o build usa o ICU completo (32 MB) e segue funcionando.
- **Tamanho medido**: **40,1 MB** no AppImage (zstd com bloco de 1 MB e nível 22).
  Não é a meta antiga de 80–130 MB: a meta atual é não passar de ~45 MB sem
  justificativa por componente.
- **Ferramenta**: `tools/build-appimage.sh <kbash> <saida.AppImage>`, com
  `appimagetool` (`mksquashfs` embutido, que só aceita zstd). Para
  distribuição, o arquivo é dividido em partes de 20 MB (`split -b 20M`), e a
  remontagem é verificada com `cat parte* | cmp`.
- **AppRun**: define `LD_LIBRARY_PATH`, `QML2_IMPORT_PATH`, `QT_PLUGIN_PATH`,
  `XDG_DATA_DIRS` (ícones) e executa o runtime. Não fixa o estilo: o runtime
  escolhe `org.kde.breeze` (§10.1).
- **Payload**: o script vai em `$APPDIR/payload/script.sh`.
- Portais XDG funcionam de dentro do AppImage (session bus do host).
- **Limitação conhecida**: o bundle não foi testado em um desktop KDE real
  (§13, Fase 4). As versões do Kirigami e do Breeze são do Ubuntu 26.04, não do
  KDE do usuário.
- **Licença**: LGPL — a receita de build é aberta e as `.so` são substituíveis
  (sem link estático).

### 11.2 Payload e comando `pack` (não implementado)

> ❌ **Não implementado.** Não existem `packaging/`, comando `pack`, `manifest.json`
> nem verificação de hash no bundle. O caminho que existe hoje é o do §11.1.
> Este subitem é o desenho para um formato de bundle independente de AppImage.

Layout proposto:

```
meu-instalador/
├── runtime                 # binário (onedir)
├── _internal/...           # libs geradas pelo empacotador
└── payload/
    ├── script.sh
    ├── assets/             # opcional
    └── manifest.json       # sha256, versão do spec, nome
```

Descoberta do payload (`packaging/discovery.py`), em ordem:
1. `--script <caminho>` (modo dev — é o que existe hoje)
2. `$APPDIR/payload` (AppImage — já é o caminho usado pelo §11.1)
3. `payload/` ao lado do executável

`kbash pack script.sh -o meu-instalador [--assets dir] [--name X]` copiaria o runtime
(onedir) e geraria `payload/` + `manifest.json`.

### 11.3 Binário único (pesquisa, fora da v1)
Anexar o payload ao final do executável conflita com bootloaders onefile do PyInstaller/Nuitka (que também usam o fim do arquivo). Alternativas a investigar: AppImage (já adotado, §11.1), launcher próprio em C/Rust que monta o payload, ou `--onedir` + squashfs. Não bloquear a v1 por isso.

---

## 12. CLI

```
kbash                                       # sem argumentos: script embutido (§10.0) ou a home
kbash home                                  # abre a home mesmo com script embutido
kbash <script.sh>                           # atalho de `kbash run <script.sh>`
kbash run <script.sh>                       # GUI com o script
kbash run <script.sh> --headless [--select a,b] [--opt k=v ...] [--yes] [--ui auto|qt|terminal|yes|none]
kbash check <script.sh>                     # valida (erros e warnings com linha)
kbash plan <script.sh> [--select a,b] [--opt k=v ...] [--json]   # mostra o plano de execução e sai
```

`--ui` (ou `$KBASH_UI`) escolhe o provedor de interação descrito em §8.5.

Códigos de saída: `0` sucesso · `1` falha de step · `2` erro de parse/validação · `130` cancelado.

O modo `--headless` usa o **mesmo core**; prompts viram perguntas no terminal (ou `--yes` assume os defaults). Opções obrigatórias sem valor e sem `default` ainda bloqueiam a execução (`campo obrigatório`): passe-as com `--opt`. Serve como base de testes e para CI.

---

## 13. Fases, entregas e critérios de aceite

Histórico: o projeto foi reescrito uma vez (formato de fluxo → formato de
anotações; ver git). As fases abaixo descrevem o estado atual. Cada fase só
está pronta quando **todos** os critérios passam.

### Fase 1 — Core sem GUI ✅
- [x] `parser.py` lê todas as diretivas do §4 e valida conforme §4.6, com mensagens `arquivo:linha`.
- [x] `planner.py` resolve dependências, ordem e ciclos (§6).
- [x] `executor.py` roda steps com env do §7.2, captura stdout/stderr em streaming, trata falha, timeout e cancelamento (§7.4).
- [x] CLI: `check`, `plan`, `run --headless`.
- [x] Testes com pytest cobrindo: parse válido/inválido, dependências, ciclo, falha com `stop` e `continue`, cancelamento (mata filhos do step), timeout.

### Fase 2 — Protocolo e helpers ✅
- [x] `ipc.py` com FIFOs (§8.1) e `rt.sh` com toda a API do §8.4.
- [x] `core/ui.py` com `Prompt`/`Answer`/`Ui` e registro de provedores (§8.5):
      `terminal`, `yes`, `none` no core e `qt` na GUI — sem nenhum processo externo.
- [x] Testes: round-trip dos prompts, valores com aspas, `\`, quebra de linha, TAB e UTF-8; `rt_secret` não aparece em log.
- [x] `rt.sh` funciona em modo fallback sem runtime.
- [x] Testes do provedor de UI: `ask` de cada implementação devolve o mesmo `Answer`
      para o mesmo `Prompt` (inclusive `cancel`).

### Fase 3 — GUI ✅
- [x] As 4 telas do §10.2 funcionando ponta a ponta com um script de exemplo.
- [x] `bridge.py` e modelos do §10.3, com log em lote sem travar em 100 mil linhas de saída.
- [x] Prompts do protocolo aparecem como diálogos (canceláveis) e respondem ao script.

### Fase 4 — Kirigami e polimento ✅ (com ressalvas)
- [x] Fachadas Kirigami (módulo `kbash`, API verificada por teste).
- [x] Spike de empacotamento do Kirigami (§10.1) documentado em `docs/KIRIGAMI-SPIKE.md`.
- [x] Tema claro/escuro, ícones (`#@icon`: nome de tema ou arquivo em `assets/`),
      estados vazios e de erro (`InlineMessage`).
- [x] Correções apuradas em uso real: `import org.kde.kirigami` sem versão,
      estilo Breeze por padrão, `AppProgressBar` sem QQC `ProgressBar` (bug do
      estilo), tipos Kirigami inexistentes trocados por QtQuick.Controls, probe
      de Kirigami em subprocesso.
- [ ] Validar a fachada do Kirigami num desktop KDE real (falta hardware com
      Kirigami; ver última seção do spike).

### Fase 5 — Empacotamento 🟡 (parcial)
- [x] AppImage reproduzível, com Kirigami e Breeze embutidos e medido (§11.1).
- [ ] `pack`, `discovery.py`, `manifest.json` e verificação de hash (§9.1, §11.2). Não implementados.

### Fase 6 — Robustez e documentação (parcial)
- [x] Tipos `paragraph` e `link` (§4.3), com validação, testes e exemplo em `examples/all-options.sh`.
- [x] Guia para portar um script bash existente (`docs/PORTAR.md`).
- [ ] Elevação de privilégio: **desligada** (`PRIVILEGE_ELEVATION = False`;
      steps `#@root` rodam como usuário comum, sem pedir senha).
- [ ] Logs persistentes com rotação (§9.3).
- [ ] Referência do formato para autores (`docs/AUTHORING.md`), além do guia de porte.

---

## 14. Convenções para desenvolvimento com IA (conteúdo base do `AGENTS.md`)

- Leia `SPEC.md` antes de qualquer tarefa; cite a seção que está implementando.
- Faça **uma fase (ou sub-tarefa) por vez**. Não altere código fora do escopo pedido.
- `core/` nunca importa Qt. Type hints em todo código novo. Python ≥ 3.11.
- Escreva testes junto com o código; rode `pytest` antes de dar a tarefa por concluída.
- Nunca use `shell=True`; monte argumentos como lista.
- Não adicione dependências sem justificar; `rt.sh` deve continuar em bash puro.
- Se o spec estiver ambíguo ou errado, **pare e proponha a mudança no spec** em vez de improvisar.
- Commits pequenos, um por etapa funcional, com mensagem descrevendo a seção do spec atendida.

---

## 15. Questões em aberto

1. ~~Nome definitivo do projeto~~: decidido, **kbash** (pacote, comando, app e extensão `.kbash`). A diretiva `#@runtime 1` e as funções `rt_*`/`RT_*` continuam como API dos scripts.
2. Condicionais em steps (`#@when editor=vim`) — v1.1?
3. Suporte a PTY para ferramentas que exigem terminal (barras de progresso, cores).
4. Renderização de cores ANSI no painel de log (v1 remove as sequências).
5. Internacionalização de títulos/descrições (`#@title[pt_BR]`).
6. Formato de bundle sem AppImage (§11.2) — só se houver um caso de uso que o AppImage não atenda.
7. Validar a fachada e o bundle num desktop KDE real (Fase 4), e decidir se `org.kde.desktop` vale o custo extra no lugar do Breeze QQC2 (ver `docs/BREEZE.md`, contraste dos controles).
