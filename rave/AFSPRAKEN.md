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
- Botnamen (65, Mixamo-standaard; in de glb `mixamorig:<Naam>`, in three.js na GLTFLoader
  **zonder dubbele punt**: `mixamorig<Naam>`, bv. `mixamorigHips`):
  `Hips`, `Spine`, `Spine1`, `Spine2`, `Neck`, `Head`, `HeadTop_End`,
  `RightShoulder`, `RightArm`, `RightForeArm`, `RightHand`,
  `RightHand{Thumb,Index,Middle,Ring,Pinky}{1,2,3,4}`, idem `Left…`,
  `RightUpLeg`, `RightLeg`, `RightFoot`, `RightToeBase`, `RightToe_End`, idem `Left…`.

### Stand van figuren.glb (door figuren ingevuld)
- Bestand ≈ 2.4 MB (Draco op de meshes — skinning getest in three.js 0.170, werkt; viewer heeft
  dus `DRACOLoader` nodig, zoals voor rave.glb). 30 fps.
- Knopen: `danser_xbot` (skelet, extras: `hoogte`, `fps`, `wiegen_bpm`, `clips` als JSON
  naam→duur), daaronder `danser_xbot_lijf` (SkinnedMesh, 24.8k punten, `figuur_huid`).
  Accessoires staan als losse knopen al **op hun plaats op de rustpose**.
- Clips (s): `house_1` 21.37, `house_2` 26.17, `house_3` 19.80 (Mixamo-lussen, volledig behouden,
  naad gecontroleerd), `backflip` 5.83 (géén lus: eindigt in de houding van `staan` beeld 0 → mooi
  overvloeien naar staan/wiegen), `staan` 4.00 (lus), `wiegen` 6.767 = **16 beats aan 141.87 BPM**
  (lus; beat valt op t = 0, 0.4229, …: diepste knik op de beat). Voor sync met `ritme.bpm`:
  `timeScale = ritme.bpm / 141.87`.
- Wortelbeweging is **al verwijderd in de glb**: de trage horizontale verplaatsing van de heup is
  eruit gefilterd (glijdend gemiddelde 1.5 s), het heupwiegen (±0.2–0.3 m in house, ±0.5 m tijdens de
  backflip) en alle verticale beweging blijven. De viewer hoeft de `Hips.position`-sporen niet meer
  plat te maken (dat bevriest het heupwiegen en laat de voeten meer glijden).
- Accessoires: extras `bot` (three.js-naam), `bot_gltf`, `positie` [x,y,z] m en `rotatie`
  [x,y,z,w] = lokale transformatie t.o.v. dat bot in three.js (getest: gelijk aan `bot.attach(acc)`
  in rustpose). Dus: `bot.add(acc); acc.position.fromArray(positie); acc.quaternion.fromArray(rotatie)`.
  | Accessoire | Bot (three.js) | positie | rotatie (x,y,z,w) | Materialen |
  |---|---|---|---|---|
  | `acc_glowstick` | `mixamorigRightHand` | (0, 0.0876, 0.025) | (-0.5, 0.5, -0.5, 0.5) | `gloed_glowstick` |
  | `acc_halsband` | `mixamorigNeck` | (0, 0.0283, 0) | (0.0609, 0, 0, 0.9981) | `gloed_glowstick` |
  | `acc_koptelefoon` | `mixamorigHead` | (0, 0.0805, -0.0022) | (0.0609, 0, 0, 0.9981) | `acc_kunststof` + `gloed_glowstick` (ringen) |
  | `acc_masker` | `mixamorigHead` | (0, 0.0749, 0.1425) | (0.0609, 0, 0, 0.9981) | `acc_masker` |
  Glowstick ligt dwars tegen de handpalm (de handen zijn in de Mixamo-dansen niet altijd gesloten).
  `gloed_glowstick`: emissive `#3dff7a`, sterkte 1 (viewer mag kleur/sterkte per kloon variëren).
- Meer personages: `PERSONAGES` bovenaan `bouw_figuren.py`; elk wordt `danser_<naam>` met dezelfde
  (geretargete) clips. Het eerste personage heeft de clipnamen hierboven; clips van latere
  personages heten `<naam>:<clip>` (anders botsen dezelfde botnamen in één glTF-animatie).

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
