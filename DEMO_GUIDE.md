# Video walkthrough

This outline leaves a few seconds spare in a three-minute video. Use it as a guide rather than reading it word for word.

Before recording, open the app in English, close unrelated browser tabs and use a window around 1440 × 900. Keep the sample files handy in `demo-files/`.

## 0:00–0:20 — Introduce the project

Introduce yourself and explain what the app does: it brings corporate SIM inventory, usage and invoices together so that costs are easier to check. Mention that the data and tariffs are examples. Include the title and personal details required for the course video.

## 0:20–0:50 — Show the overview

Point out the growth from January to August and the 10.000 SIMs in August. Select Vodafone and a tariff profile to show how the figures change, then reset the filters.

Explain that a profile is the tariff assigned to a SIM, including its allowances and rates.

## 0:50–1:20 — Look at Andorra

Open Roaming and click Andorra. Show the cost, number of SIMs, calls and SMS. Select a tariff to show its roaming zones on the map.

Clarify that the map shows usage during the selected period, not where each SIM is right now.

## 1:20–1:40 — Check a bill

Open Invoice reconciliation and filter for invoice exceptions. Open a SIM to see its history. Explain that the expected charge comes from the tariff and recorded usage, while the billed amount comes from the invoice.

If there is time, show a line with zero usage and explain why someone might want to review its monthly fee.

## 1:40–2:30 — Upload a sample

In the local version, choose Vodafone under Data imports. Upload its Inventory sample, check the preview and import it. Repeat for Usage and Invoice.

Explain the unit conversion: Vodafone’s sample uses KB and seconds, which become MB and minutes. Its invoice amounts are already in cents.

If this takes too long, import Inventory and Usage before recording and show only the Invoice step. Each sample can be imported once; uploading it again will produce a duplicate warning.

## 2:30–2:55 — Wrap up

Briefly mention Python, Flask, SQLite and JavaScript. Explain how the file checks stop invalid records from reaching the dashboard.

Finish with the practical use: checking an unexpected roaming charge or finding SIMs that are still being billed but have no recorded usage.

## After recording

- Check that the text and figures are readable.
- Add the video link to the README.
- Review the files before creating a public repository. Leave out databases, logs and secrets.
- Choose hosting for the read-only demo.
- Complete the course submission separately.
