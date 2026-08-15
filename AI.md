# AI.md — operator manual for bladebook's intake pipeline

## 1. You are the pipeline

If you're an AI agent — Claude, or any other capable model — reading this file
because someone pointed you at this repo: you *are* the intake pipeline.
There is no OCR service, no ML classifier, no "upload and wait" step. The
human shoots two photos per knife on their phone. Everything after that —
reading the box label, reading the birth card, deciding what steel/wood/date
those words mean, writing it into a seed script, running that script, running
the publish step, and reporting back in plain English — is your job.

This works because you can read handwriting and packaging shorthand and turn
it into structured data faster and more reliably than a human typing it into
a form, and because the schema is small enough to hold in your head. Nothing
in this repo requires Claude specifically. Any model with vision (to read the
photos) and the ability to run shell commands can do this end to end.

Read this whole file before you touch anything. Then work the loop in
Section 3.

## 2. System map

```
bladebook/
  db.py          SQLite schema + upserts (models, knives, events)
  photos.py      original photo archive + thumbnails
  export.py      public bundle builder (whitelist projection)
  routes.py      authed Flask API, mounted under /api/bladebook/
app.py           serves the three views + registers routes.py
scripts/
  seed_example.py   seed-list template — copy this pattern for real batches
  publish.py        regenerates the public bundle from the DB
html/
  index.html          uploader UI ("/")
  catalog/index.html  private catalog UI ("/catalog/")
  public/index.html   public index UI (copied into the published bundle)
tests/           pytest suite — run it after every batch
```

**Data directory** (`BLADEBOOK_DATA_DIR`, default `./data`):

```
data/
  bladebook.db              SQLite — models, knives, events tables
  originals/<TAG>/NNN.jpg   archived photo bytes, byte-for-byte, per tag
  originals/<TAG>/.seq      no-reuse counter — a deleted NNN is never reissued
  thumbs/<TAG>/NNN.jpg      best-effort small thumbnails for the upload UI
```

`<TAG>` is a knife's permanent identifier: `K01`, `K02`, … `K999`
(`bladebook/routes.py::_norm_tag` accepts 1–3 digits and zero-pads to two).
Tags are assigned once, at photo-upload time, and never reused.

**The three views** (served by `app.py`):

| Route | What it is | Auth |
|---|---|---|
| `/` | Uploader — phone-friendly tag stepper + camera picker, posts to `/api/bladebook/upload` | key required to browse existing tags/photos |
| `/catalog/` | Private catalog — the full record, every field | key required |
| `/public/` | Public index — whitelisted static bundle from `publish.py` | none, by design |

**Auth.** Every `/api/bladebook/*` route is gated by `BLADEBOOK_ADMIN_TOKEN`.
Callers pass it as `?key=<token>` (query string, what the browser UI uses —
stored in `localStorage` after the first paste) or as the
`X-Bladebook-Token` header. No token set in the environment means every
request is rejected (`bladebook/routes.py::_is_admin` returns `False` on an
empty token — there's no "auth disabled" mode).

**Publish is not live.** `/public/` is a static bundle written to disk by
`scripts/publish.py` (`bladebook/export.py::build_public`). Editing the DB
does not change what `/public/` shows until you run the publish step again.

## 3. The intake loop

Run this once per batch of photos the human hands you.

1. **Find what's new.** List `data/originals/*/` and compare tag names
   against what's already in the DB (`GET /api/bladebook/tags` with your
   token, or just read `data/originals/` directly if you're running
   locally). A tag with photos but no matching knife row is new work.
   Inside each new tag's directory, read the *actual* filenames — don't
   assume `001.jpg`, `002.jpg`. The `.seq` marker means a deleted shot's
   number is never reissued, so gaps (`001.jpg`, `003.jpg`) are normal and
   expected, not a sign a photo is missing.

2. **Read every photo.** The convention is two photos per knife: ① the box
   or packaging end-label, ② a spread shot showing the knife itself plus
   its birth card (and often a cloth, tools, or accessories). Occasionally
   there are extras — read those too; they sometimes carry a receipt or
   provenance detail.

3. **Decode into a seed list.** `scripts/seed_example.py` is the template:
   a flat Python list of `(tag, model_fields, knife_fields)` tuples, where
   `model_fields` is a dict for `db.upsert_model()` (family/model/generation/
   size/blade_shape/knife_type) and `knife_fields` is a dict for
   `db.upsert_knife()` (everything specific to that physical knife — steel,
   born_on, handle treatment, condition, and so on — see the column set in
   `bladebook/db.py::_KNIFE_COLS`). Copy an existing tuple as a template for
   field names. Set `hero_photo` to the spread-shot filename (e.g.
   `'002.jpg'`) — that's what publish uses as the public hero image.
   Don't add anything to `events` yourself beyond what `main()` already does
   (it logs a `photographed` event automatically); just get the knife/model
   fields right.

   **This is the one place people get bitten:** whatever list your entries
   live in has to be built — defined, appended to, or extended — *before*
   the `if __name__ == '__main__':` guard at the bottom of the script.
   Code placed after that guard runs too late: `main()` is already called
   by the time Python reaches it, so anything you add below it silently
   never seeds. If in doubt, put your new entries inline in the existing
   list, right next to the examples, above the guard.

4. **Seed, then publish:**

   ```bash
   python3 scripts/seed_example.py   # or your own copy of the seed script
   python3 scripts/publish.py
   ```

   Both read `BLADEBOOK_DATA_DIR` (and publish also reads
   `BLADEBOOK_PUBLIC_DIR`) from the environment — set them explicitly if
   you're not using the defaults (`./data`, `./public`), otherwise you'll
   write to a throwaway local directory instead of the real collection.
   Both scripts are idempotent: re-running with the same tag updates that
   knife's row rather than duplicating it. Note that `upsert_knife` only
   overwrites fields you pass — it never clears a field just because you
   left it out of the dict. If a value needs to go from something back to
   empty, that's a deliberate `UPDATE knives SET ... = NULL` by hand, not a
   re-seed.

5. **Run the test suite:**

   ```bash
   python3 -m pytest tests/ -q
   ```

   It should stay green. If you changed anything in `bladebook/` itself
   (rather than just adding seed data), this is what tells you the public
   export still can't leak a private field.

6. **Report back.** One line per knife: model, distinguishing material
   (wood/damascus pattern/finish), maker SKU if the box has one, and the
   born-on date. Call out the standouts — rare damascus patterns, unusual
   woods, left-handed pieces, anniversary or annual editions, anything that
   doesn't fit the common pattern. Flag anything you weren't confident
   about (illegible date, ambiguous steel) rather than guessing silently.

## 4. Decode conventions

**Box / packaging label.** Modern labels are typically three lines: line 1
is the model name including size, edition, and handedness if left-handed;
line 2 is the material or configuration (wood species, damascus, coating);
line 3 is the maker's SKU plus steel and a barcode. The SKU is usually
per-configuration, not per-individual-knife — two separate physical knives
built to the same configuration can share the same SKU (see "duplicate
configs are real" below). Older packaging often predates a printed SKU
entirely — expect a typed label with no SKU, or a dealer's own sticker
(record that as `acquired_from='<dealer name> (box sticker)'` when a
maker-side record is otherwise absent).

**Birth cards.** Many makers of custom or semi-custom knives ship a small
record card with each piece — sometimes called a "birth card." (Chris Reeve
Knives is one well-known example of this convention, but it's not unique to
any one maker, and this tool is not built around any single brand.) Card
formats tend to evolve over a product line's history: early cards are often
fully handwritten line-item forms; a middle era may add printed structure
but still rely on handwriting for the details; a later era often moves to a
checkbox/printed card where only a few fields stay handwritten — typically
the damascus smith and pattern name (if applicable), wood species, whether
it's left-handed, and the date. Whatever the card's era, the date on it is
the knife's `born_on` (schema default `born_on_precision='day'`,
`born_on_source='card'` — override precision if the card only gives a month
or year). Treat the card as authoritative over the box label when the two
disagree, especially for anything hardness-related: steel hardness varies
by both alloy and heat treat era, and the card's own note (when present) is
the one to trust over a generic assumption about that steel.

**Normalize vocabulary as you go.** Pick canonical spellings for recurring
values and use them consistently across every knife you seed — inconsistent
capitalization or spelling turns a searchable field into a source of missed
matches:
- Steel names: use the maker's own canonical form for the alloy (e.g. a
  consistent capitalization/hyphenation you settle on for the first knife
  and reuse thereafter). For a damascus blade, put `'Damascus'` in `steel`
  and put the smith's name and the pattern name in the separate
  `damascus_smith` / `damascus_pattern` fields — don't fold them into
  `steel` or `hardness_note`.
- Wood and other natural materials: lowercase, consistent naming
  (`box elder burl`, not `Box Elder Burl` on one knife and `boxelder`
  on the next).
- `handle_treatment`: pick a small fixed vocabulary and stick to it —
  something like `plain` / `carbon-fiber` / `graphic` / `inlay` /
  `custom` covers most collections; whatever set you choose, reuse the
  exact strings.
- `surface_finish`: same idea — `polished`, `sandblast`, `cerakote`, etc.,
  spelled the same way every time.
- Special/annual/anniversary editions: put a short canonical label in
  `special_edition` (append ` LH` if left-handed) rather than describing it
  in prose in `notes_public`.

## 5. Rails

- **Never commit the owner's data.** `data/` and `/public/` are already
  gitignored — leave them that way. That means the SQLite DB, every
  archived original photo, and the generated public bundle never go into
  version control. Only code (schema, scripts, HTML, tests, docs) belongs
  in git. If you ever find yourself about to `git add data/` or a specific
  knife's photo, stop.
- **Never write price or private data into anything public-facing.** The
  public export (`bladebook/export.py::_PUBLIC_FIELDS`) is a whitelist, not
  a blocklist — a field only reaches `/public/` if it's explicitly listed
  there. `price_paid`, `acquired_from`, `location`, `notes_private`, and
  `condition_note` are deliberately absent from that list and must stay
  that way. `asking_price` is the one field that's conditionally public,
  and only when `sale_status == 'for_sale'`. `tests/test_export.py` is the
  proof this holds — if you ever touch `export.py`, re-run the suite before
  you trust the change, don't eyeball it.
- **The tag is the only key that matters.** Two knives can have the exact
  same model, generation, size, steel, and even the same SKU on the box —
  that's not a duplicate, that's two real knives. Never merge two tags or
  treat a repeated configuration as a data-entry mistake.
- **When a record disagrees with itself, flag it — don't silently pick.**
  If a card date is illegible, if the box says one wood and the card says
  another, if an external tracking sheet the owner also keeps doesn't match
  what the photos show — say so in your report and leave a note (e.g. in
  `notes_private` or the report itself) rather than guessing which source
  wins.
