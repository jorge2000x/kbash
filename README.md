# kbash

Runtime que executa scripts bash anotados com uma interface gráfica
(Qt 6 / QML / Kirigami). Um script comum vira um formulário com opções
tipadas, etapas marcáveis e log ao vivo, sem reescrever a lógica.

- `docs/USO.md`: como abrir, configurar, executar e ler o resultado de um script.
- `docs/AUTHORING.md`: como escrever um script `.kbash` do zero (cabeçalho, opções, steps, helpers `rt_*`, root).
- `docs/PORTAR.md`: guia para transformar um script bash existente.
- `SPEC.md`: formato das anotações `#@...` e comportamento do runtime.
- `examples/`: exemplos prontos (`all-options.sh`, `setup-dev.sh`, `sober-optimizer.sh`, `fedora-superpoderoso.kbash`).

Uso rápido:

    kbash check examples/all-options.sh
    kbash run examples/all-options.sh          # abre a GUI
    kbash run --headless --yes examples/all-options.sh
    kbash home                                  # tela inicial com seletor de arquivo

Testes: `pytest` (com `dbus-run-session` para os testes de portal).
