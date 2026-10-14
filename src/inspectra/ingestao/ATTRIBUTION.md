# Atribuição e licenças

Esta pasta integra ao EnemyDisclosure duas ferramentas de código aberto do
diretório `D:\Dev\Complexo`. Os créditos e licenças originais são preservados
abaixo.

## ARTEX — `skills/api-recon` (vendorizado)

- **Origem:** `D:\Dev\Complexo\ARTEX\skills\api-recon`
- **Projeto:** ARTEX (AI autonomous penetration testing system)
- **Licença:** AGPL-3.0
- **O que foi vendorizado:** os scripts do `api-recon` foram copiados para
  `complexo/vendor/api-recon/` (`harvest_static.py`, `spider_mpa.py`,
  `runtime_harvest.js`, `preload.js`, `extract_route_map.py`,
  `build_perm_tree.py`, `package.json`, `SKILL.md`, `reference.md`).
- **Uso previsto:** reconhecimento de APIs de portais **públicos/público
  autorizados** (enumerar endpoints, rotas, parâmetros). Não é teste de
  intrusão; a própria skill proíbe exploração.
- **Nota AGPL-3.0:** como o ARTEX é licenciado sob AGPL-3.0, o uso/distribuição
  deste código vendorizado deve respeitar os termos da AGPL-3.0 (atribuição e
  disponibilização do código-fonte correspondente em caso de distribuição).
  Consulte o texto da licença no repositório do ARTEX.

## REA — Reverse Engineer Anything (dependência externa, não vendorizada)

- **Origem:** `D:\Dev\Complexo\REA`
- **Licença:** MIT
- **Como é usada:** via CLI externa (`rea`), localizada por `ENEMY_REA_BIN` /
  PATH / `ENEMY_REA_HOME`. **Nenhum código do REA foi copiado** para este
  repositório; o wrapper apenas invoca o binário.
- **Uso previsto:** análise lícita — inspeção de snapshots SQLite, análise
  estática de aplicações JavaScript, observação passiva de páginas via CDP,
  inspeção de binários gerenciados (.NET). Leia o `DISCLAIMER.md` do REA.

## play-cli — ARTEX `skills/playwright-cli` (dependência externa)

- **Origem:** `D:\Dev\Complexo\ARTEX\skills\playwright-cli`
- **Licença:** conforme o ARTEX (AGPL-3.0)
- **Como é usada:** via CLI externa, localizada por `ENEMY_PLAYWRIGHT_CLI` /
  PATH. Nenhum código copiado.

---

## Observação sobre o licenciamento combinado

Se o EnemyDisclosure for **distribuído** com o código vendorizado do ARTEX,
a AGPL-3.0 impõe obrigações sobre o conjunto. Para uso **interno/privado**, as
obrigações de distribuição da AGPL não são acionadas, mas a atribuição é boa
prática e está registrada aqui. Em caso de dúvida, prefira consumir o ARTEX
como dependência externa (como é feito com o REA) em vez de vendorizá-lo.
