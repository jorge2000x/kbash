# Breeze no bundle — como funciona e o que foi corrigido

**Status: funciona.** O AppImage embute o estilo QQC2 Breeze e escolhe ele
sozinho. Sem o módulo, cai para `Basic` sem quebrar.

## Como o estilo é escolhido

- O nome do estilo é o **URI do módulo QML**: `org.kde.breeze`. Não é `Breeze`.
- `gui/app.py:_style()` escolhe `org.kde.breeze` se o `qmldir` do módulo
  estiver num caminho de import; senão, `Basic`. `QT_QUICK_CONTROLS_STYLE`,
  se definido, sempre vence.
- O AppRun **não** fixa mais estilo.

## O que o bundle embute (Ubuntu 26.04 "resolute")

Lista completa em `tools/breeze-debs.txt` (30 pacotes). O conjunto mínimo,
medido com `ldd`/`readelf`:

| peça | por quê |
|---|---|
| `org/kde/breeze/` (QML + `libBreezeStyle.so` + `impl/libBreezeImpl.so`) | o estilo em si; só precisa de Qt |
| `org/kde/kirigami/` | o estilo importa `org.kde.kirigami` |
| `org/kde/guiaddons/` + `libKF6GuiAddons` | o estilo importa `org.kde.guiaddons` |
| `libKF6*` (ColorScheme, ConfigCore, IconThemes, I18n, Archive…) | cadeia do GuiAddons e do Kirigami |
| `libwayland-client` ≥ 1.23 | `libKF6GuiAddons` usa `wl_display_create_queue_with_name` |

**E o plugin de plataforma do Kirigami** (`kf6/kirigami/platform/org.kde.breeze.so`),
que dá a `Kirigami.Theme` as cores do Breeze (e as do KDE do usuário, quando
houver) e a fonte base. O estilo QQC2 funciona sem ele, mas o Kirigami cai
num fallback claro e pequeno. Medido no bundle, com e sem o plugin:

| | com plugin | sem plugin |
|---|---|---|
| fundo / texto / destaque | `#eff0f1` / `#232629` / `#3daee9` | `#efefef` / `#000000` / `#308cc6` |

O plugin linka `libKF6IconThemes`, que linka `libKF6BreezeIcons` (ícones,
~26 MB descompactados, ~3 MB no AppImage). Ficou embutido para os ícones
funcionarem fora do KDE. Custo do plugin + ícones: ~5 MB no AppImage (medido).

## Por que tinha dado errado (diagnóstico anterior corrigido)

As quatro tentativas antigas (renomear o módulo, versionar, etc.) estavam
atacando o erro errado:

1. `QT_QUICK_CONTROLS_STYLE=Breeze` procura um módulo `Breeze`, que não
   existe. O nome correto é `org.kde.breeze`.
2. Não havia ciclo `QtQuick.Controls → Breeze`: o `depends QtQuick.Controls`
   do próprio módulo é normal e carrega.
3. O build copiava só o QML do Kirigami e não as libs KF6 nem o módulo do
   estilo, então o import falhava com `not installed` ou `plugin not found`.
4. O Qt embutido (PySide6 do pip, 6.11/6.12) não batia com o Qt dos pacotes
   (6.10.2). Os plugins do KF6 exigem o mesmo `qt6-base-private-abi`.
   **Por isso o build agora exige `PySide6 == 6.10.2`** e falha cedo se não
   for essa versão.

## Como verificar

```sh
# qual estilo foi escolhido e se o módulo está no bundle
./sober-optimizer-x86_64.AppImage   # a GUI sobe; log em ~/.local/state/sober-optimizer/
# forçar outro estilo
QT_QUICK_CONTROLS_STYLE=Basic ./sober-optimizer-x86_64.AppImage
```

Teste feito: janela `ApplicationWindow` do Breeze carrega com zero erros QML,
e a classe da janela difere da do `Basic` (prova de que o QML do Breeze é o
usado). A suíte de testes passa com 256/257; a falha restante
(`test_portal_full_loop_without_ui`) também ocorre no código original e é
ambiental: exige barramento D-Bus de sessão.

## Limitações conhecidas

- O bundle usa Kirigami 6.24 e Breeze 6.6.4 do Ubuntu 26.04. São de
  versões diferentes; o app carrega, mas não foi testado em KDE real.
- O piso de glibc continua **2.38** (libwayland 1.24 e KF6).
- Cores e fonte seguem o sistema do usuário só quando o Qt do sistema traz
  o tema de plataforma do KDE; o bundle usa o Qt embutido, então a fonte base
  vem do piso do app (ver "Fonte base" abaixo), e as cores do Breeze claro ou
  escuro vêm do esquema do KDE, se houver em `~/.config/kdeglobals`.
- Ícones: o `libKF6BreezeIcons` embutido cobre o tema Breeze. Se o usuário
  tiver o tema do KDE instalado, ele é usado no lugar.

## Tamanho (medido)

| etapa | AppImage | observação |
|---|---|---|
| build anterior (com Breeze) | 58,3 MB | zstd padrão do appimagetool |
| + poda de libs não alcançadas | — | −31 MB descompactados (KF6 de tema/config, BreezeIcons de 26 MB, Quick extras, EGL, Labs, estilos Fluent/Fusion/Imagine/Universal) |
| + ICU filtrado (en, pt, root) | 45,0 MB | libicudata de 32 MB → 14 MB |
| + poda do stdlib por alcance | 38,4 MB | stdlib 35,6 → 7,5 MB descomp. A maior parte é a pasta `config-3.11-*` (libpython.a estático de build, 24 MB), que o binário não usa |
| + plugin de tema do Kirigami e BreezeIcons | 45,8 MB | zstd padrão (128 KB de bloco). Tema correto, mas +7,4 MB |
| + zstd nível 22 com bloco de 1 MB | **40,1 MB** | só o bloco de 1 MB dá 44,3 MB; só o nível 22 dá 45,5 MB; juntos, −12,6% |

Redução total com o tema funcionando: **−18,2 MB (−31%)** em relação ao build
com Breeze (58,3 MB). Sem o plugin de tema, o mesmo bundle ficaria em 35,0 MB,
mas com as cores erradas (ver a tabela de cores acima): o plugin custa ~5 MB.

### Compressão (zstd)

O appimagetool empacota com o mksquashfs embutido, que só aceita zstd (`--comp xz`
falha). Duas opções controlam o tamanho, e as duas são usadas no build:

- `-b 1M`: bloco de 1 MB, o máximo do squashfs. Blocos maiores deixam o zstd
  achar mais repetição entre arquivos (o ganho maior).
- `-Xcompression-level 22`: nível máximo do zstd. Sozinho ganha pouco; junto com
  o bloco de 1 MB, ganha ~10%.

Custo: o build fica ~2x mais lento (zstd 22). A descompressão continua rápida,
porque o zstd descomprime na mesma velocidade qualquer que seja o nível.

### Cores dos controles (num KDE escuro)

Os controles do Breeze QQC2 não expõem contraste por API pública: no escuro a
borda do checkbox e do interruptor é 15% do texto, e a caixa quase some no
fundo (medido: 2,08:1 sobre o cartão; WCAG 1.4.11 pede 3:1). O `frameContrast`
do Kirigami não alcança esses indicadores, e o `qqc2-breeze-style` 6.7.5 tem
os mesmos indicadores da 6.6.4.

`AppCheckBox` e `AppSwitch` usam os indicadores do próprio Breeze
(`Impl.CheckIndicator` e `Impl.SwitchIndicator`) e sobrescrevem só as cores,
via `Kirigami.Theme`: o fundo da caixa sobe 10% em direção ao texto, a borda do
desmarcado vai a 60% (contraste ≥ 3:1), e o marcado/ligado é azul cheio com
`highlightColor`. Depende do módulo interno `org.kde.breeze.impl`, que não é
API pública: pode mudar entre versões do KDE. O caminho oficial para o azul
cheio é o estilo `org.kde.desktop` (+8 a 10 MB estimados, não medidos).

Diagnóstico: `RT_DEBUG_TEMA=1` grava no log (`~/.local/state/sober-optimizer/`)
as cores que o Kirigami recebeu. (Este diagnóstico foi removido do código.)

### Tipografia e layout

Regra: **nenhum negrito explícito** no QML. A hierarquia vem do tamanho (níveis
do `Kirigami.Heading`) e do texto secundário (`opacity: 0.7`), como nos apps
KDE; o negrito de campo e de etapa deixava a tela pesada.

- Cabeçalho (`AppHeader`): ícone e título, com o colorSet `Header` do
  Kirigami. A descrição do script fica na tela de boas-vindas, não na barra.
- Página (`AppPage`): título nível 2 e margem de respiro em cima e embaixo.
- Cartão (`AppCard`): título nível 4 e padding maior.
- Etapas: grupo com rótulo pequeno e `Kirigami.Separator`; título da etapa
  em peso normal, descrição em texto secundário.
- Boas-vindas: nome como `Kirigami.Heading` nível 1, ícone de 80 px.
- "Procurar…" usa o botão com moldura (era `flat`, parecia texto solto).

### Fonte base

O Qt embutido cai em ~9 pt (12 px) sem o tema de plataforma do KDE, e os
botões e títulos do Kirigami ficaram pequenos. `gui/app.py` aplica um piso de
**11 pt** (`FONTE_MINIMA_PT`): se o sistema der mais, prevalece o do sistema.
Medido: fonte de 12 → 14 px, altura dos botões de 31 → 35 px. Para mais, mude a
constante.

### Como cada corte foi escolhido

- **Poda** (`tools/prune_unused_libs.py`): a análise parte do que o app
  carrega de fato (módulos do PySide6, plugins Qt, módulos QML) e segue o
  NEEDED. Lib que nada alcança sai. Roda a cada build, então acompanha a
  versão do Qt.
- **ICU** (`tools/build-icu-data.sh`): o `libicudata.so.73` recompilado com
  só root/en/pt. Mesmo soname e mesmo símbolo exportado (`icudt73_dat`), então
  o Qt embutido carrega sem mudança. Medido: pt-BR, en-US, colação e caixa alta
  dão saída idêntica com a lib antiga e com a nova. **Custo:** ~30 min de
  compilação em 2 núcleos, uma vez.
  - Locales fora de en/pt caem para root (inglês). Este app é pt/en.
  - Os codecs `.cnv` foram mantidos de propósito: removê-los pode quebrar
    conversões de texto do Qt.

### Usar o ICU filtrado no build

```sh
tools/build-icu-data.sh <trabalho> <trabalho>/libicudata.so.73.2
ICU_DATA_SO=<trabalho>/libicudata.so.73.2 VENV=... DEBS=... BUILD=... \
    tools/build-appimage.sh kmodifier saida.AppImage
```
Sem `ICU_DATA_SO`, o build usa o ICU completo do wheel (32 MB) e segue funcionando.

### O que foi tentado e revertido

- **Tirar o `QtNetwork`**: o binding `QtQml` do PySide importa `QtNetwork`
  internamente. Sem ele, a GUI falha com `ImportError: could not import
  module 'PySide6.QtNetwork'`. O smoke de CLI passou, porque não carrega a GUI.
  Por isso a checagem de GUI é obrigatória depois de cada corte.

### Stdlib (`tools/prune_stdlib.py`)

O que fica é o fecho de imports de `rt/`, PySide6 e shiboken6, mais o que um
rastreio real de execução carregou (`tools/stdlib-trace.txt`, gerado por
`tools/trace_stdlib.py` com CLI e GUI). `ctypes` e `unittest` saem: nenhum
caminho testado os carrega. Se algum caminho não coberto precisar deles, o
erro aparece no primeiro import, então rode a checagem de GUI depois de
alterar a lista.
