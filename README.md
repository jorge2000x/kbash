# kbash (BashRT)

Runtime que executa scripts bash anotados com uma interface gráfica
(Qt 6 / QML / Kirigami). Um script comum vira um formulário com opções
tipadas, etapas marcáveis e log ao vivo, sem reescrever a lógica.

- `SPEC.md`: formato das anotações `#@...` e comportamento do runtime.
- `docs/PORTAR.md`: guia para transformar um script bash existente.
- `examples/all-options.sh`: exemplo com todos os tipos de opção.

Uso rápido:

    rt check examples/all-options.sh
    rt run examples/all-options.sh          # abre a GUI
    rt run --headless --yes examples/all-options.sh
    rt home                                  # tela inicial com seletor de arquivo

Testes: `pytest` (com `dbus-run-session` para os testes de portal).
