# IoT Telcom Expense Manager

Video Demo: [Watch the project walkthrough on YouTube](https://youtu.be/QIDkNT4u9Qo)

A web app for reviewing corporate SIM usage, tariffs and invoices. This is Giancarlo Balan’s CS50x final project.

When a company uses several operators, its inventory, usage and billing files can be difficult to compare. This project brings those records into one place. You can check how costs change over time, look into roaming charges and find invoices that do not match the expected amount.

The demo comes with sample data, so you can explore it without uploading anything.

## About the data

CS50 Group is a fictional company. All SIM records, usage, invoices and tariffs were generated for this project. Movistar, Vodafone and Orange are used as operator labels, but the file layouts and pricing rules are examples, not official formats or offers. No customer data is included.

The sample covers January to August 2026. It starts with 5.800 SIMs and reaches 10.000 in August. The operator split stays at 60% Movistar, 25% Vodafone and 15% Orange. Each operator has three tariff profiles, with monthly data allowances of 50 MB, 500 MB and 5.000 MB.

Usage is recorded by SIM, day and country. A SIM can therefore have a record for Spain and another for Andorra on the same day. Calls and SMS are included alongside data.

The roaming sample keeps a smaller set of complete SIM trips, bringing the calculated cost to roughly 10% of the original sample in each month. Rates and domestic usage are unchanged. In August, 115 SIMs record roaming usage, costing 3.076,77 €. This adjustment applies once to generated records; uploaded records are kept as supplied.

Monthly fees in the demo are:

| Operator | 50 MB | 500 MB | 5.000 MB |
| --- | ---: | ---: | ---: |
| Movistar (MV) | 0,50 € | 2,00 € | 6,00 € |
| Vodafone (VF) | 0,55 € | 2,10 € | 6,00 € |
| Orange (OR) | 0,45 € | 1,90 € | 6,00 € |

The interface stays in English but uses Spanish number formatting: for example, 10.000 SIMs and 1.234,56 €. Profile identifiers and source-file formats keep their technical notation.

## Run the app

You need Python 3.11 or newer. Open the project folder in VS Code and run:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

On macOS or Linux, replace `.venv\Scripts\python` with `.venv/bin/python`.

Open **http://127.0.0.1:5050**. The first run creates the sample database; progress appears in the terminal. Later runs reuse that database, including any files you have imported. Press Ctrl+C in the terminal to stop the server.

On the original development computer, the packages are already installed, so `python app.py` also works. The `start-local.ps1` script uses the project’s virtual environment if one exists. VS Code also has a launch configuration for debugging.

## What you can do

- **Overview:** check monthly spend, SIM growth and costs by operator. The cards use the selected period. The history chart always shows January–August and follows the operator, profile and department filters.
- The overview compares operators on shared chart scales: monthly cost or data per SIM, stacked billed spend and SIM growth. Movistar is blue, Vodafone is burgundy and Orange is orange across the charts. Hover over a month to see all operator values together. Side-by-side bars use the selected period. Cost averages exclude missing invoices; usage averages exclude SIM-months with no usage records.
- **Roaming:** select a country to see usage and costs by tariff. Andorra has a deliberately high share of the sample’s roaming costs. Selecting a tariff colors the map by its roaming zones.
- **SIM inventory:** search by ICCID or department, open a SIM’s history and find records with no usage, excess charges or invoice differences.
- **Tariffs & operators:** compare allowances, rates and average monthly cost per SIM.
- **Invoice reconciliation:** compare invoices with expected charges and find missing records.
- **Data imports:** upload a CSV or Excel file, check the converted records and import them.

Manager, Operations and Logistics are shortcuts to different views. They are not accounts or permission levels. Manager opens the overview, Operations opens invoice exceptions and Logistics opens the zero-usage list.

## Try an import

Select an operator in Data imports and download its Inventory sample. Upload it, choose **Validate & preview**, then **Import 3 rows**. Repeat with Usage and Invoice, in that order, for the same operator.

Each sample set adds three SIMs in August, with usage in Andorra. Once all three files are imported, their invoices should match the calculated costs. You can also run `python generate_samples.py` to create all 18 CSV and Excel samples in `demo-files/`.

The sample formats use different units:

- Movistar: MB, minutes and EUR.
- Vodafone: KB, seconds and cents.
- Orange: GB, minutes and EUR. Its CSV files use semicolons and accept decimal commas.

The app converts these to common units before saving them. It uses 1.024 MB per GB and 1.024 KB per MB. Keep ICCIDs as text in Excel: numeric cells can lose digits from a 19-digit identifier.

Previewing a file does not change the database. The checks cover column names, dates, SIMs, profiles, numeric values and duplicates. If any row has an error, the whole import is blocked. Existing records are not replaced. A file hash also prevents the same file from being imported twice.

Uploads are limited to 3 MB and 5.000 rows. Excel files also have a 25 MB limit after decompression. The import history stores the filename, time, operator, document type and row count; the original file is not retained. Related dashboard summaries are updated after a successful import.

## How costs are calculated

Expected charges are the monthly fee, domestic excess and roaming added together. Amounts are stored in euro cents. Usage can include fractions of MB and minutes, and tariff rates can include fractions of a cent. Charge components are rounded to cents using Python’s rounding rules.

Each SIM pays the full monthly fee, including in its activation month. Domestic usage above its data, voice or SMS allowance is charged at the corresponding excess rate. Roaming is charged separately by country and tariff zone; the demo does not assume free EU roaming.

These are simplified rules. There are no pooled allowances, rollover, discounts, credits, partial-month fees or taxes. International calls originating in Spain are also outside the project’s scope.

Invoice differences are calculated only where both an invoice and usage records exist. A missing usage file is not treated as proof of zero usage. However, one usage record is enough to mark a SIM-month as having data: the app does not yet check whether every expected daily record has arrived.

The map shows past usage, not live SIM locations. A SIM can appear in several country totals, so adding those counts will count some SIMs more than once.

Zero-usage lines and high charges are worth checking, but they are not proof of savings. Operator comparisons also depend on the tariff mix and how much each SIM uses.

## Project files

- `app.py` handles the Flask routes, filters and upload requests.
- `domain.py` defines the database, sample tariffs and data generator. It also rebuilds monthly summaries.
- `imports.py` reads and checks the three file formats, converts units and creates sample files.
- `templates/index.html` contains the page layout.
- `static/app.js` handles navigation, charts, maps, tables and uploads.
- `static/comparison.js` and `static/comparison.css` contain the operator comparison charts and styles.
- `static/styles.css` contains the desktop and mobile styles.
- `static/world.geojson` contains the map boundaries.
- `tests/` contains the automated checks.

The app uses Flask, Waitress, SQLite, openpyxl and JavaScript. It does not need a front-end build step or an external map service. SQLite keeps daily records as well as monthly summaries, so the dashboard can load without recalculating everything each time. The generated database is about 270 MB and is excluded from version control.

## Run the tests

```powershell
python -m pytest -q tests
```

The tests check imports for each operator and file type, unit conversion, duplicates, invalid records, cost calculations and request protection. Tests of the full sample dataset expect the original 10.000 SIMs. Importing the extra sample SIMs changes those totals.

For browser tests, start the local server, then run:

```powershell
python -m pip install playwright
python -m playwright install chromium
python tests/browser_smoke.py
```

This checks the six pages, filters, country and SIM details, upload preview and mobile layout. It saves screenshots in `data/` without importing records into the main database.

## Sharing the demo

The app currently runs locally. It has not been published and has no public URL yet.

The Dockerfile prepares a read-only version for hosting. It uses `HOST=0.0.0.0`, accepts a `PORT` setting and turns off uploads with `ALLOW_IMPORTS=0`. The application factory also disables imports by default. The supplied startup script only enables them when listening on a loopback address, such as `127.0.0.1`. Public upload requests are rejected before their files are parsed, including requests sent directly to the API.

Local imports accept CSV and XLSX only. Excel files with detected macros, external workbook links, embedded files or formulas are rejected. These checks are not an antivirus scanner or a guarantee that an arbitrary file is safe. Use the provided synthetic samples for the video; never open an untrusted download just to test the app.

Hosting must provide HTTPS. Keep dependencies updated, keep secrets and real customer data out of the repository, and apply request and resource limits at the hosting layer. The application includes browser security headers and runs without debug tracebacks. Automated security checks cover upload rejection, file limits and access to private paths; they are not a penetration test or a promise of complete security.

Do not publish the writable local version as it stands. It has no login or separation between visitors’ data. Public uploads would need those protections, upload rate limits and further security testing.

Other possible additions include SIM status changes, tariff changes over time, shared allowances and more detailed billing rules. The project walkthrough is linked at the top of this README. The CS50 submission is still pending.

## Map source

The map uses public-domain [Natural Earth](https://www.naturalearthdata.com/about/terms-of-use/) data from the [natural-earth-vector repository](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson). Andorra and other small destinations use markers. The software dependencies keep their own licenses.
