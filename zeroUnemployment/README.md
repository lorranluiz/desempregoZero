# Potencial de Mobilidade de Trabalhadores por Setor — Brasil

Servidor web interativo (Dash/Plotly) que exibe **12 mapas do Brasil** (um por
setor econômico), com **setas de atração/repulsão** de trabalhadores e uma
**camada de fundo** representando o potencial de mobilidade de trabalhadores
por Unidade da Federação (subutilização da força de trabalho + informais).

## Instalação

Requer Python 3.10+ (testado em 3.14). Recomenda-se um ambiente virtual:

```bash
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Execução

```bash
python app.py
```

Acesse **http://localhost:8050**. Ao iniciar, o shapefile do IBGE é baixado
automaticamente para `data/BR_UF_2022/` (apenas na primeira execução).

## Dados de entrada

Os arquivos são procurados na raiz do projeto ou na pasta `tabelas/`:

| Arquivo | Conteúdo |
|---|---|
| `tab06.xls` (ou `*tab06*.xls`) | VAB setorial por UF (IBGE, Contas Regionais), coluna 2022 |
| `tabela4666.xlsx` (ou `*4666*.xlsx`) | Subutilização da força de trabalho por UF (PNAD Contínua, 2024) |
| `tabela8517.xlsx` (ou `*8517*.xlsx`) | Trabalhadores informais por UF (PNAD Contínua, 4º tri 2024) |

Os valores de ρᵢ são hardcoded em `data.py` (ILAESE, Anuário 2025/26,
Tabela II-quinquies, ρᵢ 2024).

## Metodologia

* **ρ̄ = 1.375** (média dos 12 parâmetros setoriais; valor calculado ≈ 1.3748).
  Há exatamente 6 setores com ρᵢ > ρ̄ (azul) e 6 com ρᵢ < ρ̄ (vermelho).
* **Fundo**: potencial de mobilidade = (subutilização + informais) normalizado
  pelo total nacional (≈ 57,96 milhões de pessoas). Escala branco → cinza-azulado.
* **Setas (fluxo entre estados)**: em vez de uma seta por estado, cada
  **fronteira entre estados vizinhos** recebe uma seta de **fluxo líquido**:

  * `saldo[r] = potencial[r] − w[i][r]` — superávit (`> 0`, "excedente de
    trabalhadores") ou déficit (`< 0`, "déficit de trabalhadores");
  * `fluxo(A→B) = saldo[A] − saldo[B]` — sinais opostos **somam**; sinais
    iguais **subtraem**. A seta aponta do superávit ao déficit.
  * Comprimento e espessura proporcionais a `√(|fluxo|/max_setor)` (compressão
    por raiz quadrada, para atenuar a forte concentração setorial — ex.:
    extrativas no RJ ≈ 68% do VAB nacional).

## Limitações

* VAB de 2022 e subutilização/informais de 2024 — anos diferentes, mas ambos os
  mais recentes disponíveis.
* O potencial de mobilidade é um **estoque**, não um fluxo; a realocação
  efetiva depende de política, qualificação e custos de migração.
* Informais já estão ocupados; sua realocação para setores formais depende de
  salário, formalização e demanda por qualificação.
* ρᵢ de 2024 aplicado a wᵢʳ de 2022.

## Decisões de implementação (documentadas)

1. **URL do shapefile corrigida**: a URL do enunciado aponta para um caminho
   desatualizado. A correta é
   `.../municipio_2022/Brasil/BR/BR_UF_2022.zip` (o enunciado omitia `Brasil/BR/`).
2. **`pyogrio` no lugar de `fiona`**: o `fiona` não possui wheel para Python 3.14;
   o `pyogrio` possui (abi3). Ambos são engines de I/O do geopandas.
3. **`xlrd` para `.xls`**: o `openpyxl` só lê `.xlsx`; o tab06 é `.xls`.
4. **Mapeamento aba→setor trocado nas duas últimas**: a aba `Tabela6.12` corresponde
   ao setor 12 (Administração pública) e a `Tabela6.13` ao setor 11 (Outros
   serviços), seguindo a ordem padrão MIP e o dicionário RHO.
5. **Direção visual das setas**: seta de fluxo aponta do superávit ao déficit
   (do estado com mais trabalhadores disponíveis em relação ao setor para o
   estado com déficit).
6. **Limiar "escuro/claro"**: mediana do potencial nacional (≈ 13/14 estados).
7. **Setas nas fronteiras**: as setas são desenhadas como traces **`Scattergeo`**
   (linha + marcador de ponta) posicionados por lon/lat, corretamente alinhados
   ao mapa (ao contrário de `add_annotation`, que só aceita coordenadas de dados
   em subplots cartesianos). A adjacência (51 fronteiras) é calculada sobre a
   geometria **completa** do shapefile (antes da simplificação), via join
   espacial + `boundary ∩ polígono`. Fronteiras com fluxo abaixo de um limiar
   (após normalização por setor) são omitidas.
8. **Tema escuro retro-futurista "verde neon" (padrão)**: página e mapas em
   fundo escuro (`#050a06`), choropleth de verde-escuro (`#07120b`) a verde
   neon (`#00ff9d`), setas em ciano `#00e5ff` (atração) e vermelho `#ff2d55`
   (repulsão). Estilos em `assets/style.css`.
9. **Popup por clique**: o tooltip de hover foi removido; as informações do
   estado aparecem num cartão neon ao **clicar** no estado, posicionado junto
   ao clique, e somem ao clicar fora (overlay) ou pressionar `Esc`. O conteúdo
   é pré-gerado no servidor e servido como JSON (em `#popup-data`) para o
   `assets/custom.js` (scripts injetados via React não executam).

## Como baixar o shapefile manualmente

Se o download automático falhar:

1. Baixe `BR_UF_2022.zip` de
   `https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/malhas_municipais/municipio_2022/Brasil/BR/BR_UF_2022.zip`
   (ou do repositório alternativo `https://github.com/kelvins/Municipios-Brasileiros`).
2. Descompacte os arquivos (`.shp`, `.shx`, `.dbf`, `.prj`, `.cpg`) na pasta
   `data/BR_UF_2022/` (criando-a se necessário).
3. Reinicie `python app.py`.
