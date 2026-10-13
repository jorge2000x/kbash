# Spike — empacotar o Kirigami dentro do bundle (SPEC.md §10.1, Fase 4)

**Pergunta:** dá para levar o módulo QML do Kirigami e as suas bibliotecas junto
com o bundle do BashRT, de forma que a interface KDE funcione numa máquina que não
tem Kirigami instalado?

**Resposta curta:** dá, e o custo é pequeno — mas **não é o caminho que escolhemos**.
Sem o Kirigami no sistema o runtime **erra alto com diagnóstico** (§10.1: só existe
a implementação Kirigami, não há fachada alternativa).

## O que foi verificado nesta máquina

| Item | Resultado |
|---|---|
| `org.kde.kirigami` visível para o Qt do sistema | **Não** — o único Kirigami instalado está dentro do runtime Flatpak `org.kde.Platform` 6.10, não exportado para o host |
| Prova de conceitual via Flatpak | **Sim** — `.../files/lib/qml/org/kde/kirigami/` existe e é um módulo completo |
| Tamanho do módulo QML | **1,2 MB** (`controls` 528K, `forms` 168K, `dialogs` 76K, `layouts` 76K, `delegates` 64K, `platform` 24K) |
| Plugins nativos dentro do módulo | `libKirigamiplugin.so`, `libKirigamiControlsplugin.so`, `libKirigamiDelegatesplugin.so` |
| Dependências de `libKirigamiplugin.so` | **6 bibliotecas** e nenhuma é do KF6: `libKirigami.so.6`, `libKirigamiPlatform.so.6`, `libQt6Qml.so.6`, `libQt6Core.so.6`, `libstdc++`, `libc` (+ `libgomp`) |
| Consequência | basta copiar o diretório do módulo + `libKirigami*.so.6` e exportar `QML2_IMPORT_PATH` e `LD_LIBRARY_PATH` |

Ou seja: o Kirigami é **autocontido** em relação ao resto do KDE — não puxa
`libKF6*` para o plugin base. Isso torna o empacotamento viável.

## Como seria

```
meu-instalador/
├── runtime
├── payload/…
└── _internal/
    ├── qml/org/kde/kirigami/…      # copiado do sistema
    ├── lib/libKirigami.so.6
    ├── lib/libKirigamiPlatform.so.6
    └── bashrt-launcher             # script que exporta as variáveis
```

O launcher precisaria exportar, antes de exec do runtime:

```sh
QML2_IMPORT_PATH="$DIRETORIO/_internal/qml:${QML2_IMPORT_PATH:-}"
LD_LIBRARY_PATH="$DIRETORIO/_internal/lib:${LD_LIBRARY_PATH:-}"
export QML2_IMPORT_PATH LD_LIBRARY_PATH
exec "$DIRETORIO/runtime" "$@"
```

Com PyInstaller/Nuitka, o gancho equivalente é um pequeno `--runtime-hook` ou um
`launcher` shell ao lado do binário.

## Riscos

1. **Duas versões do Qt**: o `libQt6Qml.so.6` do sistema precisa ser ABI-compatível
   com o Qt embutido pelo empacotador. Se o PySide6/Nuitka levar o seu próprio Qt,
   o plugin do Kirigami pode falhar em tempo de carga. Solução: não embutir o Qt (usar o do
   sistema) ou usar AppImage, que já traz um Qt coerente.
2. **Plataforma**: `libKirigamiPlatform.so.6` é específico de plataforma
   (X11/Wayland). Um bundle de um só sistema não funciona igual no outro.
3. **Ícones**: Kirigami usa ícones do framework de ícones do sistema (Breeze). Num
   sistema sem ele, a interface fica com ícones genéricos.
4. **Licença**: Kirigami é LGPL; redistribuir o módulo no bundle é permitido, com as
   obligations de licença (oferecer o código-fonte do Kirigami) — o que pesa para
   um produto fechado.
5. **Manutenção**: uma cópia congelada do Kirigami diverge do sistema e não recebe
   correções visuais.

## Decisão

- **O runtime exige o Kirigami do sistema** — sem ele, erro alto com diagnóstico
  (§10.1: "sem o módulo `org.kde.kirigami` no sistema, o runtime erra alto").
  A checagem é um *probe* real em `gui/app.py:kirigami_available()`, que compila e
  instancia um `QtObject` que importa o Kirigami. Não existe fallback.
- **O bundle não embute o Kirigami na v1.** O item fica registrado em §15
  (questão aberta 7) para uma v1.1, junto com a alternativa mais limpa:
  **AppImage**, que já resolve `QML2_IMPORT_PATH` e o Qt de forma coerente.

> **Nota de correção (2026-10):** esta seção citava um "fallback QtQuick Controls"
> e um `select_implementation()` com *queda automática*. Nenhum dos dois existe mais
> — `AGENTS.md` e `SPEC.md` §10.1 decidiram que só há uma implementação. O texto
> antigo faria alguém bundlar Kirigami achando que ele é opcional; não é.

## Como testar a fachada do Kirigami

Sem Kirigami na máquina, a suíte cobre o que dá:

- `tests/test_gui.py::test_pages_only_use_facades` — as páginas não tocam em
  `QtQuick.Controls` diretamente, então a troca de fachada é transparente;
- `tests/test_gui.py::test_kirigami_facade_is_syntactically_valid` — todos os
  arquivos Kirigami compilam (o único erro aceito é a ausência do módulo);
- `tests/test_gui.py::test_main_window_loads` — a janela sobe com as fachadas.

> **Nota de correção (2026-10):** `test_implementations_have_the_same_api` e
> `test_forced_kirigami_falls_back_when_absent` foram removidos junto com a
> fachada alternativa — não há duas implementações para comparar, nem fallback
> para exercitar. `BASHRT_UI_KIT` também não existe mais: a seleção de
> implementação saiu do código. Para validar de verdade, num desktop KDE real:

```sh
rt run examples/setup-dev.sh
```
