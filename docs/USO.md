# Como usar o kbash

Guia para quem **executa** scripts `.kbash` (ou `.sh` anotados). Para escrever um
script, veja [AUTHORING.md](AUTHORING.md). Para portar um script bash existente,
veja [PORTAR.md](PORTAR.md).

## 1. Abrir um script

Há três jeitos:

- **Pela tela inicial.** Abra o programa sem argumentos. Em *Escolher script…* você
  escolhe um arquivo `.kbash` ou `.sh`. Também dá para arrastar o arquivo para a janela.
- **Pela biblioteca.** Logo abaixo, a tela inicial lista os `.kbash` da pasta onde o
  programa está (a pasta do `.AppImage`). Cada um mostra o ícone, o nome e a descrição.
  Um clique abre o script. Arquivo que não pode ser lido aparece desabilitado.
- **Pela linha de comando.** `kbash run meu-script.kbash` abre direto.

Antes de qualquer coisa, a tela mostra o **caminho** e o **SHA-256** do script em
*Integridade do script*. Nada é executado antes de você conferir isso.

Para trocar de script enquanto a home está aberta, use *Abrir outro…*.

## 2. Escolher o que rodar

A tela de seleção tem três partes:

- **Opções.** Campos do formulário que valem para o script inteiro. Ficam no cartão
  *Opções*. Campos obrigatórios precisam estar preenchidos antes de *Executar*.
- **Predefinições.** Linha *Predefinição* dentro do cartão *Opções*:
  - escolha um nome da lista para aplicar aqueles valores;
  - *Salvar como…* grava os valores atuais com o nome que você der;
  - *Apagar* remove a predefinição escolhida.

  As predefinições ficam numa pasta `kbash-config` ao lado do programa, em um arquivo
  por script. Senhas nunca são salvas.
- **Etapas.** Lista de steps com caixa de seleção, título, descrição e selos:
  - *requer root*: a etapa pede privilégios de administrador;
  - *por dependência*: entrou sozinha porque outra etapa precisa dela;
  - *obrigatório*: sempre marcada, não dá para desmarcar.

  Marcar uma etapa marca as que ela depende. Opções ligadas a uma etapa aparecem
  **dentro da linha dela**, enquanto ela estiver marcada.

*Executar* só fica disponível quando há pelo menos uma etapa marcada e as opções
obrigatórias estão válidas.

## 3. Executar

Ao clicar em *Executar*:

1. Se alguma etapa pede root, o sistema mostra o **diálogo de autorização** (polkit).
   Ele aparece **uma vez, antes da primeira etapa**. Se você cancelar, errar a senha
   ou o `pkexec` não existir, nada roda.
2. As etapas rodam em ordem. A tela mostra o progresso geral, o progresso da etapa
   atual e o status de cada uma.
3. O log ao vivo fica disponível num painel próprio.
4. *Cancelar* interrompe a execução. As etapas que já terminaram continuam como
   terminaram.

Alguns scripts abrem janelas e perguntas durante a execução (confirmar, escolher um
arquivo, digitar um texto). Responda normalmente; *Cancelar* na pergunta cancela a etapa.

## 4. Resultado

Ao terminar, a tela de resultado mostra:

- o status geral: *Concluído*, *Falhou*, *Cancelado* ou *Execução encerrada*;
- o resumo por etapa, com o tempo gasto e o motivo, se alguma falhou;
- *Ver log* para o log completo da execução;
- *Salvar log*, para guardar o texto num arquivo;
- *Tentar novamente*, que roda de novo só as etapas que falharam;
- *Fechar*, que volta para a tela de seleção.

## 5. Onde ficam os arquivos

| O quê | Onde |
|---|---|
| Predefinições | `kbash-config/<id>.json`, na pasta do programa |
| Biblioteca | os `.kbash` da mesma pasta do programa |

"Pasta do programa" é a pasta onde está o `.AppImage`. Quando o programa roda
direto do repositório (desenvolvimento), é a raiz do projeto, e a biblioteca usa
a pasta `examples/`.

## 6. Linha de comando

```bash
kbash home                                  # tela inicial, mesmo com script embutido
kbash run meu-script.kbash                  # abre a interface com o script
kbash run meu-script.kbash --headless --yes # roda no terminal, aceitando os padrões
kbash check meu-script.kbash                # valida e mostra erros e avisos com linha
kbash plan meu-script.kbash --select a,b --opt pasta=/tmp
```

- `--select` escolhe as etapas (com as dependências automáticas).
- `--opt chave=valor` define uma opção. Use o id da opção, não o rótulo.
- `plan --json` acrescenta o plano em JSON **ao final** da saída de texto.
- `check` sai com código `2` quando há erro de parse ou validação.

Códigos de saída de `run`: `0` sucesso, `1` falha em algum step, `2` erro de
parse ou validação, `130` cancelado.

## 7. Problemas comuns

- **"Nenhuma etapa declarada" ou "Este script não declara nenhuma etapa".** O
  script não tem `#@step`. Confira se as anotações estão no cabeçalho ou logo antes
  das funções.
- **O botão *Executar* não habilita.** Alguma opção obrigatória está vazia ou inválida
  (a mensagem aparece em vermelho no campo). Ou nenhuma etapa está marcada.
- **Diálogo de root não aparece.** Confira se o `pkexec` está instalado. Sem ele, a
  execução para com erro de pré-checagem, antes de qualquer etapa.
- **Um comando "não encontrado" dentro de uma etapa de root.** Etapas de root usam o
  `PATH` do sistema, não o seu. Comandos instalados só na sua pasta pessoal não existem
  para elas. Use o caminho completo ou instale o comando para todos.
- **"predefinições ignoradas".** O arquivo `kbash-config/<id>.json` está corrompido.
  O programa não apaga o arquivo: corrija ou apague-o à mão. Enquanto isso, *salvar*
  é recusado para não perder o conteúdo.
- **Um script novo não aparece na biblioteca.** A biblioteca lista só arquivos `.kbash`
  da pasta do programa, sem subpastas. Scripts `.sh` podem ser abertos pelo seletor.

## 8. Testar sem mexer no sistema

Para ver o que um script faria, use `kbash plan`. Ele mostra as etapas, as dependências
automáticas e os valores das opções, e não executa nada. Para validar o formato, use
`kbash check`.
