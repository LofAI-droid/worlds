# Rave against the machine — afspraken tussen de bouwdelen

Gedeeld contract voor drie bouwdelen die tegelijk werken: **terrein** (Blender), **figuren** (Blender)
en **viewer** (three.js). Houd je hier exact aan; wijk je af, schrijf het hier bij.

## Sfeer (zie ook het moodboard-verslag in de opdracht)
Openlucht Goa/psytrance-feest bij nacht op een open plek in het bos. Half duister, spannend,
verleidelijk (suggestief, nooit expliciet), voor jonge volwassenen die willen losbreken.
**Vrij realistisch, niet Roblox-achtig**: echte PBR-texturen, organische vormen, geen dozenwereld.
Licht komt vooral **van achteren** (podium schijnt naar de menigte → silhouetten met randlicht),
dichte lage mist met zichtbare stralen. Palet: cyaan/teal, magenta/rood, warm oranje, UV-paars,
een vleugje zuurgroen, op bijna zwart/nachtblauw.

## Coördinaten en schaal
- Eenheid: meter. Blender Z-omhoog; glTF-export met +Y omhoog. Dus three.js `x = blender x`,
  `z = -blender y`, `y = blender z`.
- **Alles in `botsing.json` staat in three.js-coördinaten.**
- Oorsprong (0,0,0) = midden van de dansvloer. Grond is vlak op hoogte 0 binnen de open plek
  (lichte golving mag enkel buiten de speelzone, r > 45 m).
- Indeling (three.js x, z):
  | Zone | Plaats | Opmerking |
  |---|---|---|
  | Dansvloer | cirkel r ≈ 16 rond (0,0) | aarde/stro, omlijnd met LED-balken |
  | Hoofdpodium | midden (0, -24), breed ~16 m, diep ~8 m, vloer 1.2 m hoog | front kijkt naar +z (naar de menigte); truss erboven ~8 m hoog |
  | Reuzenboom | stam op (-20, -6) | kroon ~25 m breed, ~18 m hoog; van onderen aangelicht |
  | Chill-out | rond (24, 6) | tapijten, kussens, laag tentdoek, lampionnen |
  | Kampvuur | (-14, 22) | boomstammen als banken |
  | Chai-kraam | (16, 24) | kraam met lichtjes |
  | Ruïnemuur | rond (-34, 14), langs de bosrand | strijklicht |
  | String-art + paddenstoelen | bosrand, r 38–46 | |
  | Bos | ring r 42–110 | dicht genoeg om de rand te sluiten; speelgrens r = 44 |
- Speler start op (0, 30), kijkt naar het podium (richting −z).

## rave.glb (terrein) — gemaakt door `rave/blender/bouw_rave.py`
- Draco-compressie, texturen als JPG (max 1024 px, normal maps mogen 1024), totaal **< 15 MB**.
- Driehoeken: richtwaarde < 600k totaal. Bos met hergebruikte boommeshes (instancing of
  samengevoegde varianten).
- **Gloeiende materialen** heten `gloed_<groep>[_<kleur>]` en hebben emissive kleur + sterkte 1.
  De viewer stuurt hun sterkte. Groepen:
  - `gloed_led` — LED-balken rond de vloer (reageren op de beat)
  - `gloed_doek` — UV-doeken boven podium/vloer
  - `gloed_stringart`, `gloed_paddenstoel` — bosrand (traag ademend)
  - `gloed_lampion` — chill-out, chai-kraam (warm, rustig)
  - `gloed_vuur` — kampvuur (flakkert)
  - `gloed_scherm` — LED-wand/visuals achter de DJ (beat + drop)
  - `gloed_podium` — spots/blinders op de truss (drop)
- **Lichtankers**: lege objecten (Empties) met naam-prefix `licht_`, positie + richting
  (lokale −Z van de empty = schijnrichting, zoals een Blender-spot). Viewer maakt er lampen/stralen van:
  - `licht_spot_<n>` — spots op truss/podium, schijnen schuin naar de menigte (tegenlicht)
  - `licht_laser_<n>` — laserbronnen op de truss (6–8 stuks)
  - `licht_boom_<n>` — uplights aan de voet van de boom (magenta/oranje)
  - `licht_vuur` — kampvuur
  - `licht_blinder_<n>` — felle blinders achter de DJ, naar het publiek
  - `licht_rook_<n>` — plaatsen waar rook/mist opborrelt
  Geef elke empty een custom property `kleur` (hex, bv. `"#ff2fd0"`); die komt als glTF `extras` mee.
- Geen echte Blender-lampen in de glb nodig (viewer maakt ze zelf); voor renders mag je wel lampen gebruiken.

## botsing.json — ook door `bouw_rave.py`
```json
{
  "versie": 1,
  "grens": 44.0,
  "start": {"x": 0, "z": 30, "richting": 0},
  "vakken": [[x0, z0, x1, z1, hoogte], ...],
  "rondjes": [[x, z, straal, hoogte], ...],
  "zitplaatsen": [{"x":..,"z":..,"y":..,"h":..}],
  "dansers": [{"x":..,"z":..,"h":.., "zone": "vloer|podium|chill|vuur|rand"}],
  "dansvloer": {"x": 0, "z": 0, "r": 16},
  "podium": {"x0": -8, "z0": -28, "x1": 8, "z1": -20, "y": 1.2}
}
```
- `vakken` = rechthoeken zoals in Ministad (`[x0,z0,x1,z1,h]`, three.js), `rondjes` = cirkels
  (boomstammen, paaltjes). `h` in `zitplaatsen` = kijkrichting in radialen (zoals Ministad).
- `dansers`: ~60 plaatsen. ~40 op de dansvloer (dichter naar het podium toe), 2 op het podium
  (DJ + danser), rest verspreid bij chill-out, vuur en bosrand. `h` = kijkrichting (vloer: naar podium).

## figuren.glb — gemaakt door `rave/blender/bouw_figuren.py`
- Bron: Mixamo-FBX in `rave/blender/bronnen/mixamo/` (**nooit committen**, staat in .gitignore):
  `xbot.fbx` (personage + skelet), `house_1/2/3.fbx` (dansen, met huid), `backflip.fbx` (zonder huid).
- Inhoud: één geskinnede figuur **`danser_xbot`** (Mixamo-skelet, botnamen `mixamorig:*` of
  `mixamorig*`, schrijf de exacte namen hieronder), hoogte ≈ 1.75 m, voeten op y = 0, gecentreerd,
  kijkt naar **+z** in three.js. Geen wortelbeweging (ter plaatse).
- Animaties (glTF-clips) met exact deze namen: `house_1`, `house_2`, `house_3`, `backflip`,
  `staan` (zelfgemaakte rustige wiegpose, lus), `wiegen` (zacht meedeinen, lus). Lussen naadloos.
- Materiaal `figuur_huid`: donker, mat (bijna zwart met lichte glans voor randlicht). Viewer mag
  per kloon de kleur iets variëren.
- Accessoires als aparte meshes (niet geskinned), oorsprong op het hechtpunt:
  `acc_glowstick` (materiaal `gloed_glowstick`), `acc_halsband` (glow-ketting, `gloed_glowstick`),
  `acc_koptelefoon`, `acc_masker` (half gezichtsmasker). Viewer hangt ze aan botten:
  glowstick → rechterhand, halsband → nek, koptelefoon/masker → hoofd.
- Later komen echte Mixamo-mensen; het script moet dan met een lijst personages hetzelfde doen.
- Budget **< 8 MB**.
- Botnamen (in te vullen door figuren): `...`

## Viewer — `rave/index.html`, `rave/*.js`, `rave/stijl.css`
- Vertrekt van `ministad/wandel.js` (lopen, botsing, camera, kaart, aanraakbediening).
- three.js 0.170 via jsdelivr importmap (zoals Ministad).
- Beat: Spotify-embed (`https://open.spotify.com/embed/album/44TN3JC95d7tY2MHL3USay`) speelt via
  luidsprekers; pagina luistert met toestemming via microfoon (Web Audio AnalyserNode) en detecteert
  kicks + energie (opbouw/drop). Terugval: vast tempo 142 BPM + meetikken (toets `T`).
- Gedeeld ritme-object `ritme`: `{ beat (0..1 puls), bpm, fase: 'basis'|'opbouw'|'drop', energie }`.

## Mappen en bestanden
```
rave/
  AFSPRAKEN.md
  index.html  stijl.css  wandel.js  licht.js  ritme.js  dansers.js   (viewer)
  rave.glb  figuren.glb  botsing.json                                (export)
  blender/
    gereedschap.py           (kopie uit ministad, mag uitgebreid worden)
    bouw_rave.py  rave.blend  texturen/  voorbeeld-*.png   (terrein)
    bouw_figuren.py  figuren.blend  voorbeeld-figuren.png  (figuren)
    bronnen/                 (gitignored: Mixamo, gedownloade ruwe assets)
```
Scripts draaien vanuit `rave/`: `python3.11 blender/bouw_rave.py` (bpy is geïnstalleerd).
Niet committen of pushen — dat doet de coördinator.
