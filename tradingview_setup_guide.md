# TradingView → MMGPT Bridge Integration Guide

**Version:** 1.0  
**Date:** April 2026  
**Bridge URL:** `https://nonsymbolic-londyn-nonfacetiously.ngrok-free.dev`  
**Webhook Endpoint:** `POST /tradingview/webhook?token=TV_7039840724932504`

---

## Overview

TradingView Pro supports **webhook alerts** — when a Pine Script strategy or indicator condition is met, TradingView fires an HTTP POST request to a URL you specify, with a custom JSON payload. This integration routes those alerts into your MMGPT SQL Server database (`dbo.Signals_Inbox`), making TradingView a live signal source for the MMGPT pipeline.

**Data flow:**
```
TradingView Alert → ngrok tunnel → FastAPI bridge → SQL Server (dbo.Signals_Inbox)
```

---

## Step 1 — Add the Pine Script to TradingView

1. Open TradingView and load any chart (e.g. BHP.AX on ASX)
2. Click **Pine Script Editor** at the bottom of the screen
3. Click **New** to create a blank script
4. Open the file `tradingview_pine_alert_template.pine` from the MMGPT repo
5. Copy the entire contents and paste into the Pine Script Editor
6. Click **Save** — give it a name like "MMGPT Signal Bridge"
7. Click **Add to chart** — you should see two EMA lines appear on the chart

> **Note:** The demo script uses a simple 9/21 EMA crossover. You can replace the signal logic with your own strategy — just keep the `alert()` calls at the bottom intact.

---

## Step 2 — Create a TradingView Alert

1. Click the **Alert** button (clock icon) in the TradingView toolbar, or press **Alt+A**
2. In the **Condition** dropdown, select your script: "MMGPT Signal Bridge"
3. Set **Trigger** to: `alert() function calls only`
4. Set **Expiration** to: `Open-ended` (no expiry)
5. Under **Notifications**, tick **Webhook URL**
6. Paste the webhook URL:
   ```
   https://nonsymbolic-londyn-nonfacetiously.ngrok-free.dev/tradingview/webhook?token=TV_7039840724932504
   ```
7. In the **Message** box, paste this JSON (TradingView fills in the `{{placeholders}}` at alert time):
   ```json
   {
     "ticker": "{{ticker}}",
     "strategy": "MACrossover",
     "action": "{{strategy.order.action}}",
     "price": {{close}},
     "score": {{strategy.position_size}},
     "note": "TV alert at {{timenow}}"
   }
   ```
8. Click **Create** to save the alert

> **Important:** The `token=TV_7039840724932504` in the URL is your authentication token. Keep this URL private — anyone with this URL can write to your signals inbox.

---

## Step 3 — Customise for Your Own Strategies

To use your own Pine Script strategies instead of the demo:

1. Add `alert()` calls to your existing Pine Script wherever you want to fire a signal:
   ```pine
   // In your strategy, after your entry condition:
   if my_buy_condition
       alert('{"ticker":"' + syminfo.ticker + '","strategy":"MyStrategy","action":"BUY","price":' + str.tostring(close, "#.####") + ',"score":85,"note":"My custom signal"}', alert.freq_once_per_bar_close)
   ```

2. The JSON fields map to `dbo.Signals_Inbox` columns:

   | JSON field | SQL column | Notes |
   |---|---|---|
   | `ticker` | `Ticker` | Exchange prefix stripped (e.g. ASX:BHP → BHP) |
   | `strategy` | `Strategy` + `StrategyName` | Your strategy identifier |
   | `action` | Part of `Note` | BUY / SELL / LONG / SHORT |
   | `price` | Part of `Note` | Current close price |
   | `score` | `Score` | Signal strength (0–1000 scale recommended) |
   | `note` | `Note` | Free text, max 500 chars |

3. `RunDate` is automatically set to today's date by the bridge
4. `CreatedAt` is automatically set to the current SQL Server timestamp

---

## Step 4 — Verify It's Working

### Option A — Check the bridge logs on the VM

Open PowerShell on the VM and run:
```powershell
Get-Content E:\MMGPT_V3\03_bridge\bridge_out.log -Tail 20
```

When a TradingView alert fires, you should see a log line like:
```
2026-04-10 09:15:32  INFO      TradingView alert: ticker=BHP strategy=MACrossover action=BUY score=2.0
```

### Option B — Test manually with curl (PowerShell)

Open PowerShell and run this to simulate a TradingView alert:
```powershell
$body = '{"ticker":"BHP","strategy":"TestStrategy","action":"BUY","price":45.50,"score":85,"note":"Manual test"}'
curl.exe -X POST "https://nonsymbolic-londyn-nonfacetiously.ngrok-free.dev/tradingview/webhook?token=TV_7039840724932504" -H "Content-Type: application/json" -d $body
```

Expected response:
```json
{
  "status": "ok",
  "message": "Signal ingested successfully",
  "ticker": "BHP",
  "strategy": "TestStrategy",
  "action": "BUY",
  "run_date": "2026-04-10",
  "rows_inserted": 1
}
```

### Option C — Check the Streamlit dashboard

Go to the MMGPT Supervisor Dashboard Home page. The **TradingView Signals** section at the bottom shows the last 10 signals received from TradingView in real time.

### Option D — Query SQL Server directly

In SQL Server Management Studio or the Streamlit SQL Connection Test page:
```sql
SELECT TOP 10 * FROM dbo.Signals_Inbox
WHERE Note LIKE '%TradingView%'
ORDER BY CreatedAt DESC
```

---

## Step 5 — Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| TradingView shows "Webhook error" | Bridge is offline | Check `Get-Service MMGPT-Bridge` and `Get-Service MMGPT-Ngrok` on the VM |
| curl returns `{"detail":"Invalid or missing webhook token"}` | Wrong token in URL | Confirm token is `TV_7039840724932504` |
| curl returns `{"status":"error","message":"..."}` | SQL insert failed | Check bridge_err.log on VM |
| Alert fires but nothing appears in SQL | Note filter too strict | Query without the WHERE clause to check all recent rows |
| ngrok URL has changed | ngrok service restarted with new URL | Check ngrok dashboard at https://dashboard.ngrok.com — the reserved domain should be permanent |

---

## Service Management (VM — PowerShell as Administrator)

```powershell
# Check service status
Get-Service MMGPT-Bridge
Get-Service MMGPT-Ngrok

# Restart services (e.g. after updating supervisor_api.py)
E:\MMGPT_V3\03_bridge\nssm-2.24\win64\nssm.exe restart MMGPT-Bridge
E:\MMGPT_V3\03_bridge\nssm-2.24\win64\nssm.exe restart MMGPT-Ngrok

# View live bridge logs
Get-Content E:\MMGPT_V3\03_bridge\bridge_out.log -Tail 50 -Wait
```

---

## Security Notes

- The webhook token (`TV_7039840724932504`) is embedded in the URL — treat it as a secret
- Rotate the ngrok authtoken periodically at https://dashboard.ngrok.com
- The ngrok reserved domain (`nonsymbolic-londyn-nonfacetiously.ngrok-free.dev`) is permanent on your free plan — it won't change on restart
- Consider adding IP allowlisting for TradingView's webhook IP ranges in a future version

---

## What's Next

Once TradingView signals are flowing into `dbo.Signals_Inbox`, the existing MMGPT pipeline (Stage 25–38 stored procedures) will pick them up automatically on the next run. The signals will flow through:

```
dbo.Signals_Inbox → spSignals_Stage2_BuildQueue → dbo.Signals_Queue → Signals_Converged → Supervisor_TradePlans → Supervisor_Execution_Queue
```

No changes to the downstream pipeline are required — TradingView signals are treated identically to any other signal source.
