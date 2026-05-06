# Pontus Finance · Dashboard de Captação

Dashboard estática que lê dados de campanhas Meta Ads da conta **NBP - Gui Pontus** (`act_1772556290384735`), filtrando campanhas com `inlead` no nome.

URL: <https://manualdotrafego.github.io/pontus-dashboard/>

## Funil de conversão (Pixel)

| Etapa | Evento Meta Pixel | Gatilho na LP |
|---|---|---|
| 01 · PageView | `landing_page_view` | LP carregada |
| 02 · AddToCart | `AddToCart` | Clique no botão da LP |
| 03 · Contact | `Contact` | "Continuar" na etapa do e-mail |
| 04 · CompleteRegistration | `CompleteRegistration` | "Continuar" na etapa do WhatsApp |
| 05 · Lead | `Lead` | Página final (obrigado / em breve / recebemos) |

## Atualização

- **Automática:** GitHub Actions a cada 6 horas (cron `0 */6 * * *` UTC).
- **Manual:** `Actions → Update Pontus Dashboard → Run workflow`.

O workflow `.github/workflows/update-pontus-dashboard.yml` roda `scripts/fetch_pontus_dashboard.py` (gera `docs/data.json`) e publica `data.json` + `index.html` no branch `gh-pages`.

## Rodar localmente

```bash
pip install -r requirements.txt
META_ACCESS_TOKEN=xxxxx python scripts/fetch_pontus_dashboard.py
# Sirva docs/ em qualquer HTTP estático, ex.:
python -m http.server 8000 --directory docs
```

## Secret necessária

`META_ACCESS_TOKEN` — token Meta Ads com permissão `ads_read` na conta `act_1772556290384735`.
