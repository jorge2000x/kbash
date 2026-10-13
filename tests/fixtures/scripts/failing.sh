#!/usr/bin/env bash
# Fixture: falhas, on_error e dependências (Fase 1/§7.4).
#@runtime 1
#@name Fixture de falhas

#@step ok_one
ok_one() { echo "ok_one rodou"; }

#@step boom
#@desc Sempre falha com código 3 (on_error padrão = stop).
boom() { echo "falhando de propósito" >&2; return 3; }

#@step after_boom
after_boom() { echo "não deveria rodar (stop)"; }

#@step boom_continue
#@on_error continue
boom_continue() { echo "falha mas o plano continua" >&2; return 7; }

#@step after_continue
after_continue() { echo "rodou depois da falha com continue"; }

#@step child_of_continue
#@depends boom_continue
child_of_continue() { echo "depende de um step que falhou"; }

#@step slow
#@timeout 1
slow() { sleep 30; }

#@step spawner
#@desc Lança um processo filho que precisa morrer no cancelamento.
spawner() { sleep 300 & echo "filho=$!"; sleep 300; }

#@step ultimo
#@desc Declarado por último: útil para verificar o skip após cancelamento.
ultimo() { echo "não deveria rodar"; }
