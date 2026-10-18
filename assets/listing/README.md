# Listing assets

Marketplace/listing images for the `yahoo-mail-organizer` agent skill.

- `logo-512.png` / `logo.svg`: 512×512 logo (neutral envelope icon, no Yahoo branding)
- `shot1-triage.png`, `shot2-declutter.png`, `shot3-safe-delete.png`: 1280×800 demo mockups
- `src/`: HTML sources for the screenshots

The screenshots are illustrative mockups with made-up data (example.com addresses), not recordings of a real mailbox. To regenerate one:

```bash
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
  --window-size=1280,800 --screenshot=shot1-triage.png "file://$PWD/src/shot1-triage.html"
```
