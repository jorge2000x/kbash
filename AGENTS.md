# AGENTS.md — regras de desenvolvimento (base: SPEC.md)

Leia `SPEC.md` antes de qualquer tarefa e cite a seção que está implementando.

- Trabalhe **um passo por vez**. Não altere código fora do escopo pedido.
- `core/` **nunca importa Qt** (SPEC.md §3). É Python puro, testável com pytest sem display.
- Escreva testes junto com o código; rode `pytest` antes de dar a tarefa por concluída.
- Nunca use `shell=True`; monte argumentos como lista.
- Python ≥ 3.11, com type hints em todo código novo.
- `rt.sh` continua em bash puro, sem dependências externas.
- Se o spec estiver ambíguo ou errado, **pare e proponha a mudança no spec** em vez de improvisar.
- Commits pequenos, um por etapa funcional, com mensagem descrevendo a seção do spec atendida.
- O formato é **um arquivo bash + anotações `#@`**: nunca divida o script do
  usuário em zonas/arquivos; a lógica dele fica intacta, só a interação
  (`read` → `rt_*`) é adaptada.

## Convenções do repositório

- Comandos: `pytest` (testes), `kbash check <script.sh>` (validação, SPEC.md §4.6).
- Testes: `./.venv/bin/python -m pytest tests/ -q` com `PYTHONNOUSERSITE=1`
  (o `.venv` usa o PySide6 **da distro**, o único que carrega o Kirigami;
  sem isso cai no PySide6 do pip e o QML quebra). `QT_QPA_PLATFORM=offscreen`
  para rodar sem display.
- Entry points: `kbash` (`python -m kbash.main` em desenvolvimento; `kbash/__main__.py`
  passa pelo `main`, com a trava de interpretador).
- Erros de parse/validação são exceções com `arquivo:linha` (§4.6); a CLI
  imprime-os e devolve 2 (§12).
- Códigos de saída: `0` sucesso · `1` falha de step · `2` erro de
  parse/validação · `130` cancelado.
- Kirigami: use o PySide6 **da distro**, com `import org.kde.kirigami` **sem versão**
  (SPEC.md §10.1). O PySide6 do pip não carrega o Kirigami do sistema.
- Nem todo `Kirigami.X` existe: verificar cada tipo no runtime antes de usar
  (verificados: ApplicationWindow, Page, PasswordField, Dialog, Icon, Heading,
  InlineMessage, Action, OverlaySheet; botões/campos/combos/switches/barra são
  QtQuick.Controls ou retângulos próprios).
