# The README screenshot

The README embeds `docs/screenshot.png`. **That file does not exist yet** —
until it does, the image shows as broken on GitHub. This is the one thing
that has to be done by hand.

## What to capture

1. Open the live app: https://truck-routing-8xit.onrender.com
   (or `npm run dev` locally — the live one is better, it proves it deploys).
2. Wait for it to finish loading. On the free tier the first load can take
   about 50 seconds.
3. Plan this trip:
   - **Origin:** Dallas, TX
   - **Destination:** Denver, CO
   - **Departure:** leave the default, or any time tomorrow morning
   - **Load weight:** 42000
   - **Checkpoint spacing:** 25 mi
4. Wait for the forecast slider to finish loading at the bottom of the map
   (the "Loading forecast" note disappears).
5. Make sure all of this is visible in the window before you capture:
   - the left panel with the form filled in,
   - the map with the recommended route coloured by risk and the other two
     as dashed grey lines,
   - the three route pills at the top of the map,
   - the risk key at the top right,
   - the forecast slider across the bottom,
   - the right panel showing the stat tiles and the comparison cards.

Maximise the browser window first. A 1920×1080 window gives the best
result: at narrower widths the right panel collapses into a button and the
screenshot loses the analysis, which is the most interesting part.

Scroll the right panel so the **stat tiles and the three comparison cards**
are in view, rather than the checkpoint list.

## How to capture it on Windows

Press **Win + Shift + S**, choose the rectangle tool, and drag around the
whole browser content area (you can leave out the browser's own toolbar and
tabs). The capture goes to the clipboard.

Then paste it into Paint (`Win` → "Paint" → `Ctrl+V`) and save as:

```
C:\Users\dk290\OneDrive\Desktop\Truck Routing\docs\screenshot.png
```

Save as **PNG**, not JPEG — text stays sharp.

## Check it before committing

```powershell
cd "C:\Users\dk290\OneDrive\Desktop\Truck Routing"
Get-Item docs\screenshot.png | Select-Object Name, Length
```

Anything over about 50 KB and under about 2 MB is fine. If it is much bigger
than 2 MB, the window was very large; resize and recapture rather than
committing a huge file.

## Optional second image

If you want one more, a good second choice is the heatmap with the slider
part-way along and the metric switched to **Wind**, which shows the
forecast moving across the corridor. Save it as `docs/heatmap.png` and add
it under the first image in the README.
