# Como escrever um script para o kbash

Referência para quem cria um script `.kbash` (ou `.sh` anotado) do zero. Para
transformar um script bash que já existe, veja [PORTAR.md](PORTAR.md). A regra
completa está no [SPEC.md](../SPEC.md); aqui está o que você precisa para escrever.

## 1. Ideia geral

Um script kbash é um script bash comum com **anotações** em comentários `#@`.
As anotações descrevem o formulário (opções) e as etapas (steps). Cada step é
uma função bash. O runtime mostra o formulário, deixa o usuário marcar as etapas,
roda cada uma em um processo novo e mostra o log.

Duas regras importantes:

- **Só definições no topo.** O script é lido de novo em cada step: código solto
  fora de funções roda várias vezes. Deixe no topo apenas funções e variáveis.
- **O parser nunca executa o script.** Ele lê as anotações estaticamente.

## 2. Esqueleto mínimo

```bash
#!/usr/bin/env bash
#@runtime 1
#@name Meu script

#@step ola
#@title Dizer olá
ola() {
  rt_log "olá"
}
```

A função do step precisa ter o **mesmo nome do id** (ou use `#@function nome`).
Um exemplo completo está na seção 11.

Valide sempre antes de abrir:

```bash
kbash check meu-script.kbash     # erros e avisos, com linha
kbash plan meu-script.kbash      # o que vai rodar, com as opções
```

`check` sai com `2` se houver erro de parse ou validação, `0` caso contrário.

## 3. Cabeçalho

Anotações de cabeçalho ficam **antes** da primeira `#@step` ou `#@option`.

| Diretiva | Obrigatória | Para que serve |
|---|---|---|
| `#@runtime 1` | sim | Versão do formato. |
| `#@name Texto` | sim | Título na janela. |
| `#@id com.exemplo.app` | não | Identificador (log, configuração, predefinições). Padrão: slug do nome. Use algo estável: é o nome do arquivo de predefinições. |
| `#@description Texto` | não | Descrição curta, mostrada na tela inicial e na biblioteca. |
| `#@version 1.2.0` | não | Versão do script. |
| `#@author Nome` | não | Autor. |
| `#@icon nome` | não | Ícone: nome do tema (ex.: `folder-remote`) ou arquivo em `assets/` (ex.: `assets/logo.svg`). |
| `#@requires cmd1,cmd2` | não | Comandos que precisam estar no `PATH`; checados antes de executar. |
| `#@strict true\|false` | não | Se `true` (padrão), os steps rodam com `set -o errexit -o pipefail`. |

### Ícones

- **Nome de tema:** qualquer nome do tema de ícones do sistema. Confira que ele
  existe (ex.: `ls /usr/share/icons/*/*/*/nome.svg`). Se não existir, aparece o
  ícone padrão.
- **Arquivo:** o caminho é relativo a `assets/`, ao lado do script. Um arquivo
  é reconhecido quando tem `/` ou termina em `.svg` ou `.png`. Arquivo que não
  existe cai no ícone padrão.

## 4. Opções

Opções são o formulário. Cada uma vira a variável de ambiente `OPT_<ID>` (id em
maiúsculas) em todos os steps.

```bash
#@option pasta   type=path label="Pasta a copiar" default="$HOME/Documentos" required=true
#@option perfil  type=choice label="Perfil" choices="rapido,completo" default=rapido
#@option ativo   type=bool label="Ativar" default=false
#@option senha   type=password label="Senha"
```

### Tipos

| `type` | Widget | Valor em `OPT_<ID>` |
|---|---|---|
| `string` (padrão) | campo de texto | o texto |
| `password` | campo de senha | o texto, **nunca registrado no log nem salvo em predefinições** |
| `text` | área de várias linhas | o texto, com quebras de linha |
| `choice` | lista suspensa (`choices=`) | a escolha |
| `multi` | várias escolhas (`choices=`) | separadas por vírgula |
| `bool` | caixa de seleção | `1` ou `0` |
| `number` | campo numérico (`min=`, `max=`) | o número, como texto |
| `slider` | controle deslizante (`min`, `max`, `step`) | o número |
| `path` | pasta ou arquivo digitado | o caminho (`~` e `$HOME` expandidos) |
| `file` | seletor de arquivo (`multiple=true` permite vários) | o caminho ou caminhos separados por vírgula |
| `date` | data | `AAAA-MM-DD` |
| `time` | hora | `HH:MM`, 24 horas |
| `paragraph` | só texto (`label=` é o texto) | não tem valor |
| `link` | botão que abre `url=` (só `http`/`https`) | não tem valor |

### Atributos

| Atributo | Para que serve |
|---|---|
| `label` | Texto exibido. Padrão: o id. |
| `default` | Valor inicial. Aceita `$HOME` e `~`. |
| `required=true` | Bloqueia *Executar* enquanto vazio. |
| `help` | Texto de ajuda. |
| `choices` | Lista separada por vírgula (`choice`/`multi`). |
| `min`, `max`, `step` | Faixa e passo (`number`/`slider`). |
| `pattern` | Expressão regular que o valor precisa casar inteira (`string`/`password`). |
| `minlen`, `maxlen` | Tamanho mínimo e máximo (`string`/`password`/`text`). |
| `filters` | Globs do seletor de arquivo. Hoje o portal abre sem filtro. |
| `show_if` | Mostra a opção só quando outra tem certo valor: `show_if="perfil=completo"`. Várias condições com vírgula (E). |
| `needs_step` | Liga a opção a um step: ela aparece **dentro da linha desse step**, e só enquanto o step estiver marcado. |
| `group` | Bloco da tela onde a opção aparece, pelo título. Sem `group`, fica no bloco sem título. Ignorado em opção com `needs_step`. |

### Quando usar `needs_step`

Use `needs_step` sempre que uma opção configura um step. O usuário vê a escolha
no mesmo lugar em que decide rodar a ação. Opção sem `needs_step` é geral e fica
no bloco indicado por `group=`. Quem organiza a tela é você: blocos aparecem na
ordem da primeira declaração no arquivo (§4.8.1 do SPEC).

Não crie opção só para ligar ou desligar uma etapa: o checkbox do step já faz isso.

```bash
#@option bwlimit type=number label="Limite (MB/s)" min=0 default=0 needs_step=enviar
#@step enviar
#@title Enviar
```

`show_if` e `needs_step` combinam (E): a opção aparece só se as duas condições valem.

### Predefinições do usuário

O usuário pode salvar valores das opções como predefinição (na linha *Predefinição*, no topo da tela).
Elas ficam em `kbash-config/<id>.json`, na pasta do programa. Senhas nunca entram.
Por isso o `#@id` precisa ficar estável depois que o script for distribuído.

## 5. Steps

```bash
#@step enviar
#@title Enviar para a nuvem
#@desc Copia ou sincroniza, conforme o modo escolhido.
#@group Envio
#@default on
#@depends verificar
#@timeout 3600
#@on_error stop
enviar() {
  rclone copy "$OPT_PASTA" "$OPT_DESTINO"
}
```

| Diretiva | Para que serve |
|---|---|
| `#@step id` | Começa o bloco. Deve ser igual ao nome da função (ou use `#@function nome`). |
| `#@title` | Título. Padrão: o id. |
| `#@desc` | Descrição (pode repetir a linha). |
| `#@group` | Bloco da tela onde o step aparece (também vale para ações e opções com `group=`). |
| `#@default on\|off` | Marcado por padrão. Padrão: `on`. |
| `#@required` | Sempre marcado, não pode ser desmarcado. |
| `#@depends a,b` | Marcar este step marca `a` e `b` junto. |
| `#@root true` | Roda como root, com autorização do sistema (seção 8). |
| `#@timeout N` | Limite em segundos. Padrão: sem limite. |
| `#@on_error stop\|continue` | Se falhar: parar tudo (padrão) ou seguir para o próximo. |

As anotações de step ficam em linhas seguidas, logo antes da função.

## 5a. Ações (mini-scripts)

Uma ação é uma função que o usuário roda **na própria tela de seleção**, por um botão,
sem entrar no plano. Serve para medir ou checar algo antes de *Executar*.

```bash
#@action medir
#@title Medir o que seria liberado
#@desc Só mede. Não apaga nada.
#@button Medir
#@group Verificar
#@timeout 60
medir() {
    local mb
    mb=$(du -sm "$OPT_PASTA" 2>/dev/null | cut -f1) || mb=""
    rt_log "Ocupado agora: ${mb:-desconhecido} MiB"
}
```

| Diretiva | Para que serve |
|---|---|
| `#@action id` | Começa o bloco. Mesmas regras de id dos steps. |
| `#@title`, `#@desc` | Título e descrição. |
| `#@button` | Rótulo do botão. Padrão: *Executar*. |
| `#@group` | Bloco da tela. |
| `#@root true` | Pede a senha do sistema antes de rodar (seção 8). |
| `#@timeout N` | Segundos até encerrar. Padrão: 60. |
| `#@function nome` | Nome da função, se for diferente do id. |

**O que a ação recebe.** As `OPT_*` com os valores **atuais** da tela, no clique. Por
isso ela pode depender de opções já preenchidas. Opção oculta entra com o `default`.

**O que ela devolve.** A saída de `rt_log` e do que for impresso, embaixo do botão, com
status *Concluído*, *Falhou (código N)* ou *Tempo esgotado*. Nada disso vai para o log
de execução nem para o resultado.

**Limites.** Ação não é interativa: `rt_confirm`, `rt_input`, `rt_choice` e os outros
helpers de entrada falham com mensagem e a ação termina como *Falhou*. Use uma etapa
para perguntar algo. Não existe `#@default`, `#@required`, `#@depends` nem `#@on_error`
em ação; se aparecerem, geram aviso e são ignorados.

## 6. Variáveis que o runtime define

Dentro de qualquer step:

| Variável | Conteúdo |
|---|---|
| `OPT_<ID>` | Valor de cada opção que tem valor. |
| `RT_STEP_ID`, `RT_STEP_FN` | Id e função do step atual. |
| `RT_SCRIPT` | Caminho do script. |
| `RT_WORKDIR` | Pasta temporária da execução (removida ao final). |
| `RT_VAR_<CHAVE>` | Valores guardados por `rt_set` em steps anteriores. |
| `RT_STRICT`, `RT_MODE` | `1`/`0` e sempre `step`. |

O step roda com o diretório atual em `$HOME`. Os steps rodam em processos separados,
então variáveis do bash **não** passam de um step para outro: use `rt_set` / `rt_get`.

## 7. Helpers `rt_*`

Use os helpers em vez de `read` ou `zenity`. Eles conversam com a interface. Sem
a interface (ex.: `kbash run --headless`), caem para o terminal, então o script
continua rodando.

| Função | Uso |
|---|---|
| `rt_log "texto"`, `rt_warn`, `rt_error` | Mensagem no log. |
| `rt_progress 50 "texto"` | Progresso do step (`-` = indeterminado). |
| `rt_confirm "pergunta" [y\|n]` | Retorna 0 ou 1. |
| `nome=$(rt_input "Nome" [padrão])` | Campo de texto. |
| `senha=$(rt_secret "Senha")` | Campo de senha; não aparece no log. |
| `op=$(rt_choice "Qual?" a b c)` | Escolha. |
| `$(rt_multi "Quais?" a b c)` | Várias escolhas, uma por linha. |
| `n=$(rt_number "Quantos?" 1 1 10)` | Número validado. |
| `d=$(rt_date "Quando?" 2026-12-31)` | Data ISO. |
| `h=$(rt_time "Hora?" 08:30)` | Hora `HH:MM`. |
| `f=$(rt_file "Foto" "" "*.png")` | Caminho de arquivo. |
| `t=$(rt_text "Notas")` | Texto de várias linhas. |
| `rt_textbox "Título" "texto longo"` | Mostra texto para ler. |
| `win=$(rt_progresswin_start 5 "Copiando")` | Janela de progresso. Depois `rt_progresswin_update "$win" 3` e `rt_progresswin_done "$win"`. |
| `rt_set chave valor` / `rt_get chave` | Guarda um valor para os próximos steps. |
| `rt_notify "texto"` | Notificação na interface. |
| `rt_fail "motivo"` | Para o step com erro. Sem argumento, informa o nome do step. |

Chaves de `rt_set` são letras, números e `_`, com início de letra ou `_`.
Outras são ignoradas com aviso.

## 8. Root

Steps com `#@root true` rodam como root. O sistema mostra o diálogo de autorização
(polkit) **uma vez, antes do primeiro step**, depois que o usuário revisou o plano.

- **Não use `sudo` dentro do script.** Não há terminal, e o step já é root.
- O root recebe um ambiente **próprio**: `PATH` só com diretórios do sistema
  (`/usr/bin`, `/usr/sbin` etc.), `HOME=/root`, e só as variáveis `RT_*`, `OPT_*` e
  as de idioma e tela (`LANG`, `TERM`, `DISPLAY`, `XAUTHORITY`, `XDG_*`). Ele **não**
  herda o `PATH` do usuário.
- Por isso, comando instalado só na sua pasta pessoal (`~/.local/bin`) não existe
  como root. Use comandos do sistema ou instale-os para todos.
- `#@requires` ainda é checado no `PATH` do usuário, não no do root. Limitação
  conhecida (SPEC §9.2).

## 9. Erros e avisos comuns

`kbash check` mostra `arquivo:linha: erro:` ou `aviso:`. Os erros mais comuns:

| Mensagem (resumo) | Causa |
|---|---|
| `id duplicado` | Dois steps ou opções com o mesmo id. |
| `função do step não encontrada` | `#@step x` sem `x() { ...; }` (ou `#@function`). |
| `depends aponta para step inexistente` / ciclo | Dependências erradas. |
| `choice sem choices` / `default fora de choices` | Lista de escolhas incompleta. |
| `show_if` ou `needs_step` com referência inexistente | O id citado não existe. |
| `#@requires` com espaços (`find awk df`) | A lista é separada por **vírgula**: `#@requires find,awk,df`. |
| `group` em opção com `needs_step` | Aviso: a opção fica na linha do step e o grupo é ignorado. |
| `url` ausente ou não `http`/`https` | Em `link`. |
| atributo que não se aplica ao tipo | Aviso: por exemplo, `default` em `paragraph`. |
| comando solto fora de função | Aviso heurístico: esse código roda a cada step. |

## 10. Boas práticas

- **Idempotente:** o script pode rodar de novo sem estragar nada (ex.: `mkdir -p`,
  `grep -q ... || echo ... >>`).
- **Valide antes de agir:** `[ -d "$OPT_PASTA" ] || rt_fail "pasta não existe: $OPT_PASTA"`.
- **Uma responsabilidade por step.** Facilita pular, repetir e entender o log.
- **Use `rt_fail` com motivo claro.** Ele aparece na tela de resultado.
- **Não coloque segredo em opção comum.** Use `type=password`.
- **Dê um `#@id` estável.** Ele nomeia o arquivo de predefinições.

## 11. Exemplo completo

Um script de backup para a nuvem, com validação, opções condicionais e um step
opcional. Este arquivo passa em `kbash check` e `kbash plan`.

```bash
#!/usr/bin/env bash
#@runtime 1
#@name Backup para a nuvem
#@id com.exemplo.backup-nuvem
#@description Copia uma pasta para a nuvem com rclone.
#@version 1.0.0
#@author Você
#@icon folder-remote
#@requires rclone
#@strict true

# Só definições no topo: este arquivo é lido em cada step.

#@option pasta   type=path label="Pasta a copiar" default="$HOME/Documentos" required=true
#@option destino type=string label="Destino no rclone" default="nuvem:backup" required=true
#@option modo    type=choice label="Modo" choices="copiar,sincronizar" default=copiar
#@option bwlimit type=number label="Limite de velocidade (MB/s)" min=0 max=100 default=0 needs_step=enviar
#@option senha   type=password label="Senha do arquivo" needs_step=criptografar

#@step verificar
#@title Verificar pasta e destino
#@desc Confere se a pasta existe.
#@required
verificar() {
  [ -d "$OPT_PASTA" ] || rt_fail "pasta não existe: $OPT_PASTA"
  rt_log "copiando $OPT_PASTA para $OPT_DESTINO"
}

#@step criptografar
#@title Criptografar antes de enviar
#@desc Usa a senha informada, que nunca aparece no log.
#@default off
#@depends verificar
criptografar() {
  rt_log "criptografia habilitada"
}

#@step enviar
#@title Enviar para a nuvem
#@desc Copia ou sincroniza, conforme o modo escolhido.
#@depends verificar
#@timeout 3600
#@on_error stop
enviar() {
  local bw=()
  [ "$OPT_BWLIMIT" != "0" ] && bw=(--bwlimit "${OPT_BWLIMIT}M")
  if [ "$OPT_MODO" = sincronizar ]; then
    rclone sync "$OPT_PASTA" "$OPT_DESTINO" "${bw[@]}"
  else
    rclone copy "$OPT_PASTA" "$OPT_DESTINO" "${bw[@]}"
  fi
}
```

Observações sobre o exemplo:
- `verificar` é `#@required`: sempre roda, e não pode ser desmarcado.
- `criptografar` não faz nada útil aqui; serve para mostrar um step opcional com
  uma opção de senha ligada a ele (`needs_step=criptografar`).
- `bwlimit` só aparece com `enviar` marcado.
