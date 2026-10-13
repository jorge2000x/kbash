#!/usr/bin/env bash
# Exemplo do §4.7 — usado em testes e como referência de autoria.
#@runtime 1
#@name Configurar ambiente de desenvolvimento
#@description Instala ferramentas básicas e configura o git.
#@version 1.0.0
#@author Equipe kbash

#@option user_name type=string label="Nome para o git" required=true
#@option editor type=choice label="Editor padrão" choices="vim,nano" default=nano
#@option telemetry type=bool label="Enviar telemetria" default=false

#@step update_index
#@title Atualizar índice de pacotes
#@desc Simula a atualização do índice de pacotes.
#@group Preparação
#@root true
update_index() { echo "atualizando índice (root)"; }

#@step install_tools
#@title Instalar ferramentas
#@desc Instala as ferramentas básicas.
#@group Ferramentas
#@depends update_index
install_tools() {
  rt_progress 10 "Instalando ferramentas..."
  echo "instalando: curl git"
  rt_set tools_dir "$RT_WORKDIR/tools"
  rt_progress 100 "feramentas instaladas"
}

#@step config_git
#@title Configurar git
#@group Ferramentas
#@depends install_tools
config_git() {
  echo "git user.name=$OPT_USER_NAME editor=$OPT_EDITOR telemetry=$OPT_TELEMETRY"
  echo "ferramentas em $RT_VAR_TOOLS_DIR"
  if rt_confirm "Ativar assinatura de commits?" n; then
    echo "assinatura ativada"
  else
    echo "assinatura desativada"
  fi
  rt_notify "Git configurado"
}
