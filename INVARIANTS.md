# Invariantes do core

Uma por linha, em português simples (SPEC §16.2). Entre colchetes, o teste ou
contrato que as verifica. `[pendente]` = ainda sem verificação.

## Parser (`core/parser.py`)

- Qualquer texto de entrada termina com um script válido ou com `ParseError`/`ValidationError`, nunca com outra exceção. [tests/test_props_parser.py::test_nunca_levanta_outra_excecao]
- Parsear o mesmo texto duas vezes dá o mesmo script. [tests/test_props_parser.py::test_determinismo]
- Um script gerado com N opções, steps e ações devolve exatamente essas N declarações, com os mesmos ids. [tests/test_props_parser.py::test_declarado_e_obtido]
- Ids de opções, steps e ações são únicos entre si. [tests/test_props_parser.py::test_ids_unicos]
- Os grupos (`groups`) seguem a ordem da primeira declaração, com `""` para o bloco sem título. [tests/test_props_parser.py::test_ordem_dos_grupos]
- A linha `#!` inicial não muda o resultado. [tests/test_props_parser.py::test_shebang_nao_muda_resultado]
- `timeout` de step e de ação é nulo ou maior que zero. [tests/test_props_parser.py::test_timeout_positivo]

## Planner (`core/planner.py`)

- `resolve` devolve exatamente o fecho da seleção (mais os `required`) pelas dependências, conferido por força bruta. [tests/test_props_planner.py::test_fecho_igual_ao_oraculo]
- Em `resolve`, cada dependência presente vem antes do step que depende dela. [tests/test_props_planner.py::test_dependencias_antes]
- `resolve` é idempotente: resolver o resultado de novo dá o mesmo resultado. [tests/test_props_planner.py::test_idempotencia]
- `auto_added` é exatamente o que entrou além da seleção explícita e dos `required`. [tests/test_props_planner.py::test_auto_added_exato]
- Step inexistente na seleção é erro de validação, não é ignorado. [tests/test_props_planner.py::test_selecao_desconhecida_erra]

## Protocolo IPC (`core/ipc.py`)

- Escapar e desescapar um texto devolve o próprio texto. [tests/test_props_ipc.py::test_escape_roundtrip]
- A resposta codificada é uma única linha terminada em quebra de linha, mesmo para valores longos. [tests/test_props_ipc.py::test_uma_linha]
- Se a resposta for truncada, o valor que chega ao script é um prefixo do valor original. [tests/test_props_ipc.py::test_truncamento_preserva_prefixo]
- Para valores curtos, codificar e decodificar devolve id, status e valor exatamente. [tests/test_props_ipc.py::test_roundtrip_curto]
- Chave de variável aceita só `[A-Za-z_][A-Za-z0-9_]*`. [tests/test_props_ipc.py::test_chave_de_variavel]

## Ações (`core/actions.py`)

- O ambiente de uma ação tem `OPT_*` para toda opção com valor. [tests/test_props_actions.py::test_opt_para_toda_opcao]
- Opção oculta (`needs_step` fora da seleção) entra com o `default`, não com o valor da tela. [tests/test_props_actions.py::test_oculta_usa_default]
- O status de uma ação é sempre um de `ok`, `failed`, `timeout`, `error`. [tests/test_actions_run.py::test_error_status_when_process_cannot_start]
- `ok` só com código de saída 0. [tests/test_actions_run.py::test_success_status_and_exit_code]
- A saída devolvida tem no máximo `OUTPUT_LINES` linhas. [tests/test_actions_run.py::test_output_is_limited_to_last_lines]
