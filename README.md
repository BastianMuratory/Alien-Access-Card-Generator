# Access Badge Generator — Alien RPG

Generates double-sided ID / access badges for Alien RPG characters.

- **Size:** 88 × 63 mm, landscape — the pokemon card format, if you want to fit them in card sleeves.
- **Look:** each badge is styled after its company's official logo colours.

| Company | Palette (taken from the logo) |
|---|---|
| Weyland-Yutani | black / signal yellow / grey |
| Seegson | warm black / gold / olive (70s retro) |
| Prodigy Corporation | light paper / black (monochrome) |
| Lasalle Bionational | night blue / steel blue / grey |

---

## Quick start

```bash
pip install pillow reportlab

python3 generateur_cartes.py                 # reads personnages.json
python3 generateur_cartes.py my_file.json    # reads any other JSON file
```

### What you get in `./cartes/`

| File | What it is |
|---|---|
| `LASTNAME_Firstname_recto.png` | Badge front, 300 DPI, rounded corners, transparent background |
| `LASTNAME_Firstname_verso.png` | Badge back, same format |
| `planche_impression.pdf` | A4 print sheet, **8 badges per page**, with cut marks |
| `apercu.png` | Contact sheet of every badge, for a quick look |

**Printing:** print the PDF at **100 % / actual size** (no "fit to page"), duplex,
flipping on the **long edge**. Back pages are already mirrored for that setting.

---

## The `personnages.json` file

Only four keys are truly required per character: `compagnie`, `nom`, `prenom`,
`profession`. Everything else is either optional decoration or an override for a
value the script would otherwise invent.

Minimal working file:

```json
{
  "personnages": [
    {
      "compagnie": "weyland-yutani",
      "nom": "Vasseur",
      "prenom": "Hélène",
      "profession": "Science Officer"
    }
  ]
}
```

SURNAME example, with every option in place:

```json
{
  "annee": 2183,
  "textes_compagnies": {
    "seegson": { "propriete": "PROPERTY OF SEEGSON CORP. — RETURN TO OFFICE 12" }
  },
  "personnages": [
    {
      "compagnie": "weyland-yutani",
      "nom": "Vasseur",
      "prenom": "Hélène",
      "profession": "Science Officer",
      "username": "h.vasseur",
      "password": "NOSTROMO-937",
      "flavor": "Progress never asks permission.",
      "photo": "photos/vasseur.jpg",
      "logo_grand": "logos/weyland.png",
      "logo_petit": "logos/weyland.png",
      "habilitation": 5,
      "site": "USCSS NOSTROMO",
      "textes": { "code_titre": "MY OWN LABEL" }
    }
  ]
}
```

### Top-level keys

| Key | Effect |
|---|---|
| `annee` | The in-fiction year. Used for issue/expiry dates and available as `{annee}` in custom labels. |
| `textes_compagnies` | Label overrides applied to **every character of a given company** (see *Editing the printed labels*). |
| `personnages` | The list of characters. One badge per entry. |

---

## Character fields

### 1. Identity — always printed

| Key | Result on the badge |
|---|---|
| `compagnie` | Chooses the whole visual theme: colours, layout, wording, back-side design. |
| `nom` | Last name (also used in the output filename). |
| `prenom` | First name (also used in the output filename). |
| `profession` | Job title / function line. |
| `username` | Terminal login, printed in the access-code block. |
| `password` | Terminal password, printed next to the login. |
| `flavor` | A short quote or line printed on the **back** of the badge. |

Accepted values for `compagnie`: `weyland-yutani`, `seegson`, `prodigy`,
`lasalle` — plus common variants (e.g. `wy`).

### 2. Auto-generated fields — set them only if you want a specific value

The script invents these and always invents the **same** value for the same
character, so re-running it never changes an existing badge. Fill the key in to
pin the value yourself:

| Key | Result on the badge | If you leave it out |
|---|---|---|
| `id` | Employee number | A stable random matricule |
| `habilitation` | Clearance level, `0`–`5`, shown as a gauge (see below) | A stable random level |
| `division` (or `secteur`) | Division / sector line | Picked from that company's list |
| `site` | Posting / facility | Picked from that company's list |
| `groupe_sanguin` | Blood type — printed on the Lasalle badge and in the MRZ | Randomly assigned |
| `emis` / `exp` | Issue and expiry dates | Derived from `annee` |
| `serie` | Serial number | A stable random serial |

### 3. Logos

| Key | Where it appears |
|---|---|
| `logo_petit` | Small logo at the top of the **front** |
| `logo_grand` | Large logo in the middle of the **back** |

Paths to PNG / WEBP / JPG files. A **flat background is cut out automatically**
(black, white, paper…), so logos exported "as is" work without editing.

Lookup order when the key is missing: `./logos/<company>.png|webp|jpg`, then a
built-in stylised logo drawn by the script.

### 4. Photo — optional

`photo` is a path to an image. It gets cropped to the badge frame and recoloured
as a duotone in the company's palette.

| Value | Result |
|---|---|
| Missing or `""` | **No photo frame is drawn at all** — that area stays empty |
| Valid path | Cropped, duotone portrait |
| Path set but unreadable | A generic silhouette is used instead |

---

## Editing the printed labels

Every piece of fixed wording on the badge can be replaced. Two levels, the more
specific one wins:

1. **Whole company** — at the root of the JSON:
   ```json
   "textes_compagnies": { "wy": { "entete": "CORPORATE ACCESS" } }
   ```
2. **One character** — inside that character (overrides the company-level value):
   ```json
   "textes": { "entete": "SPECIAL CLEARANCE" }
   ```

### Available label keys

Not every company uses every key — a key a company doesn't print is simply
ignored.

| Key | What it labels |
|---|---|
| `raison` | Company legal name / corporate line |
| `entete` | Main header text |
| `sous_entete` | Sub-header under the main header |
| `l_nom` | The "Last name" caption |
| `l_prenom` | The "First name" caption |
| `l_fonction` | The "Function" caption |
| `l_identifiant` | The login caption |
| `l_habilitation` | The clearance caption |
| `l_id` | The employee-number caption |
| `l_division` | The division caption |
| `l_site` | The posting caption |
| `l_gs` | The blood-type caption |
| `l_emis` | The issue-date caption |
| `l_exp` | The expiry-date caption |
| `l_serie` | The serial-number caption |
| `code_titre` | Title above the login/password block |
| `propriete` | The "property of…" notice |
| `micro` | Microprinted security text |
| `bandeau` | Banner text — **Seegson** |
| `pied` | Footer line — **Prodigy** |
| `mrz_prefixe` | Prefix of the machine-readable zone — **Weyland-Yutani** |

Note that `l_*` keys rename the **caption**; the value beside it still comes from
the character fields in section 2.

### Variables inside labels

Label values can embed data with braces:

| Variable | Value |
|---|---|
| `{n}` | Clearance level |
| `{id}` | Employee number |
| `{site}` | Posting |
| `{division}` | Division |
| `{gs}` | Blood type |
| `{annee}` | Year |

```json
"l_habilitation": "QUARANTINE — LEVEL {n}"
```

---

## Going further

Inside `generateur_cartes.py`:

| Where | What you can change |
|---|---|
| `THEMES` | Default palettes and default wording per company |
| `DONNEES_COMPAGNIES` | The pools of divisions and postings used for random values |
| `*_recto` / `*_verso` functions | The actual layout of each side |
