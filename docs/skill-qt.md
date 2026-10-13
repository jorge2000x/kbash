# skill-qt.md — PySide6 + QML + Kirigami sem quebrar

Guia operacional para manter a GUI do `rt` (e qualquer GUI PySide6/Kirigami
parecida) **correta, bonita e consistente**. Cada regra aqui existe porque a
regressão correspondente já aconteceu neste repositório ou foi verificada em
runtime nesta máquina.

Ambiente de referência: **Qt 6.11.1**, Kirigami do sistema (KF6), PySide6 da
distro, Python ≥ 3.11, rodando Linux/Fedora.

> Ao mudar QML, rode sempre:
> `PYTHONNOUSERSITE=1 QT_QPA_PLATFORM=offscreen ./.venv/bin/python -m pytest tests/ -q`
> (`PYTHONNOUSERSITE=1` é obrigatório — ver §1).

---

## 1. Preflight: o que quebra antes de qualquer linha de QML

Três falhas matam a janela em silêncio. Todas são de ambiente, não de código.

### 1.1 Use o PySide6 da distro, nunca o do pip

O PySide6 do pip **não carrega o Kirigami do sistema** — o import falha e a
janela não abre. E o `.venv` do projeto usa o da distro, o único que enxerga o
Kirigami.

```bash
# o culpado usual: site do usuário aparecendo antes do da distro
./.venv/bin/python -c "import PySide6; print(PySide6.__file__)"
# precisa sair de /usr/lib/python3.*/site-packages  (NÃO de ~/.local/lib/...)

# rode SEM o site do usuário
PYTHONNOUSERSITE=1 ./.venv/bin/python -c "import PySide6; print(PySide6.__file__)"
```

`PYTHONNOUSERSITE=1` é o interruptor. `pyproject.toml` declara
`dependencies = []` e o GUI fica em `optional-dependencies` justamente porque o
PySide6 vem do sistema, não do pip.

### 1.2 Importe o Kirigami **sem versão**

```qml
import org.kde.kirigami as Kirigami   // ✅
import org.kde.kirigami 3.0 as Kirigami   // ❌ não existe nesta build
```

`3.0` nunca existiu nas builds testadas (KF6 6.30 expõe até `2.20`). Manter
`KIRIGAMI_VERSION = ""` e versionar é erro de cópia de tutorial.

### 1.3 Style Breeze, e probe **antes** de criar o Bridge

```python
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", _style())  # "org.kde.breeze"
```

O Breeze é o que faz o app parecer nativo. E o estilo precisa estar definido
**antes** de o primeiro componente ser instanciado — `setdefault` depois do
engine já vivo não recolore nada.

O `kirigami_available()` faz um *probe de verdade*: compila e instancia um
`QtObject` que importa o Kirigami, e roda **antes** do `Bridge` (que já teria
ligado timer e thread). Sem o módulo, o runtime erra alto com diagnóstico, em
vez de tela branca. Exige `QGuiApplication` viva — com `QCoreApplication` o
processo aborta.

---

## 2. Arquitetura: a regra das fachadas

**Nenhuma tela toca um controle do Qt diretamente.** As quatro telas usam só
tipos do módulo `BashRT`; botões, campos, combos, switches, cartões, diálogos e
selos são as fachadas. Isso existe para trocar o toolkit inteiro sem reescrever
as telas.

```
qml/
├── main.qml                      ← ApplicationWindow, StackLayout, toast
├── pages/                        ← módulo "pages" (qmldir obrigatório)
│   ├── qmldir
│   └── WelcomePage / SelectPage / RunPage / ResultPage
└── kirigami/BashRT/              ← módulo "BashRT" — as fachadas
    ├── qmldir
    └── App*.qml, StepRow, StepBadge, OptionField, LogPanel, LogDrawer…
```

Três regras de módulo:

1. **Tudo que o QML instancia por nome precisa de `qmldir`.** `main.qml`
   instancia `WelcomePage {}` etc. pelo nome; um arquivo solto no import path
   não é encontrado. Por isso `pages/qmldir` existe.
2. **Um import path por módulo.** `engine.addImportPath(qml/kirigami)` para
   `BashRT`, `engine.addImportPath(qml/)` para `pages`. `qmldir` deve ficar
   *dentro* da pasta do módulo.
3. **Toda fachada declarada no `qmldir` precisa existir como arquivo** — e ser
   instanciável. Erro de import faltando (usar `Layout.*` sem importar
   `QtQuick.Layouts`) só aparece em runtime; por isso o smoke test cria cada
   tipo de verdade (`test_every_facade_instantiates`).

### 2.1 O que é fachada e o que é tela

| | Pode usar |
|---|---|
| **Tela** (`pages/`) | `App*`, `StepRow`, `OptionField`, `LogPanel`, `Label`, `RowLayout`, `Flow`, `Item` |
| **Fachada** (`BashRT/`) | `Kirigami.*` quando existe; `QtQuick.Controls` para o resto |

Exceção consciente: `ScrollView` + `TextArea` dentro de uma fachada é legítimo
(a fachada existe justamente para esconder o controle). O que é proibido é a
**tela** desenhar o controle.

Teste que garante isso: `test_pages_only_use_facades` — vale a pena
**estender a lista de proibidos** quando um controle crudo escapa. Hoje ele
proíbe `Button, TextField, CheckBox, ComboBox, Switch, ProgressBar, Dialog,
Page, ToolButton, ApplicationWindow, AbstractCard`; `TextEdit` e `ScrollView`
não estão na lista (ver achado A2).

---

## 3. Contexto Python ↔ QML

### 3.1 O que é property, o que é atributo

Atributo Python puro é **invisível** para o QML. Tudo que o QML lê tem que ser
`Property`:

```python
steps = Property(QObject, lambda self: self._steps_model, constant=True)
```

Sem o `Property`, a view lia 0 linhas e o sintoma é "o modelo não aparece" —
não um erro, uma lista vazia. Quando o objeto nunca é trocado (só o conteúdo
muda, via sinais do próprio modelo), use `constant=True`.

`Property` precisa de `notify=` com o sinal correspondente. Property sem `notify`
é property morta: o QML avalia uma vez e nunca mais.

### 3.2 `@Slot` para o que o QML chama

Tudo que o QML invoca precisa ser `@Slot`, com os tipos declarados:

```python
@Slot(str, bool, result=bool)
def setStepChecked(self, step_id: str, checked: bool) -> bool: ...

@Slot(str, "QVariant")
def answer(self, request_id: str, value: Any) -> None: ...
```

`"QVariant"` é obrigatório quando o tipo varia (uma resposta de prompt é
`str`, `bool` ou `list`). Sem ele o QML passa `QVariant` e o Python recebe
`None`.

`result=` declara o retorno. `return` numa função sem `result=` é silenciosamente
ignorado pelo QML.

### 3.3 Threading: a regra que o Qt impõe

**Nenhum `QAbstractListModel` é tocado de fora da thread da GUI.**

O padrão do projeto:

```
thread de execução (Executor)
    └─ apenas queue.put(evento)        ← nunca toca em modelo/propriedade
thread da GUI
    └─ QTimer(50ms).timeout → _drain() ← aplica tudo aqui
```

Por quê: `QAbstractItemModel` emite `dataChanged` para a view; emitir de outra
thread corrompe a view e só falha "às vezes". O timer de 50 ms agrupa o trabalho
— é o que mantém a GUI responsiva com saída volumosa de log.

`LogModel` é a exceção controlada: `push()` pode vir de qualquer thread (tem
`Lock` e só escreve numa lista de entrada); `flush()` só na thread da GUI e é o
único que emite `begin/EndInsertRows`.

### 3.4 Slots Python **não** podem emitir o sinal que os reavalia

Este é o loop mais sutil do arquivo, e ele é **real**:

```python
@Slot(result=str)
def logText(self) -> str:
    self._log_model.flush()
    self.logCountChanged.emit()   # ← reavalia qualquer binding que dependa disto
    return self._log_model.text()
```

Se o QML fizer `text: bridge.logText()`, o binding depende de `logCount` (por
causa do `emit`), e o `emit` acontece *durante* a leitura da propriedade. O Qt
detecta e quebra o loop com aviso — mas o conteúdo fica errado e o aviso passa
despercebido.

**Regra: binding QML lê `Property`; operação com efeito colateral vai em
`onXxxChanged` explícito, não em binding.** Para texto grande, prefira deixar o
modelo cuidar (ver achado A2).

### 3.5 `setParent` nos objetos do context property

O context property guarda só o ponteiro C++. Sem `parent`, o objeto morre no
momento em que o Python solta a referência — e em Python, referênciascollect
não avisam. Sempre:

```python
bridge.setParent(engine)
theme.setParent(engine)
```

O mesmo vale para o `QQmlComponent` que criou o objeto: guarde-o em uma
variável de módulo (`_THEME_COMPONENTS`), senão o `theme` fica órfão.

---

## 4. Layout: as regras que o Layout não te conta

Esta seção é a que mais dói. Todas as regras abaixo corrigiram um bug real.

### 4.1 A `ApplicationWindow` não põe Layout nos filhos diretos

Sem uma `ColumnLayout` com `anchors.fill: parent` em volta do conteúdo, o
`StackLayout` das telas fica **0×0** e as telas somem. Não há erro nenhum.

### 4.2 A página não usa o `pageStack` do Kirigami

`Kirigami.ApplicationWindow` tem `pageStack` (`PageRow`), mas ele é um
`ColumnView` que em janela larga (`pageStack.wideMode`, ligado por padrão)
deixa a tela **anterior espremida ao lado da atual** (360/580 px numa janela de
940) e não assenta sozinho. Fluxo linear → `StackLayout` dirigido por
`bridge.page`.

E as quatro telas são instanciadas **uma única vez**: um `Loader` por página
destruiria e recriaria a tela a cada navegação, levando junto o scroll da lista
de etapas, o auto-scroll do log e o diálogo aberto.

### 4.3 A coluna da página precisa de largura **explícita**

A tela inteira colapsava para ~371 px numa janela de 940 px, com o texto
cortado. Três coisas causam isso, e qualquer uma volta a quebrar:

- **`ScrollView` como `contentItem` de uma `Kirigami.Page`.** A Page é um
  `Flickable`; o ScrollView fica com **largura 0**. A `AppPage` é um `Item`
  comum com o `ScrollView` em `anchors.fill`.
- **`Layout.alignment: Qt.AlignHCenter` na coluna** — faz o Layout dimensionar
  pelo *conteúdo*, não pela janela. Centralize com `x` calculado.
- **`implicitWidth` da página atado ao ScrollView** — circular (a página mede o
  filho, o filho mede a página) e o Layout fica com 0.

O que funciona (e é o que `AppPage.qml` faz):

```qml
Item { id: pageBody; width: scroll.availableWidth
      ColumnLayout {
          width: Math.min(pageBody.width - 2 * root.contentMargin, root.maxContentWidth)
          x: Math.max(root.contentMargin, (pageBody.width - width) / 2)   // centraliza
      }
}
```

Linha de leitura: `maxContentWidth: 820`. Acima disso o texto fica longo demais.

### 4.4 Layout **ou** anchors, nunca os dois no mesmo item

O gerenciador de geometria e os anchors se brigam e tudo colapsa na largura
mínima. Regras:

- filho de `ColumnLayout`/`RowLayout` → `Layout.*`, **sem** `anchors`
- filho de `ScrollView`/`Rectangle` que é `contentItem` → `anchors.fill`
- `anchors.fill` em item que também é filho de um Layout → **proibido**

O sintoma é o mesmo nos dois casos: o item fica com a largura mínima.

### 4.5 Altura: deixe o pai medir

Não meça a altura à mão quando o pai sabe medir. `AppCard` usa
`contentItem` + `padding` (o mecanismo do próprio `AbstractCard`) e as listas
usam `Layout.fillHeight` com `Layout.minimumHeight` de rede. Números fixos
(`Layout.preferredHeight: 200` vs `300` vs `Math.min(contentHeight, 400)`) são
a forma mais rápida de a consistência visual quebrar entre telas — ver achado A4.

### 4.6 `ColumnLayout` não tem `topPadding`/`leftPadding`

`QtQuick.Layouts` não tem essas propriedades. Atribuir é **erro de compilação**
("Cannot assign to non-existent property") e a janela inteira deixa de carregar.
Margem de diálogo/Item vem do `padding` do `Control` (`AppDialog` faz
`padding: Kirigami.Units.largeSpacing`), não do Layout.

### 4.7 `DialogButtonBox` reescreve o `highlighted` dos filhos

Ele reescreve o destaque conforme o papel de cada botão, e o botão de *default*
do diálogo de Sim/Não ficava sem destaque. Use `RowLayout` + `AppButton`
manuais (é o que `AppDialog` faz).

---

## 5. Cor: a paleta vem do Kirigami, sempre

**Regra dura: nada de cor fixa** (`#ffffff`, `#000000`, `#3498db`). O que é
legível no tema claro é ilegível no escuro, e o app segue o tema do sistema.

### 5.1 Papéis que existem no `Kirigami.Theme` (verificados)

`textColor` · `backgroundColor` · `alternateBackgroundColor` ·
`disabledTextColor` · `linkColor` · `visitedLinkColor` · `highlightColor` ·
`highlightedTextColor` · `positiveTextColor` · `neutralTextColor` ·
`negativeTextColor` · `hoverColor` · `focusColor` · `defaultFont`

### 5.2 Papéis que **não** existem — não usar

`midColor` · `frameColor` · `placeholderTextColor` · `inactiveTextColor` ·
`buttonBackgroundColor`

Atribuir qualquer um deles vira `Unable to assign [undefined]`. Saiam de memória
de tutorials, não do código.

> `luminance` **não existe** em `color` do QML (dá `undefined`, então `isDark`
> era sempre `false`). O indicador confiável de esquema é a **luminosidade do
> fundo**: as cores de texto do Kirigami são escuras no claro e claras no escuro.

### 5.3 Cores desenhadas à mão saem de funções, não de literais

Para toast, selo, painel de log, borda — misture sobre a cor do texto:

```qml
function faint(base)  { return Qt.rgba(base.r, base.g, base.b, 0.12) }
function hairline(base){ return Qt.rgba(base.r, base.g, base.b, 0.45) }
```

Funciona nos dois esquemas, ao contrário de um cinza fixo (some no escuro).

### 5.4 O toast: fundo e texto em pontas opostas

```qml
color: theme.surface                              // fundo chapado
border.color: theme.hairline(theme.onSurface(toast.level))
color(texto): theme.onSurface(toast.level)        // a cor do nível
```

Pintar o fundo com a cor do nível e o texto por cima deixava branco ilegível
no tema escuro — a regressão de contraste já corrigida. `test_toast_never_paints_fixed_white_on_a_saturated_background`
trava isso.

### 5.5 Tema claro/escuro segue o sistema; não offers alternância

O Kirigami desta máquina (KF6 6.30, Qt 6.11) **não expõe `Theme.colorScheme`**
e **ignora** `QGuiApplication.styleHints().setColorScheme()` — as cores do
`Kirigami.Theme` não mudam. Um botão que escrevesse um `forcedScheme` próprio
mudaria só o rótulo dele, mentindo para o usuário. Para oferecer a escolha é
preciso um Kirigami com `Theme.colorScheme` ou uma paleta própria (o que abriria
mão de casar com o Breeze).

---

## 6. Controles: o que o Kirigami tem (e o que não tem)

Verificados em runtime nesta máquina. **Verificar no runtime antes de usar
qualquer `Kirigami.X` novo** — metade dos nomes que o povo usa não existe.

### 6.1 Existem no Kirigami

`ApplicationWindow` · `Page` · `PasswordField` · `Dialog` · `Icon` ·
`Heading` · `InlineMessage` · `Action` · `OverlaySheet` · `OverlayDrawer` ·
`AbstractCard` · `Badge` · `PlaceholderMessage` · `Separator` · `Theme` ·
`Units`

### 6.2 **Não** existem — usar QtQuick.Controls (o Breeze renderiza nativo)

`TextField` · `CheckBox` · `Switch` · `ComboBox` · `Slider` · `Button` ·
`ToolButton` · `ProgressBar` · `AbstractPageHeader` · `AbstractCard.contentColumn`

Exceções com desenho **justificado** no repositório:

- `AppProgressBar` — dois `Rectangle`. Motivo: o `ProgressBar` do QQC no Breeze
  6.7.5 cospe 16 `TypeError` por barra criada.
- `AppHeader` — a barra da janela, porque o `pageStack` está vazio (§4.2).
- `toast` no `main.qml` — não existe toast nativo neste Kirigami.

### 6.3 Sem `background`/`contentItem` próprios em controle de entrada

O Breeze renderiza nativo. Se você escreve `background:` ou `contentItem:` num
`Button`/`TextField`, deixa de parecer nativo e ainda quebra a acessibilidade.
A regra vale para `AppButton`, `AppTextField`, `AppSwitch`, `AppComboBox`,
`AppCheckBox` — que são `QtQuick.Controls` puro, com zero customização de
pintura.

`AppCard` e `AppDialog` **podem** ter `contentItem`: são o mecanismo oficial
dessas classes (o `AbstractCard` mede o conteúdo e dá o `padding`).

### 6.4 `variant` do botão

`default | primary | danger | flat`. O Breeze não tem papel "destrutivo", então
`danger` reusa o destaque de `primary` — o que o run traz de atenção. O **rótulo**
é que diz o que o botão faz.

### 6.5 Ícone: nome de tema ou arquivo, nunca os dois

`AppIcon` faz a troca (`source` tem precedência sobre `name`). `#@icon` do
script pode ser um nome (`utilities-log-viewer`) ou um caminho em `assets/` — o
Bridge resolve e expõe `scriptIcon` / `scriptIconFile` separados.

`window.icon` **não existe** no Kirigami 6.10: atribuir `window.icon.source`
dá `TypeError: Value is undefined` no startup. O ícone da janela vem de
`app.setWindowIcon()` no Python.

---

## 7. Binding: as quatro armadilhas

### 7.1 Nunca amarre o `text` do campo direto ao valor do modelo

```qml
// ❌ cada tecla chama setOption, o modelo devolve value de volta,
//    e o campo apaga o que está sendo digitado
TextField { text: root.value; onTextEdited: bridge.setOption(root.optId, text) }
```

O sintoma é pior num campo de senha: o modelo sempre devolve vazio (por
segurança), então **o campo apaga a cada tecla**.

O padrão certo é sincronia imperativa que respeita o foco:

```qml
function syncField(field) {
    if (!field.activeFocus)
        field.text = root.value ?? ""
}
TextField {
    id: textField
    Component.onCompleted: root.syncField(textField)
    Connections {
        target: root
        function onValueChanged() { root.syncField(textField) }
    }
}
```

O mesmo vale, com a condição própria de cada controle:

- **slider** → `if (!slider.pressed)`
- **combo** → `if (combo.popupVisible) return`; e valor vazio precisa ser
  explícito (`currentIndex = -1`), porque o ComboBox normaliza `-1` para `0`
  ao medir
- **`required property` no delegate nunca** — ver §7.2

**No handler, use o `id` explícito.** `function onValueChanged() { syncField(field) }`
não resolve `field` e a sincronia falha em silêncio.

### 7.2 Delegate: `required` em propriedade do modelo nasce vazio

`required` é avaliado **antes** do contexto do modelo anexar, e o delegate
nasce vazio **em silêncio** — sem erro, sem lista.

```qml
// ❌ lê-se model.<papel> direto do contexto
delegate: Item { required property string text; text: model.text }

// ✅
delegate: Item { property string line: model.text }
```

Exceção: `LogPanel.qml` **usa** `required` e funciona, porque o modelo expõe
`roleNames()` e o `required` casa com os roles. É a exceção que prova a regra —
não o padrão. Padronize num estilo só, senão o próximo a copiar pega o
exemplo errado (achado A3).

### 7.3 `model.<role>` vs `modelData`

`QAbstractListModel` com `roleNames()` → `model.stepId`, `model.title`.
Array/JS literal → `modelData`. Misturar os dois no mesmo arquivo é o jeito
mais rápido de um delegate aparecer vazio.

### 7.4 O Qt normaliza valores na volta — não asserte a string crua

`inputMask` é o caso registrado: o Qt **acrescenta** o sufixo `"; "` ao reler.

```qml
inputMask: "0000-00-00"
```
```python
field.property("inputMask")   # → '0000-00-00; '   (não '0000-00-00')
```

Um `TextField` puro, sem nenhum alias, já devolve assim — é o `parseMask` do Qt,
não bug do app. Asseerte o que importa:

```python
assert visible[0].property("inputMask").startswith("0000-00-00")
```

Mesma família de Surpresas: `className()` de tipos que viraram declarativos
(§9.2).

---

## 8. Acessibilidade e consistência

- Todo texto visível passa por `qsTr`.
- `focusPolicy: Qt.StrongFocus` em botão e checkbox (o padrão do QQC é
  `TabFocus`, que ignora setas).
- Diálogo precisa de algo focado: sem foco inicial, só o mouse responde. Enter
  confirma. `PromptDialog` faz `forceActiveFocus()` por kind.
- Todo botão é um `AppButton` com `variant` — não misture "default" e
  "primary" na mesma tela sem motivo.
- Diálogo de Sim/Não **precisa do Não**. "Não" responde `false` (o script segue
  o caminho normal) e é distinto de *Cancelar*, que responde a sentinela de
  cancelamento. Um diálogo de Sim/Não sem o *Não* obriga o usuário a responder
  "não" cancelando a execução inteira.
- `closePolicy: Popup.NoAutoClose` em diálogo de prompt: sem isso, Esc/ clique
  fora fecha sem responder e o script fica esperando até o timeout de 1 h.
  O único botão de fechar do Kirigami.Dialog também não passa por `rejected` —
  precisa de `onClosed` respondendo também.
- Ícone sem nome textual precisa de `ToolTip`.
- Respeite a fonte do sistema: `theme.smallFont` deriva de
  `Kirigami.Theme.defaultFont.pixelSize`. Fonte fixa (12) ignora escala e
  preferência do usuário.

---

## 9. Testes: onde a GUI te engana

Roda com `QT_QPA_PLATFORM=offscreen`. Quatro armadilhas específicas:

### 9.1 "File name case mismatch"

Carregar o **mesmo componente** a partir de arquivos diferentes com conteúdo
idêntico faz o Qt reclamar. O smoke test que instancia todas as fachadas
escreve **um único arquivo** com todas elas dentro (§10).

### 9.2 `className()` de tipos que o Qt redeclara em QML

`FileDialog`/`FolderDialog` de `QtQuick.Dialogs` **não** são mais
`QQuickFileDialog` no Qt 6.11 — o tipo é declarativo e o que aparece na árvore
é o `QFileDialogOptions`:

```python
# ❌ não acha nada no Qt 6.11
item.metaObject().className() == "QQuickFileDialog"
# ✅
item.metaObject().className() == "QFileDialogOptions"
```

Antes de assertar sobre `className`, **liste os filhos e veja como eles se
chamam de verdade**. Um teste que passa com `className` errado está testando
nada: ele só falha se a lista por acaso vier vazia.

### 9.3 Popup sem janela lê `visible` sempre `false`

Testar `Dialog`/`OverlayDrawer` instanciando o componente isolado não funciona —
sem janela, `visible` é sempre falso. Emita o sinal de abertura com uma janela
real (`create_engine` + `bridge.promptRequested.emit(...)`) e espere a condição
com `spin()`.

### 9.4 Os testes rodam com `Basic`, a produção com `Breeze`

`test_gui.py` faz `os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")`.
Os testes **não exercitam o estilo de produção**. Uma regressão que só aparece
com o Breeze (o `ProgressBar` que cuspia 16 `TypeError`, por exemplo) passa
verde. Vale um smoke com Breeze:

```python
os.environ["QT_QUICK_CONTROLS_STYLE"] = "org.kde.breeze"
```

### 9.5 `spin()`, nunca `sleep()`

```python
def spin(app, predicate, timeout=60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return False
```

### 9.6 Instancie toda fachada declarada

Erro de import faltando só aparece em runtime. `test_every_facade_instantiates`
lê o `qmldir`, monta um QML com **todos** os tipos e exige que
`component.create()` devolve algo. É o teste que pega "esqueci o
`import QtQuick.Layouts`".

---

## 10. Checklist de Pull Request

**Ambiente**
- [ ] `PYTHONNOUSERSITE=1` em toda invocação de Python/Qt
- [ ] `import org.kde.kirigami` **sem versão**
- [ ] `QT_QUICK_CONTROLS_STYLE=org.kde.breeze` antes de instanciar componente
- [ ] `import org.kde.kirigami` segue **sem versão** também nos exemplos novos

**Fachadas**
- [ ] Nenhum controle cru em `pages/` (só `App*`, `StepRow`, `OptionField`, `LogPanel`)
- [ ] Tipo novo declarado no `qmldir` **e** com arquivo
- [ ] `Kirigami.X` novo verificado no runtime antes de usar
- [ ] Nada de `background`/`contentItem` em botão/campo de entrada
- [ ] Nenhum literal de cor novo

**Layout**
- [ ] `ColumnLayout` com `anchors.fill: parent` em volta do conteúdo da janela
- [ ] `StackLayout`, não `pageStack`
- [ ] Nenhum item com `anchors.*` **e** `Layout.*`
- [ ] Nenhum `Layout.alignment: Qt.AlignHCenter` em coluna de conteúdo
- [ ] Nenhum `implicitWidth` atado ao próprio filho
- [ ] Altura vem do pai, não de número fixo

**Binding**
- [ ] Campo sincronizado por imperativo, respeitando foco
- [ ] `id` explícito dentro dos `Connections`
- [ ] Delegate sem `required` em propriedade do modelo
- [ ] Nenhum `@Slot` com efeito colateral lido dentro de binding

**Python**
- [ ] Tudo que o QML lê é `Property` com `notify`
- [ ] Tudo que o QML chama é `@Slot` com tipos e `result=`
- [ ] Modelo só é tocado na thread da GUI
- [ ] `setParent(engine)` em todo context property

**Testes**
- [ ] `pytest` verde com `PYTHONNOUSERSITE=1 QT_QPA_PLATFORM=offscreen`
- [ ] Fachada nova entra no smoke de instanciação
- [ ] Asserção sobre valor **normalizado** do Qt (`inputMask` ⇒ `startswith`)
- [ ] `className()` confirmado listando os filhos, não de memória

---

## Apêndice A — Achados na base atual

Levantados ao auditar a integração PySide/QML. **Não corrigidos** — a base
estava sendo alterada por outro agente. Ordenados por gravidade.

### A1 — 11 `console.trace` em `OptionField.qml` · **alto** (performance/ruído)

Linhas 100, 115, 128, 144, 157, 176, 184, 198, 217, 240, 257:

```qml
onTextEdited: { console.trace('SETOPT:' + root.optId); bridge.setOption(root.optId, text) }
```

Vestígio de depuração em produção. Dispara **a cada tecla**, a cada passo do
slider (`onMoved`) e a cada clique — em `textField`, `dateField`, `timeField`,
`textArea`, `passwordField`, `folderDialog`, `fileDialog`, `sliderField`,
`AppSwitch`, `AppComboBox` e no `multi`. A remoção é o caso único do arquivo:
as linhas viram `onTextEdited: bridge.setOption(root.optId, text)`.

### A2 — `ResultPage.qml:74-102` desenha o log à mão, contra a fachada · **alto**

O diálogo "Ver log" monta `ScrollView` + `TextEdit` crus, ignorando o
`LogPanel` que já existe (com auto-scroll, *Copiar* e paleta de log). Duplica
código e entrega uma visual diferente da gaveta inferior.

Pior: `TextEdit { text: bridge.logText() }` (§3.4) é um **binding com efeito
colateral** — `logText()` emite `logCountChanged` durante a leitura, e o mesmo
arquivo usa `bridge.logCount` em `enabled:`. Loop de binding.

Correção: trocar o `ScrollView`/`TextEdit` por `LogPanel` com
`onCopyRequested: bridge.copyToClipboard(bridge.logText())`. O `LogPanel` lê o
modelo `bridge.log` e não tem o problema. E acrescentar `TextEdit`/`ScrollView`
à lista de proibidos de `test_pages_only_use_facades`.

### A3 — `required property` em delegate só no `LogPanel` · **médio**

`LogPanel.qml:45-49` usa `required property string text/stream/level/stepId`,
enquanto `SelectPage`/`RunPage`/`ResultPage` usam `model.<role>` (§7.2). Funciona
nos dois casos porque o modelo expõe `roleNames()`, mas são dois estilos para a
mesma coisa — e o próximo a copiar pega o exemplo errado. Padronizar em
`model.<role>`.

### A4 — Alturas de lista inconsistentes entre telas · **médio**

`SelectPage` usa `Math.min(contentHeight, 400)`; `RunPage` fixa
`Layout.preferredHeight: 200`; `ResultPage` fixa `300`. Três números mágicos
para "a lista de etapas", que é o mesmo componente nas três telas. Um token
comum (ou `Layout.fillHeight` com `minimumHeight`) deixa as três com a mesma
altura visual.

### A5 — `AppPage.heading` é propriedade morta · **médio**

`AppPage.qml:17` declara `property string heading`, e **nada a renderiza** — o
único `Label` do corpo usa `root.subheading` (linha 54). As quatro telas
atribuem `heading` (`bridge.scriptName`, `qsTr("Executando")`, o veredito
calculado de `ResultPage`) e nada aparece. Ou renderiza, ou remove.

Como está, o resultado perde o título: quem vê a tela de Resultado não lê
"Falhou" em lugar nenhum da página (a barra da janela continua com o nome do
script).

### A6 — `AppTextField` redeclara com alias propriedades herdadas · **baixo**

```qml
property alias validator: control.validator
property alias inputMask: control.inputMask
```

`TextField` **já declara** `validator` e `inputMask`. O alias aponta a
propriedade do próprio `control`, ou seja, para si mesmo. Funciona (o QML
resolve o alvo contra o tipo base), mas é auto-referencial e não compra nada.
Apagar as duas linhas deixa o comportamento idêntico e sem o risco.

### A7 — Import não usado em `main.qml` · **baixo**

`import QtQuick.Dialogs` (linha 11) — o `main.qml` não usa nenhum `FileDialog`
nem `ColorDialog`. O `ResultPage` e o `PromptDialog` é que usam.

### A8 — `AppSwitch._defaultLabel` muta `text` no `onCompleted` · **baixo**

```qml
property bool _defaultLabel: text === ""
Component.onCompleted: if (_defaultLabel) text = checked ? qsTr("Sim") : qsTr("Não")
onToggled: if (_defaultLabel) text = checked ? qsTr("Sim") : qsTr("Não")
```

Escrever `text` de dentro de um handler quebra o binding de quem chamou, e o
`_defaultLabel` é avaliado uma vez só. Uma `property string label` (com `text:
root.label !== "" ? root.label : (checked ? ... )`) resolve sem mutação.

### A9 — `theme`/`bridge` são context properties, não singleton · **débito estrutural**

Todo QML referencia `theme` e `bridge` como globais, sem `import` nenhum.
Consequências: erro de digitação só falha em runtime; nenhum arquivo QML é
carregável isolado; a checagem estática do QML não enxerga nada disso.

O padrão correto é `pragma Singleton` declarado no `qmldir`:

```
singleton Theme 1.0 Theme.qml
```
```qml
import BashRT
// Theme.smallFont, sem context property
```

Custo: `_create_theme`/`setContextProperty` saem de `app.py`, e `bridge` ainda
precisa ser registrado (é um objeto Python por sessão — nesse caso o context
property continua sendo o certo, com um `QmlElement`/registro se Growth). Vale
para o `theme`; **não** vale fazer agora sem medir: toca toda fachada.

### A10 — Dois testes falham (base em workset) · **médio**

`pytest` hoje: **237 passam, 2 falham** (144 s). Ambos por asserção
especificada demais, **não** por defeito do app — confirmado em runtime:

1. `test_option_file_renders_picker_with_filters` — procura
   `className() == "QQuickFileDialog"`, que não existe no Qt 6.11 (§9.2).
   Achei `QFileDialogOptions` com `title == "Escolher arquivo"` e
   `nameFilters == ['*.png']`: o `FileDialog` está correto.
2. `test_prompt_new_kinds_render_their_fields` — assere
   `inputMask == "0000-00-00"`, mas o Qt devolve `"0000-00-00; "` (§7.4). Um
   `TextField` puro, sem alias nenhum, devolve igual: é o `parseMask` do Qt.
   O `dateField` aparece e recebe a máscara certa.

Correção: trocar por `startswith()` e por `QFileDialogOptions`.
