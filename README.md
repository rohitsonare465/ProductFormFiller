# Product Form Filler

A macOS desktop helper for filling an already-open product form in Google Chrome from a CSV row.

The app is intentionally conservative:

- It does not open Chrome.
- It does not navigate pages.
- It does not change tabs.
- It does not move or click the mouse.
- It does not press Enter.
- It has a low-level safety guard that blocks Enter/Return before any key is emitted.
- It does not click Submit.
- It only types characters and presses Tab between fields.
- It stops immediately after the final `Barcode` field.

## Requirements

- macOS
- Python 3.12
- Chrome opened manually by the user
- macOS Accessibility permission for the terminal or packaged app that runs this program

## Install

```bash
cd /Users/rohitsonare/ProductFormFiller
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## macOS Accessibility Permission

The typing engine uses `pynput`, which requires Accessibility access.

1. Open **System Settings**.
2. Go to **Privacy & Security**.
3. Open **Accessibility**.
4. Enable the terminal app you use to run this project, such as Terminal, iTerm, VS Code, Cursor, or Codex.
5. Restart that terminal/app after enabling permission.

## Run

```bash
source .venv/bin/activate
python main.py
```

## Workflow

1. Click **Load CSV** and select the product CSV.
2. Select the row to fill.
3. Open Chrome manually.
4. Open the product form manually.
5. Click inside the first field, `SKU`, manually.
6. Return to the app and click **Fill Current Form**.
7. Confirm the safety prompt.
8. During the five-second countdown, manually focus Chrome and click the `SKU` field again if needed.
9. The app types fields in order and presses Tab between fields.
10. After `Barcode`, the app stops.
11. Review the form and click Submit manually.

## Enter/Return Safety

The typing engine validates every key before it is sent to macOS. `Enter`, `Return`, newline, carriage return, and text-mode tab characters are blocked. If a future code change accidentally tries to emit Enter or Return, the worker stops and reports a safety error instead of sending the key.

Field navigation is only:

```text
Type field value
Tab
Type next field value
Tab
...
Type Barcode
Stop
```

## Typing Timing

- Normal Mode targets about 4 to 5 minutes for a complete 41-field form, depending on field length.
- Fast Mode targets about 3 to 3.5 minutes for a complete 41-field form, depending on field length.
- Normal character delay: random 40 ms to 90 ms.
- Fast character delay: random 25 ms to 60 ms.
- Word pause after spaces: random 80 ms to 200 ms.
- Normal Tab delay: random 250 ms to 500 ms.
- Fast Tab delay: random 120 ms to 300 ms.
- Normal field pause after every field except `Barcode`: random 200 ms to 600 ms.
- Fast field pause after every field except `Barcode`: random 80 ms to 250 ms.
- Normal group pause after every random group of 5 to 8 fields: random 1.0 to 2.5 seconds.
- Fast group pause after every random group of 8 to 12 fields: random 0.5 to 1.2 seconds.
- Normal pause after `Long Description`: random 2.0 to 4.0 seconds.
- Fast pause after `Long Description`: random 1.0 to 2.0 seconds.
- The timing profile never uses Enter, Return, submit actions, mouse actions, navigation, or tab changes.

## CSV Columns

The CSV must contain these columns:

```text
SKU, ASIN, Product Title, Brand, Manufacturer, Model, Category, Short Desc,
Long Desc, Search Keywords, Generic, Target, Use, MRP, Selling, Discount,
Stock, MOQ, Fulfillment, Weight, Length, Width, Height, Handling, Main Image,
Img1, Img2, Img3, Video, Color, Material, Variant, HSN, Origin, Warranty,
Safety, Cert, Disclaimer, Return, GST, Barcode
```

Extra columns are ignored. Missing required columns block filling.

## Progress And Logs

Local data is stored in:

```text
~/Library/Application Support/ProductFormFiller/
```

Files:

- `settings.json`: last CSV, UI preferences, typing profile, auto-advance setting.
- `progress.json`: last completed row.
- `filled_rows.log`: timestamped history of completed fills.

## Controls

- **Previous Row / Next Row / Go To Row**: select a row in the preview table.
- **Auto Advance**: after a successful fill, select the next row automatically.
- **Typing Profile**: choose Normal Mode or Fast Mode. Both modes keep character-by-character typing, Tab-only navigation, randomized timing, and stop after `Barcode`.
- **Pause / Resume / Stop**: controls an active fill operation.
- **Dark Mode**: toggles the application theme.

## Packaging Optional

For a standalone macOS app bundle, install PyInstaller and build:

```bash
source .venv/bin/activate
pip install pyinstaller
pyinstaller --windowed --name "Product Form Filler" main.py
```

Grant Accessibility permission to the generated app after packaging.
