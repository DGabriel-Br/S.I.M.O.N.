# Correção Ruff 02

Correção pontual dos quatro avisos `I001` restantes.

O Ruff estava considerando o bloco de imports não formatado por causa de uma linha em branco extra entre os imports e as constantes de módulo. Esta correção apenas normaliza esse espaçamento, sem alterar comportamento.

Arquivos modificados:

- `src/simon/claims.py`
- `src/simon/entities.py`
- `src/simon/goals.py`
- `src/simon/storage.py`

Após substituir os arquivos, execute:

```powershell
uv run pytest
uv run ruff check .
uv run mypy src
uv run simon
```
