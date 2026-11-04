# furryp — Spécification v1

> Document de référence du projet. Il est **normatif** : le code DOIT s'y conformer.
> Mots-clés : **DOIT** / **NE DOIT PAS** = obligatoire ; **DEVRAIT** = recommandé ; **PEUT** = optionnel.
> Les décisions prises par défaut sont listées au §15 (« Arbitrages ») avec un identifiant `Axx`.
> **Priorité à ruff** : furryp est aligné sur la philosophie de ruff. Si cette spécification diverge du comportement réel de ruff, ou si elle est insuffisante pour arbitrer un comportement, ruff a la priorité (A39). Le comportement est vérifié sur ruff, puis reporté ici. **Le but reste une bonne qualimétrie** : suivre ruff ne dispense pas de mesurer l'effet réel d'un choix, et un choix qui nuit à la qualité des mesures est signalé à l'utilisateur, chiffres à l'appui (A39).

## Sommaire

1. Vision
2. Périmètre
3. Contraintes techniques
4. Interface en ligne de commande
5. Sortie terminal (format exact)
6. Suppression des diagnostics : `foqa`
7. Corrections automatiques
8. Configuration JSON
9. Architecture
10. Définitions communes
11. Catalogue des règles
12. Rapport HTML d'audit
13. Tests et critères d'acceptation
14. Phases de réalisation
15. Arbitrages pris par défaut

---

## 1. Vision

`furryp` est un linter Python **local**, **sans dépendance** (bibliothèque standard uniquement), qui reprend l'usage, les options principales et la sortie terminal de **ruff**.
Il vérifie des règles de **taille**, de **complexité** (Halstead, cognitive) et de **conception** (complexité et attributs des classes, contrats de couches, loi de Déméter).
Il sait **retirer** les directives devenues inutiles, **geler** la dette existante et produire un **rapport HTML d'audit** de type SonarQube.

## 2. Périmètre

### 2.1 Dans le périmètre (v1)

- Commande `furryp check [PATHS]...` (aussi `python -m furryp check ...`).
- Commande `furryp rule <CODE|NOM>` / `furryp rule --all` : fiche d'une règle (§4.6).
- Options de `check` : `--config`, `--select`, `--extend-select`, `--ignore`, `--fix`, `--diff`, `--statistics`, `--show-settings`, `--exit-zero`, `--add-foqa`, `--report-html`. Options globales : `--version`, `-h/--help`.
- Sortie terminal au format ruff « full », avec le code de la règle entre crochets et un `help:` systématique (§5, §11.0).
- Suppression par commentaire `# foqa` et détection des directives inutiles (§6, FUR001).
- Corrections automatiques, **sûres uniquement** (§7).
- Configuration par fichier JSON (§8).
- 11 règles (§11) et un rapport HTML (§12).

### 2.2 Hors périmètre (v1) — NE DOIT PAS être implémenté

- `--output-format` et tout autre format de sortie (json, github, junit…).
- `--unsafe-fixes`, et toute correction susceptible de changer le comportement du code.
- Couleurs ANSI dans le terminal.
- `furryp format`, `furryp server` (LSP), `--watch`, cache, `--show-files`, `--isolated`, `-q/--quiet`, `-o/--output-file`, `--fix-only`, `--exit-non-zero-on-fix`.
- Options CLI d'inclusion/exclusion de chemins (configuration JSON uniquement).
- Lecture de `.gitignore`.
- Configuration hiérarchique (un seul fichier de configuration par exécution).
- Analyse d'imports transitive (contrats de couches : imports directs seulement).
- Parallélisme (multiprocessing, sous-interpréteurs, free-threading).
- Lecture de l'entrée standard.
- Ce que ruff contrôle déjà : complexité de McCabe d'une fonction (C901), espaces en fin de ligne (W291, W293), lignes vides, tri des imports (I001). furryp NE DOIT jamais signaler le style que `ruff format` produit. Une mesure, elle, peut changer quand `ruff format` replie du code : une fonction repliée peut dépasser un seuil (A72).

## 3. Contraintes techniques

- **Python 3.14** minimum (`requires-python = ">=3.14"`).
- **Exécution : bibliothèque standard uniquement.** Aucune dépendance tierce, ni à l'exécution ni pour les tests (tests en `unittest`).
- Build : `uv_build`, le backend natif de uv (dépendance de build uniquement), avec une contrainte de version alignée sur le uv installé. Arborescence plate déclarée par `[tool.uv.build-backend]` → `module-root = ""` ; les fichiers non Python du package (gabarits, fiches `rules/docs/`) sont embarqués sans configuration. Version unique : `version` statique dans `pyproject.toml` ; `furryp/__init__.py` expose `__version__` (constante) et un test vérifie que les deux sont égales.
- **Package**, pas script : arborescence `furryp/` à la racine du dépôt (§9.1), exécutable sans installation par `python -m furryp` depuis la racine. Point d'entrée console `furryp = "furryp.cli.app:main"`.
- **Métadonnées** : `authors = [{ name = "skire666" }]`, `license = "Unlicense"` (identifiant SPDX, PEP 639), `license-files = ["LICENSE"]` ; le fichier `LICENSE` (texte de l'Unlicense) est fourni à la racine (A38).
- **Environnement de développement : uv.** `.python-version` = `3.14`, `uv sync` crée `.venv` et installe furryp en mode éditable, toutes les commandes passent par `uv run …`, `uv.lock` est versionné. Aucune dépendance déclarée : ni `dependencies`, ni groupe de dépendances de développement. `uv add`, `uv pip install` et `pip install` sont interdits dans ce dépôt ; les outils externes ponctuels (ruff) passent par `uvx`.
- **Windows est une plateforme de premier rang** (développement sous Windows + VS Code) : séparateurs de chemins natifs à l'affichage, fichiers CRLF, encodage de console (§5.7).
- **furryp DOIT passer ses propres règles** : `python -m furryp check furryp` DOIT sortir avec le code 0, avec la configuration du dépôt (§9.4). Pendant le développement, cette contrainte s'applique aux règles déjà implémentées.
- Annotations de type complètes sur toutes les fonctions. Dataclasses `frozen=True, slots=True` pour les objets valeur.
- **Pièges Python 3.14** (le modèle de code est souvent entraîné sur du code plus ancien) :
  - `ast.Num`, `ast.Str`, `ast.Bytes`, `ast.NameConstant`, `ast.Ellipsis` **n'existent plus** : utiliser `ast.Constant` uniquement.
  - `except A, B:` sans parenthèses est valide (PEP 758) ; `except*` produit `ast.TryStar`.
  - t-strings (PEP 750) : nœuds `ast.TemplateStr` / `ast.Interpolation`, tokens `TSTRING_START` / `TSTRING_MIDDLE` / `TSTRING_END`. Les f-strings produisent `FSTRING_START` / `FSTRING_MIDDLE` / `FSTRING_END` (depuis 3.12).
  - `ast` donne `col_offset` / `end_col_offset` **en octets UTF-8**, pas en caractères (§10.4).
  - Les annotations sont évaluées de façon différée (PEP 649) : ne pas ajouter `from __future__ import annotations`.
  - `PurePath.full_match()` gère `**` (depuis 3.13) : l'utiliser pour les motifs de chemins.

### 3.1 Entrées/sorties : encodages et fins de ligne

Sous Windows, Python 3.14 utilise encore l'encodage local (cp1252 sur un poste français) pour tout fichier ouvert sans `encoding=` : le mode UTF-8 ne devient le défaut qu'avec Python 3.15 (PEP 686 ; `sys.flags.utf8_mode` vaut 0 en 3.14 et 1 en 3.15). furryp NE DOIT donc jamais dépendre de l'encodage par défaut, ni du mode UTF-8 (`PYTHONUTF8`). Le même code doit se comporter à l'identique sous Windows, Linux et macOS.

| Fichier | Lecture | Écriture |
|---|---|---|
| Sources `.py` analysées | En **octets**, puis `tokenize.detect_encoding` : UTF-8 par défaut, BOM et déclaration `# -*- coding: … -*-` respectés, jamais la locale. Décodage par `bytes.decode` : aucune traduction des fins de ligne. | `path.write_bytes(texte.encode(encodage))` avec l'encodage détecté (§7.2) : encodage, BOM et fins de ligne préservés. |
| `furryp.json` | `encoding="utf-8-sig"` (UTF-8, BOM des éditeurs Windows toléré). | — |
| `pyproject.toml` | `tomllib.load` sur un fichier ouvert en `"rb"`. | — |
| Gabarits du rapport, fiches `rules/docs/` | `read_text(encoding="utf-8")`. | — |
| Rapport HTML | — | `encoding="utf-8"`, `newline="\n"` (fichier identique sur toutes les plateformes). |
| stdout / stderr | — | Reconfigurés en `encoding="utf-8", errors="replace", newline="\n"` (§5.7). |

- **Interdit** : `open()`, `Path.open()`, `Path.read_text()`, `Path.write_text()`, `Traversable.read_text()` ou `io.TextIOWrapper` sans `encoding=` explicite ; toute écriture en mode texte sans `newline=` explicite. Un test le vérifie (§13).
- Pour les sources, « toujours UTF-8 » est appliqué via `tokenize.detect_encoding`, qui fait exactement ce que fait l'interpréteur : UTF-8 par défaut (PEP 3120), BOM et déclaration d'encodage respectés (PEP 263).
- Chemins : affichage avec `os.sep`, comparaison des motifs en POSIX (§8.5) ; aucun séparateur `\` ou `/` codé en dur, uniquement `pathlib`.

## 4. Interface en ligne de commande

### 4.1 Synopsis

```
furryp check [PATHS]... [OPTIONS]
furryp rule <CODE|NOM> [--config PATH]
furryp rule --all [--config PATH]
furryp --version
```

`python -m furryp ...` est équivalent. `PATHS` : fichiers ou dossiers ; défaut `.`. Les dossiers sont parcourus récursivement (§8.5).

### 4.2 Options de `check`

| Option | Effet |
|---|---|
| `--config PATH` | Utilise ce fichier JSON au lieu de la découverte automatique (§8.1). |
| `--select RULES` | Remplace la sélection de la configuration. `RULES` = liste séparée par des virgules de codes, préfixes de code ou noms (§4.5). Répétable. |
| `--extend-select RULES` | Ajoute à la sélection. Répétable. |
| `--ignore RULES` | Retire de la sélection. Répétable. |
| `--fix` | Applique les corrections (toutes sûres, §7) et écrit les fichiers. |
| `--diff` | N'écrit rien : affiche le diff unifié des corrections. |
| `--statistics` | Affiche le décompte par règle au lieu des diagnostics (§5.4). |
| `--show-settings` | Affiche la configuration effective et quitte sans analyser (§5.5). |
| `--exit-zero` | Code de sortie 0 même s'il reste des violations (pas en cas d'erreur). |
| `--add-foqa` | Ajoute un `# foqa` sur chaque violation existante, écrit les fichiers et quitte (§6.1). |
| `--report-html PATH` | Génère le rapport HTML (§12). N'écrit rien sur la sortie standard. |

Comme ruff 0.17.3 (vérifié, A70), une option s'écrit en entier : `--stat` ou `--sel` sont refusés (code 2).

### 4.3 Combinaisons interdites

Ces combinaisons DOIVENT produire une erreur d'usage (code 2) :

- `--add-foqa` avec `--fix`, `--diff`, `--statistics`, `--show-settings` ou `--report-html` ;
- `--report-html` avec `--fix`, `--diff`, `--statistics` ou `--show-settings` ;
- `--statistics` avec `--fix` ou `--diff` ;
- `--show-settings` avec `--fix`, `--diff` ou `--statistics`.

`--fix` + `--diff` est permis et équivaut à `--diff` (comme ruff).

### 4.4 Codes de sortie

| Code | Signification |
|---|---|
| 0 | Aucune violation restante (ou `--exit-zero`) ; `--diff` sans aucun changement ; `--add-foqa` terminé ; `furryp rule` réussi. |
| 1 | Au moins une violation restante, ou `--diff` avec au moins un changement. |
| 2 | Erreur d'usage, de configuration, d'écriture du rapport, règle inconnue pour `furryp rule`, ou erreur interne. |

Une erreur interne sur un fichier (exception dans une règle) est affichée sur stderr (`error: Failed to check {path}: {exception}`), l'analyse continue sur les autres fichiers, et le code final est 2.
Les messages d'erreur vont sur **stderr**, préfixés par `error: `.

Pour un usage direct en CI (comportement vérifié sur ruff 0.16.9) :

- **Priorité** : 2 l'emporte sur 1 ; `--exit-zero` ne masque jamais 2.
- La règle vaut pour toutes les options d'analyse : `--statistics` et `--report-html` sortent aussi en 1 s'il reste des violations.
- **Chemin passé en argument inexistant, ou fichier illisible** : diagnostic FUR000 `Failed to read file: …` en `{path}:1:1`, donc code 1 (comme `E902` chez ruff). Une faute de frappe dans un chemin de CI ne donne pas un faux succès.
- **Dossier impossible à lister** (droits insuffisants), passé en argument ou rencontré pendant le parcours : `warning: Encountered error: {path}: {raison}` sur stderr, l'analyse continue, et le code de sortie n'en dépend pas (comme ruff 0.17.3, qui avertit sans échouer ; furryp ajoute le chemin du dossier). `{raison}` est le message du système.
- **Aucun fichier Python trouvé** (ni chemin inexistant, ni dossier illisible) : `warning: No Python files found under the given path(s)` sur stderr, puis `All checks passed!` (rien avec `--statistics`, §5.4), code 0 (comme ruff).
- Sortie sans couleur, sans interaction, déterministe et en UTF-8 : `furryp check` s'utilise tel quel dans un pipeline (exemples dans le README).

### 4.5 Sélection des règles

- Chaque règle a un **code** (`FUR101`) et un **nom** (`function-too-long`). Partout où une règle est référencée (CLI, configuration, `foqa`), les deux formes DOIVENT être acceptées.
- Un **préfixe de code** sélectionne une famille : `FUR` = toutes les règles, `FUR4` = `FUR4xx`, `FUR40` = `FUR400` à `FUR409`.
- Un identifiant inconnu est une erreur d'usage (code 2) avec suggestion (`difflib.get_close_matches`). En ligne de commande, comme ruff 0.17.3 (vérifié, A70), un élément vide ou entouré de blancs est un identifiant inconnu : `--select ""`, `--select FUR403,`, `--ignore "FUR403, FUR401"`. Sinon `--select "$RULES"` avec une variable vide ne sélectionnerait rien et passerait.
- Sélection effective d'un fichier = (`--select` si fourni, sinon `select` de la configuration) ∪ `extend-select` (configuration + CLI) − `ignore` (configuration + CLI) − `per-file-ignores` applicables. **`ignore` l'emporte toujours** sur `select`.
- `FUR000` (`invalid-syntax`) est toujours actif et ne peut pas être ignoré.

### 4.6 `furryp rule`

Équivalent de `ruff rule`. Affiche la fiche d'une règle, pour qu'un humain ou un agent comprenne la règle **avant** de corriger.

- `furryp rule FUR101` (forme recommandée) ou `furryp rule function-too-long`. Identifiant inconnu : erreur d'usage (code 2) avec suggestion.
- `furryp rule --all` : toutes les fiches, triées par code, séparées par une ligne `---`.
- La configuration est découverte comme pour `check` (§8.1), `--config` accepté : la fiche affiche les valeurs **effectives** des options.
- Sortie Markdown, en anglais, sur stdout, code 0. Gabarit :

~~~
# function-too-long (FUR101)

Category: size · Scope: line · Fix: not available

## What it measures
## Why it matters
## Options (furryp.json → rules.function-too-long)
- max-lines = 30 (default: 25)
## How to fix it well
## What not to do
## Example
(code « flagged », puis code « fixed »)
~~~

- Les parties rédigées sont des fichiers `furryp/rules/docs/<CODE>.md` (chargés via `importlib.resources`, `read_text(encoding="utf-8")`) ; la ligne d'en-tête et la section Options sont générées depuis le registre et la configuration effective.
- Chaque fiche DOIT contenir toutes les sections du gabarit. L'exemple « flagged » DOIT déclencher la règle et l'exemple « fixed » NE DOIT PAS la déclencher (vérifié par les tests).
- « What not to do » liste les contournements connus de la règle (ceux du README §4).

## 5. Sortie terminal (format exact)

### 5.1 Diagnostic

Exemple de référence (chemins Windows) :

```
unused-foqa [FUR001] [*]: Unused `foqa` directive (unused: `FUR102`)
   --> __src__\main.py:101:26
    |
 99 |     base = os.environ.get("LOCALAPPDATA", str(Path("~").expanduser()))
100 |     path_browser = str(Path(base) / C_APP_NAME / "ms-playwright")
101 |     return path_browser  # foqa:FUR102
    |                          ^^^^^^^^^^^^^
help: Remove unused `foqa` directive
    |
100 |     path_browser = str(Path(base) / C_APP_NAME / "ms-playwright")
    -     return path_browser  # foqa:FUR102
101 +     return path_browser
    |

function-too-long [FUR101]: Function `get_args_for_stealth` has too many lines of code (31 > 26)
   --> __src__\services\browser_playwright_service.py:114:9
    |
112 |             self._wire_page_crash_listener(page)
113 |
114 |     def get_args_for_stealth(self) -> list[str]:
    |         ^^^^^^^^^^^^^^^^^^^^
115 |         # Resolve to absolute path — Chromium executable is not Python, so relative paths are unsafe.
116 |         ext_path = str(Path(self._chromium_extensions_dir).resolve())
    |
help: Long functions are hard to read and test; consider splitting this one

Found 2 errors.
[*] 1 fixable with `--fix`.
```

Règles de rendu (`W` = nombre de chiffres du plus grand numéro de ligne affiché dans l'extrait) :

1. **En-tête** : `{name} [{code}]: {message}` ; si le diagnostic a une correction : `{name} [{code}] [*]: {message}` (A06). Le nom sert à lire, le code sert à `foqa`, `--select` et `furryp rule`.
2. **Flèche** : `" " * W + "--> " + "{path}:{line}:{column}"`. `line` et `column` sont 1-indexés, la colonne est comptée en **caractères** (§10.4).
3. **Gouttière vide** : `" " * (W + 1) + "|"`.
4. **Ligne de source** : `f"{lineno:>{W}} | {texte}"` ; si le texte est vide, la ligne se termine par `|` sans espace final.
5. **Ligne de soulignement** (span sur une ligne) : gouttière vide + `" "` + espaces jusqu'à la colonne de début + `^` × longueur, minimum 1, insérée juste après la ligne du span. Cette colonne et cette longueur sont des **largeurs d'affichage**, comme chez ruff (A57) : 2 pour un caractère large (`east_asian_width` `W` ou `F`), 0 pour une marque combinante ou un caractère de format (catégories `Mn`, `Me`, `Cf`), 1 sinon.
   **Span sur plusieurs lignes**, comme ruff : toutes ses lignes sont affichées, et chaque ligne de l'extrait reçoit une marge de 2 caractères entre `| ` et son texte. Si seuls des blancs précèdent le début du span, sa première ligne a la marge `/ ` ; sinon, elle est suivie de `{gouttière}  ` + `_` × (colonne de début) + `^`. Les lignes suivantes du span ont la marge `| `, et la dernière est suivie de `{gouttière} |` + `_` × (colonne du dernier caractère) + `^`.
6. **Contexte** : 2 lignes avant le début et 2 lignes après la fin du span, bornées au fichier, puis **retrait des lignes vides (ou blanches) aux deux extrémités** de la fenêtre (les lignes vides internes sont conservées, cf. ligne 113 ci-dessus).
7. **Caractères invisibles du texte affiché**, comme ruff (A57) : une tabulation devient 4 espaces ; un contrôle `U+0000` à `U+001F` son pictogramme (`U+2400` + code, `␌` pour un saut de page) ; `U+007F` devient `␡` ; le liant `U+200D` est retiré ; un contrôle bidirectionnel (`U+202A` à `U+202E`, `U+2066` à `U+2069`) devient `U+FFFD`. La position du soulignement tient compte de ces remplacements.
8. Après l'extrait : une gouttière vide **seulement si sa dernière ligne est une ligne de source** (après un soulignement, rien, comme ruff), puis **toujours** `help: {help}` (contrat du §11.0).
9. Une ligne vide sépare deux diagnostics et précède le pied de page.
   **Diff de la correction**, comme ruff : si le diagnostic a une correction, le `help:` est suivi de son diff, entre deux gouttières vides. Les lignes sont comparées entières, avec **une** ligne de contexte autour de chaque changement. Une ligne conservée s'écrit `{n:<W} | {texte}`, une ligne ajoutée `{n:<W} + {texte}`, une ligne retirée `{" " * W} - {texte}` ; `n` est le numéro dans le texte corrigé, aligné à gauche, et `W` le nombre de chiffres du dernier numéro affiché. Une ligne vide ne garde pas d'espace final ; une ligne qui change est retirée puis ajoutée ; les tabulations restent telles quelles, et seuls `U+0007`, `U+0008`, `U+001B` et `U+007F` sont remplacés (`␇`, `␈`, `␛`, `␡`). Jusqu'à 4 lignes identiques entre deux changements sont affichées ; au-delà, seule une ligne de contexte reste de chaque côté, et une ligne de 80 tirets remplace les autres. Rien ne s'affiche si la correction ne change rien. `--diff`, `--statistics` et `--add-foqa` n'affichent pas de diagnostics, donc pas ce diff.
10. **Chemin** : relatif au répertoire courant si le fichier est sous ce répertoire, absolu sinon ; séparateurs **natifs** (`os.sep`).
11. **Ordre** : par chemin affiché, puis ligne, puis colonne, puis code.
12. **Pas d'extrait** : source illisible (FUR000 de lecture ou de décodage), ou span vide en 1:1, qui vise tout le fichier (FUR201, comme `0..0` chez ruff pour D100). Ni gouttière ni extrait : l'en-tête, la flèche (`:1:1`), puis `help:`. Aucun numéro de ligne n'est affiché, donc `W` = 0 : la flèche s'écrit `--> {path}:1:1`, sans retrait (comme ruff).

**Comparaison avec ruff 0.17.3.** Périmètre : les 655 fichiers `*.py` de `Lib` (Python 3.14.8, hors `site-packages`), fichier par fichier, avec `ruff check --isolated --no-cache --select ALL --unsafe-fixes --exit-zero`. Les spans et les corrections viennent de ruff : seul le rendu est comparé, au caractère près.

- **Extraits** : 119 841 identiques sur 120 015. Les 174 autres : 163 que ruff raccourcit par `…` (lignes longues ou bloc très indenté), ce que furryp ne fait pas (A54), et 11 qui portent une annotation secondaire, qu'aucune règle de furryp ne produit.
- **Diffs** : 59 130 identiques sur 59 324. Les 194 autres, où ruff et `difflib` alignent différemment les mêmes changements : déplacement d'imports ou de noms (I001 81, TC 15, RUF022 et RUF023 9), extraction d'un message (EM 78), bloc réindenté (RET 5, PLR5501 5), D413 1. Aucune correction de furryp ne déplace ni ne réindente de code (A21).

### 5.2 Pied de page

- Aucun diagnostic : `All checks passed!` (rien avec `--statistics`, §5.4)
- Sinon : `Found {n} error{s}.` (`1 error`, `2 errors`), puis, si au moins un diagnostic affiché a une correction : ``[*] {fixable} fixable with `--fix`.``
- Après `--fix` : les diagnostics **restants** sont affichés, puis `Found {total} error{s} ({fixed} fixed, {remaining} remaining).` si au moins une correction a été appliquée, sinon `Found {remaining} error{s}.` (comme ruff 0.17.3), puis la ligne `[*]` calculée sur les restants. Si `total = 0` : `All checks passed!`.

### 5.3 `--diff`

Format de ruff 0.17.3 (vérifié) :

- Pour chaque fichier modifié, dans l'ordre des chemins affichés : `difflib.unified_diff` avec `fromfile` = `tofile` = chemin affiché (3 lignes de contexte), lignes avec leur fin de ligne d'origine (`\r\n` compris) ; une dernière ligne sans fin de ligne est suivie de `\ No newline at end of file` ; une ligne vide suit chaque fichier.
- Puis : `Would fix {n} error{s}.` (`n` = nombre de corrections appliquées) ; aucun changement : **rien** n'est affiché.
- Aucun diagnostic n'est affiché, pas même FUR000 (chemin inexistant), et aucun avertissement sur ce chemin (ceux des directives restent, §6) : c'est le comportement de ruff 0.17.3 quand E902 est sélectionné, ce qui est le cas par défaut, et FUR000 est toujours actif (A60). Code de sortie : 1 s'il y a au moins un changement, 0 sinon ou avec `--exit-zero` ; 2 en cas d'erreur.
- Aucun fichier n'est écrit.

### 5.4 `--statistics`

Une ligne par règle ayant au moins une violation, triées par nombre décroissant puis par code :

```
{count:>N}\t{code}\t{marker}{name}
```

`N` = largeur du plus grand compte ; `marker` = `[*] ` si au moins une violation de la règle est corrigeable, sinon `[ ] ` ; **aucun marqueur** si aucune règle du tableau n'est corrigeable. Le pied de page du §5.2 suit directement, sans ligne vide. **Aucune violation : rien n'est affiché**, pas même `All checks passed!`. Tout ceci comme ruff 0.17.3 (A61).

### 5.5 `--show-settings`

```
Project root: {chemin absolu}
Config file: {chemin absolu | (none, defaults)}
{configuration effective en JSON, indent=2, clés triées, toutes les valeurs par défaut incluses, sélection CLI appliquée}
```

Le JSON affiché DOIT être réutilisable tel quel comme fichier de configuration. Code de sortie 0.

### 5.6 Rapport HTML

Avec `--report-html PATH` : rien sur stdout ; les erreurs vont sur stderr ; code de sortie calculé comme pour `check` (0/1), ou 2 si le rapport ne peut pas être écrit (`error: Failed to write report {path}: {raison}`). Comme `--output-file` de ruff 0.17.3 (vérifié, A66) : les dossiers parents manquants sont créés ; une erreur de configuration n'écrit aucun fichier ; sans fichier Python, l'avertissement habituel va sur stderr, le rapport est écrit et le code est 0.

### 5.7 Robustesse console

Au démarrage, `sys.stdout` et `sys.stderr` DOIVENT être reconfigurés avec `encoding="utf-8", errors="replace", newline="\n"`. Sans `newline`, Windows écrirait `\r\n` : la sortie est faite des mêmes octets sur toutes les plateformes, comme celle de ruff. La sortie est ainsi en UTF-8 sur toutes les plateformes, y compris redirigée vers un fichier ou un journal de CI (sous Windows, Python 3.14 utiliserait sinon cp1252, §3.1), et l'affichage de sources non ASCII ne lève jamais `UnicodeEncodeError`.

## 6. Suppression des diagnostics : `foqa`

- **Instruction** : un commentaire `# foqa:FUR101,FUR403` supprime ces règles pour tous les diagnostics dont la **ligne de début appartient à la même ligne logique** que le commentaire. Ligne logique = suite de tokens terminée par un token `NEWLINE` : une instruction simple, ou l'en-tête d'une instruction composée jusqu'à son `:`. Codes ou noms acceptés, séparés par des virgules, espaces libres. Un `# foqa` seul supprime toutes les règles sur cette ligne logique (déconseillé).
  - *Pourquoi la ligne logique* : quand une ligne dépasse la longueur maximale, `ruff format` replie l'instruction et déplace le commentaire final sur sa dernière ligne (`):  # foqa:FUR101`). Vérifié avec ruff 0.16.9. Rattachée à la ligne logique, la directive reste valide (A31).
- **Fichier** : `# furryp: foqa` sur sa propre ligne, éventuellement après un autre commentaire, supprime tout le fichier ; `# furryp: foqa:FUR102,FUR201` supprime ces règles pour tout le fichier. Des blancs sont admis autour du premier `:`. Indispensable pour les règles de portée `file` (§11). Après du code, elle n'a aucun effet et un avertissement le dit.
- Détection uniquement sur les tokens `COMMENT` (via `tokenize`), jamais par recherche textuelle : un `# foqa` dans une chaîne ne compte pas. Le mot-clé `foqa` est insensible à la casse, pas `furryp`. La directive peut suivre un autre commentaire (`# raison  # foqa:FUR101`) et cohabiter avec `# noqa`.
- **Forme, comme `# noqa` dans ruff 0.17.3** (vérifié, A71). Dans un commentaire, seul le **premier** mot-clé de chaque forme (`foqa`, `furryp: foqa`) compte, même si ce qui le suit est invalide : `# foqa.  # foqa:FUR101` ne supprime rien. Après ce mot-clé :
  - un blanc, un `#` ou la fin du commentaire : directive globale, quel que soit le texte qui suit (`# foqa raison`, et aussi `# foqa FUR101`) ;
  - `:` (blancs admis autour), puis une liste d'identifiants séparés par des virgules ou des blancs. Un identifiant est un code (`[A-Z]+[0-9]+`, connu ou non) ou le nom d'une règle existante (§4.5). La liste s'arrête au premier mot qui n'en est pas un : `# foqa:FUR101 raison` et `# foqa:FUR101,raison,FUR102` ne nomment que `FUR101` ;
  - tout autre caractère collé au mot-clé ou à un identifiant, une liste vide ou qui ne commence pas par un identifiant : **la directive est invalide**. Elle ne supprime rien, FUR001 ne la signale pas, et un avertissement le dit. Exemples : `` # foqa` ``, `# foqa.`, `# foqa-x`, `# foqa:`, `# foqa:fur101`, `# foqa:FUR101;`, `# foqa:FUR101 FUR102x`.
- **Avertissements**, comme ruff 0.17.3 (vérifié, A71) : sur stderr, dans tous les modes, que la règle concernée soit sélectionnée ou non, sans effet sur le code de sortie.

| Cas | Avertissement |
|---|---|
| Directive invalide | ``warning: Invalid `# foqa` directive on {path}:{line}: {raison}`` ; forme de fichier : ``warning: Invalid `# furryp: foqa` directive at {path}:{line}: {raison}`` |
| Caractère collé au mot-clé | `{raison}` = ``expected `:` followed by a comma-separated list of codes (e.g., `# foqa:FUR101,FUR403`).`` |
| Liste vide | `{raison}` = ``expected a comma-separated list of codes (e.g., `# foqa:FUR101,FUR403`).`` |
| Caractère collé à un identifiant | `{raison}` = ``expected code to consist of uppercase letters followed by digits only (e.g. `FUR101`)`` |
| Virgule sans code avant elle (`FUR101,,FUR102`, `FUR101 , FUR102`) : la directive reste valide, un avertissement par virgule | `warning: Missing or joined rule code(s) at {path}:{line}: expected rule code between commas` |
| Codes collés (`FUR101FUR102`) : la directive reste valide et nomme les deux | `warning: Missing or joined rule code(s) at {path}:{line}: expected comma or space delimiter between codes` |
| Directive de fichier après du code | ``warning: Unexpected `# furryp: foqa` directive at {path}:{line}. File-level suppression comments must appear on their own line. For line-level suppression, omit the `furryp:` prefix.`` |

  Ceux des directives de fichier viennent d'abord. Ils sont écrits à chaque lecture du fichier : `--fix` et `--diff` les répètent à chaque passe, tant que la directive est là. Un fichier qui ne se tokenise pas n'a aucune directive, donc aucun avertissement.
- Un diagnostic supprimé n'est ni affiché, ni compté, ni corrigé. Il est compté à part dans le rapport HTML (colonne « Suppressed »).
- **Directive de fichier et directive de ligne**, comme ruff 0.17.3 (vérifié, A76) : les directives de fichier passent d'abord. Si l'une d'elles nomme la règle d'un diagnostic, elle le supprime, et une directive de ligne qui le couvre aussi reste inutile : FUR001 la signale.
- `FUR000` et `FUR001` ne peuvent pas être supprimés par `foqa` (seulement désactivés par la sélection). **Seule exception, comme ruff** (A76) : un `# furryp: foqa` global exempte tout son fichier de FUR001, directives de ligne comprises.
- Les directives devenues inutiles sont signalées par FUR001 (`unused-foqa`, équivalent de ruff RUF100).

### 6.1 `--add-foqa` (gel de la dette existante)

Équivalent de `ruff check --add-noqa`. Analyse avec la sélection courante, puis ajoute une directive `foqa` pour **chaque** diagnostic restant (hors `FUR000` et `FUR001`), écrit les fichiers et quitte. Ensuite, seules les nouvelles violations apparaissent ; les violations gelées restent visibles dans le rapport HTML, colonne « Suppressed ».

- **Portée des règles** : chaque règle déclare `scope = "line"` ou `scope = "file"` (tableau du §11).
- **Format compact** (A22) : `  # foqa:FUR101,FUR403`. Deux espaces avant `#` (PEP 8, `ruff format`), aucune espace après `:` ni après les virgules, **codes** triés. Environ 15 caractères pour un code.
- **Règle de ligne** : la directive est ajoutée à la fin de la **dernière ligne physique de la ligne logique** qui contient la ligne de début du diagnostic, c'est-à-dire là où `ruff format` la placerait de toute façon. Les blancs finaux de cette ligne sont retirés avant l'ajout. Si la ligne logique porte déjà une directive, les codes y sont fusionnés ; si elle porte un `# foqa` global, rien n'est ajouté. Un commentaire existant est conservé et la directive est ajoutée après lui. Comme `--add-noqa` de ruff 0.17.3 (vérifié, A76), une dernière ligne ainsi modifiée qui n'a pas de fin de ligne en reçoit une, dans le style du fichier ; une dernière ligne qui n'est pas modifiée reste telle quelle.
- **Règle de fichier** : ajouter ou compléter **une seule** ligne `# furryp: foqa:CODES` dans le préambule, après le shebang et la déclaration d'encodage s'ils existent, sinon en ligne 1.
- Les fichiers en `FUR000` sont ignorés. L'opération est **idempotente** et préserve encodage, BOM et fins de ligne (même écriture qu'au §7.2, étape 6). **Seule exception, comme `--add-noqa` de ruff 0.17.3** (vérifié, A71) : après une directive invalide, la directive ajoutée reste sans effet (seul le premier mot-clé compte), et une nouvelle s'ajoute à chaque exécution. L'avertissement du §6 le signale.
- **Longueur de ligne et ruff** : ruff exclut `# noqa` du calcul de longueur (E501) mais pas `# foqa`. Une directive ajoutée peut donc faire dépasser la limite de ruff. Il suffit de lancer `ruff format` : il replie l'instruction, et la directive reste valide grâce à la ligne logique. Seule une ligne impossible à replier (longue chaîne) peut garder un E501 : limite assumée (A31).
- **Instruction composée sur une seule ligne**, même limite que `# noqa` dans ruff 0.17.3 (vérifié, A72) : `ruff format` réécrit `def f(x): return x  # foqa:FUR202` sur deux lignes et place le commentaire sur `return`, une autre ligne logique. La directive n'agit plus, et le diagnostic revient avec FUR001. Sur du code pas encore formaté, lancer `ruff format` **avant** `--add-foqa` évite ce cas, ainsi que les mesures qui changent au repli (chiffres en A72).
- **Sortie**, comme ruff 0.17.3 : `Added {n} foqa directive{s}.` sur **stderr** (`n` = nombre de lignes ajoutées ou complétées) ; `n = 0` : rien n'est affiché. Rien sur stdout. Code de sortie 0 (2 en cas d'erreur).

## 7. Corrections automatiques

### 7.1 Principe

- **Seules des corrections sûres existent** : une correction ne change jamais le comportement du code à l'exécution. Toute transformation qui pourrait le changer (déplacer un import, réordonner du code) n'est pas proposée : le diagnostic est seulement signalé. Seules les directives `foqa` ont aujourd'hui une correction (§7.3).
- Une correction (`Fix`) = une liste d'éditions `(start, end, content)` sur le **texte** du fichier (index en caractères).
- **Analyse par `ast` + `tokenize`, réécriture par éditions textuelles ciblées.** `ast` perd les commentaires et la mise en forme : il ne sert qu'à **localiser**. Les éditions sont posées aux positions fournies par `tokenize` et `ast`, le reste du fichier est conservé octet pour octet. NE DOIVENT PAS servir à réécrire du code : `ast.unparse`, `tokenize.untokenize`, ni une bibliothèque de CST comme `libcst` (dépendance tierce, et inutile : aucune correction ne restructure le code, A21). `ast.unparse` reste permis pour **afficher** un extrait dans un message (FUR403). Si une future correction devait restructurer du code, ce choix serait à rouvrir (A34).
- `--fix` applique toutes les corrections disponibles ; `--diff` les montre sans rien écrire.
- Une correction NE DOIT jamais produire un code que `ruff format` modifierait (espacement compris). **Exceptions, comme RUF100 de ruff 0.17.3** (vérifié, A72) : retirer une directive (FUR001) peut rendre inutile le repli qu'elle avait provoqué, ou laisser deux lignes vides dans un corps. Relancer `ruff format` suffit.

### 7.2 Algorithme (par fichier)

1. Analyser, puis collecter les corrections des diagnostics non supprimés. Comme ruff 0.17.3, un fichier qui ne se parse pas (FUR000) ne reçoit aucune correction : ses diagnostics n'ont ni `Fix` ni `[*]`.
2. Trier par position de début ; écarter toute correction qui chevauche une correction déjà retenue. Comme ruff, une correction qui commence là où la précédente finit est aussi écartée : elle attend la passe suivante.
3. Appliquer les éditions retenues de la fin vers le début du texte.
4. Ré-analyser. Si le nouveau texte ne se parse plus : revenir au texte précédent, écrire sur stderr `error: Fix introduced a syntax error in {path}; reverting`, et arrêter les corrections pour ce fichier.
5. Recommencer tant qu'il reste des corrections, dans la limite de 10 itérations.
6. Écrire le fichier uniquement s'il a changé : `path.write_bytes(texte.encode(encodage))`, avec l'encodage détecté à la lecture (`utf-8-sig` restitue le BOM). Le texte en mémoire a gardé ses fins de ligne d'origine (§3.1) et les lignes insérées par `--add-foqa` utilisent le style dominant (`\r\n` ou `\n`, d'après la première fin de ligne du fichier) : aucune fin de ligne existante n'est modifiée, sur aucune plateforme.

### 7.3 Règles corrigeables

| Règle | Correction |
|---|---|
| FUR001 unused-foqa | Réécrit une directive signalée avec ses seuls codes qui ont servi (comme ruff) ; retire la directive devenue vide |

Les autres règles n'ont pas de correction. **Aucune correction ne déplace du code** (A21).

## 8. Configuration JSON

### 8.1 Découverte

1. Si `--config PATH` est fourni : ce fichier. **Racine du projet** = son dossier.
2. Sinon, remonter depuis le répertoire courant jusqu'au premier dossier contenant `pyproject.toml`. Ce dossier est la racine du projet ; la configuration est `furryp.json` **dans ce dossier** s'il existe, sinon les valeurs par défaut.
3. Sans `pyproject.toml` : racine = répertoire courant ; configuration = `./furryp.json` s'il existe, sinon les défauts.

Tous les motifs de chemins de la configuration sont relatifs à la racine du projet. `furryp.json` est lu en `encoding="utf-8-sig"` (§3.1).

### 8.2 Précédence

CLI > `furryp.json` > valeurs par défaut du code. Un objet partiel dans `rules` ne remplace que les clés fournies (fusion clé par clé ; pas de fusion de listes).

### 8.3 Validation

- JSON invalide, clé inconnue, type invalide, valeur hors domaine : `error: {fichier}: {chemin.de.la.clé}: {problème}` sur stderr et code 2. Pour une clé inconnue, proposer la plus proche (`did you mean "max-lines"?`).
- La validation est dérivée des dataclasses d'options de chaque règle (pas de bibliothèque de schéma).
- Les clés de `rules` sont les **noms** de règle (lisibilité : le JSON n'a pas de commentaires).

### 8.4 Référence complète (valeurs par défaut)

Les seuils sont à titre indicatif.

```json
{
  "include": ["**/*.py"],
  "exclude": [".git", ".hg", ".svn", ".venv", "venv", "env", "__pycache__", "build", "dist",
              "node_modules", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".nox", "*.egg-info"],
  "extend-exclude": [],
  "select": ["FUR"],
  "extend-select": [],
  "ignore": [],
  "per-file-ignores": {},
  "rules": {
    "unused-foqa": {},
    "function-too-long": { "max-lines": 26 },
    "file-too-long": { "max-lines": 1000 },
    "halstead-file": { "metric": "volume", "max": 15000 },
    "halstead-function": { "metric": "volume", "max": 1200 },
    "cognitive-complexity": { "max": 16 },
    "too-complex-class": { "max-class-complexity": 80 },
    "layer-violation": { "source-roots": ["."], "include-type-checking": true, "contracts": [] },
    "demeter-chain": { "max-depth": 3, "ignore-roots": ["self", "cls"], "ignore-imported-modules": true, "count-calls": false },
    "too-many-instance-attributes": { "max-instance-attributes": 20 }
  },
  "report": { "top-n": 10, "title": "furryp — audit", "rating-thresholds": [0.20, 0.40, 0.60, 0.80] }
}
```

Domaines : `metric` ∈ {`volume`, `difficulty`, `effort`, `bugs`} ; entiers ≥ 0 ; `rating-thresholds` = 4 réels croissants dans [0, 1]. La clé JSON d'un champ est son nom avec `_` remplacé par `-`.

`per-file-ignores` : `{ "motif": ["FUR101", "demeter-chain"] }`.

### 8.5 Sélection des fichiers

- Parcours récursif de chaque dossier de `PATHS` ; les dossiers exclus sont **élagués** (pas de descente).
- Un motif **sans `/`** s'applique à **chaque composant** du chemin relatif (nom de dossier ou de fichier), via `fnmatch.fnmatchcase`. Un motif **avec `/`** s'applique au chemin relatif complet en POSIX, via `PurePosixPath(rel).full_match(motif)`.
- Un fichier est retenu s'il correspond à `include` et à aucun motif de `exclude` ∪ `extend-exclude`.
- Les exclusions s'appliquent **aussi** aux fichiers passés explicitement en argument (A07).
- Lecture des sources : §3.1. Les chemins sont dédoublonnés après résolution. Un chemin passé en argument qui n'existe pas produit un diagnostic FUR000 (§4.4).

## 9. Architecture

### 9.1 Arborescence

```
pyproject.toml  uv.lock  .python-version  .gitignore  LICENSE
furryp.json                 # configuration de dogfooding (§9.4)
.claude/    settings.json  # Claude Code
README.md  CLAUDE.md
furryp/
  __init__.py                # __version__
  __main__.py                # python -m furryp
  cli/        parser.py  app.py  rule.py           # argparse, orchestration, codes de sortie, `furryp rule`
  config/     options.py  defaults.py  loader.py  schema.py  selection.py
  core/       source.py  diagnostic.py  discovery.py  errors.py  paths.py  suppression.py
              registry.py  names.py  ast_utils.py  positions.py  project.py
  metrics/    lines.py  halstead.py  cognitive.py  cyclomatic.py  classes.py  file_metrics.py
  rules/      __init__.py  catalog.py (ALL_RULES)  syntax.py  suppression.py  size.py
              metrics.py  design.py  contracts.py
              docs/  FUR000.md … FUR404.md          # fiches affichées par `furryp rule`
  lint/       runner.py                            # règles sélectionnées → filtre foqa → FUR001
  fix/        engine.py  diff.py  foqa.py              # foqa.py : --add-foqa
  output/     terminal.py  snippet.py  statistics.py  settings.py  rule_doc.py  fix_preview.py
  report/     files.py  categories.py  model.py  render.py  templates/ (page.html, *.html, report.css)
tests/
  fixtures/<nom-de-règle>/ ok_*.py  ko_*.py  ko_*.expected
  snapshots/
  test_*.py
```

Cette arborescence est indicative : elle peut être affinée si un fichier dépasse les règles, mais les couches du §9.4 sont obligatoires.

### 9.2 Modèle de données (contrat)

```python
@dataclass(frozen=True, slots=True)
class Position:  # 1-indexé, colonne en caractères
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class Span:
    start: Position
    end: Position


@dataclass(frozen=True, slots=True)
class Edit:
    start: int  # index de caractère dans le texte
    end: int
    content: str


@dataclass(frozen=True, slots=True)
class Fix:  # toujours sûre (§7.1)
    edits: tuple[Edit, ...]


@dataclass(frozen=True, slots=True)
class Diagnostic:
    code: str
    name: str
    message: str
    path: Path
    span: Span
    help: str  # obligatoire et non vide (§11.0)
    fix: Fix | None
```

- `SourceFile` : chemin, chemin affiché, texte, encodage (`utf-8-sig` en cas de BOM), style de fin de ligne, lignes, tokens, lignes logiques, AST (ou erreur de syntaxe), table de conversion octets ↔ caractères ↔ index. **Tokens et AST sont calculés une seule fois** et partagés par toutes les règles.
- `FileMetrics` : calculé une fois par fichier (paresseusement) et partagé par les règles de métriques **et** le rapport : lignes, lignes de code, Halstead du fichier, liste de `FunctionMetrics` (nom qualifié, span du nom, lignes de code, Halstead, complexité cognitive et ses contributions), liste de `ClassMetrics` (nom, span du nom, complexité, nombre d'attributs d'instance, classe de test, de dispatch ou de données), une par classe.
- `Rule` : `code`, `name`, `category`, `summary`, `options_type` (dataclass avec défauts), `fixable` (booléen), `scope` (`line` ou `file`, §6.1), et `check(context) -> Iterable[Diagnostic]`. `context` donne le `SourceFile`, les options typées, le `FileMetrics`, les noms importés (`ImportTable`, §10.5) et le `ProjectContext` (racine, résolution de noms de modules). Chaque règle a sa fiche `rules/docs/<code>.md` (§4.6).
- FUR001 est déclarée comme une règle (code, nom, fiche, sélection) mais évaluée par `lint.runner` après le filtrage `foqa`, seul à connaître l'usage de chaque directive.
- Registre : `rules/catalog.py` définit `ALL_RULES` (liste explicite), réexporté par `rules/__init__.py` ; le cœur n'importe jamais les règles.

### 9.3 Pipeline

`cli` → chargement et validation de la configuration → découverte des fichiers → pour chaque fichier : `lint.runner` (`SourceFile` → règles sélectionnées → filtre `foqa` → FUR001 → diagnostics) → (corrections : `fix.engine` rappelle `lint.runner` après chaque passe) → rendu (terminal, statistiques ou HTML) → code de sortie.

### 9.4 Contrat de couches de furryp (dogfooding)

`furryp.json` à la racine du dépôt DOIT contenir au minimum :

```json
{
  "extend-exclude": ["tests"],
  "rules": {
    "layer-violation": {
      "contracts": [
        {
          "type": "layers",
          "name": "furryp-layers",
          "layers": [
            "furryp.cli",
            ["furryp.output", "furryp.report", "furryp.fix"],
            "furryp.lint",
            "furryp.config",
            "furryp.rules",
            "furryp.metrics",
            "furryp.core"
          ]
        }
      ]
    }
  }
}
```

## 10. Définitions communes

### 10.1 Lignes

- **Lignes physiques** : séparées par `\r\n`, `\r` ou `\n` uniquement. NE PAS utiliser `str.splitlines()`, qui coupe aussi sur `\f`, `\v`, `\x1c`… Total = nombre de fins de ligne, + 1 si le texte est non vide et ne finit pas par une fin de ligne.
- **Ligne de code** : ligne physique couverte (de `start[0]` à `end[0]` inclus) par au moins un token **significatif**. Non significatifs : `COMMENT`, `NL`, `NEWLINE`, `INDENT`, `DEDENT`, `ENDMARKER`, `ENCODING`, et tous les tokens d'une docstring.

### 10.2 Fonctions et méthodes

- **Fonction** : tout `FunctionDef` / `AsyncFunctionDef`, méthodes comprises. Les `lambda` ne sont pas des fonctions.
- **Fonction imbriquée** : fonction définie (à n'importe quelle profondeur) dans le corps d'une autre fonction.
- **Span du nom** : le token `NAME` qui suit le mot-clé `def`. C'est la position par défaut des diagnostics de fonction ; idem pour les classes avec `class`.
- **Nom qualifié** : le nom de la fonction précédé de ceux des classes et fonctions qui l'englobent, séparés par des points, sans `<locals>` (`Parser.load`, `outer.inner`). Un bloc (`if`, `try`…) n'y ajoute rien. C'est le `{name}` des messages de FUR101, FUR202 et FUR203.
- Les **décorateurs** et **valeurs par défaut** d'une fonction sont évalués dans la portée englobante : ils n'appartiennent pas à la fonction.

### 10.3 Docstrings

Premier statement d'un module, d'une classe ou d'une fonction quand c'est un `Expr` contenant un `Constant` de type `str`.

### 10.4 Positions

`ast` fournit des offsets en **octets UTF-8** : ils DOIVENT être convertis en colonnes de **caractères** (fonction unique dans `core/positions.py`). `tokenize` fournit déjà des colonnes en caractères. Toute position affichée est 1-indexée.

### 10.5 Résolution des noms importés

Table construite depuis les imports du module : `import enum` → `enum` ↦ `enum` ; `import enum as e` → `e` ↦ `enum` ; `from enum import Enum as E` → `E` ↦ `enum.Enum`. Un nom (`Name`) ou un attribut (`a.b`) se résout en remplaçant sa racine par sa cible ; une racine qui n'est pas importée reste telle quelle. Elle sert au test `TYPE_CHECKING` (ci-dessous), à FUR402, à FUR403 et à FUR404.

- **Portée** : les imports de premier niveau et ceux des blocs qu'ils contiennent (`if`, `try`, `with`…), pas ceux des fonctions et des classes.
- `import a.b` lie `a` ↦ `a` ; un import relatif garde ses points (`from .m import x` → `x` ↦ `.m.x`) ; `from m import *` ne lie rien. Pour FUR403, un module importé est un nom dont la première liaison est `import x` ou `import x as y`.
- Un nom lié deux fois garde sa **première** cible : dans `try: from enum import StrEnum` / `except ImportError: …`, c'est le module essayé d'abord.
- **Test `TYPE_CHECKING`, comme ruff 0.17.3** (vérifié avec TC004 et TC005) : le nom `TYPE_CHECKING`, tout attribut `x.TYPE_CHECKING` (`typing.TYPE_CHECKING`, `t.TYPE_CHECKING`), ou un nom qui se résout vers `typing.TYPE_CHECKING` ou `typing_extensions.TYPE_CHECKING` (`from typing import TYPE_CHECKING as TC`). `if False:` n'en est pas un.

## 11. Catalogue des règles

Messages et aides en anglais, comme ruff. Chaque règle a aussi une fiche utilisateur, affichée par `furryp rule` (§4.6).

furryp s'adresse à des développeurs seniors comme juniors (A51). Chaque règle DOIT se comprendre en une phrase et se configurer simplement, et son `help` DOIT dire en une phrase quoi corriger ou regarder. La précision passe avant la sévérité : un junior qui reçoit trop de faux positifs abandonne l'outil, et une règle couvre les cas avérés plutôt que tous les cas.

### 11.0 Contrat du `help:`

Le `help:` donne, comme chez ruff, une piste simple : il reste factuel et laisse au développeur le choix de la solution. Toute règle DOIT le fournir, selon ces règles :

1. **Toujours présent**, sur **une seule ligne**, 160 caractères au plus (tronqué par `…`).
2. **Simple et factuel**, comme chez ruff : une phrase, qui dit ce que le problème implique et, au besoin, une direction (`consider…`). Si c'est insuffisant, deux phrases ou une phrase plus longue.
3. **Laisse le choix de la solution** : ni contributeurs, ni poids, ni numéros de ligne, ni liste de ce qu'il faudrait traiter en premier. Un tel détail pousse à corriger ce qui fait baisser le score, au détriment de la vision d'ensemble (loi de Goodhart, A54). L'explication détaillée reste dans la fiche (`furryp rule`).
4. **Ne propose jamais** de contournement : ni `foqa`, ni `ignore`, ni changement de seuil.
5. **Déterministe** : mêmes entrées, même texte.

**Message d'une règle de mesure** : il se termine par `({valeur} > {max})`, comme ruff (`Too many arguments in function definition (7 > 5)`). Le seuil et la valeur se lisent donc au même endroit, dans toutes les règles.

Chaque fiche ci-dessous donne le gabarit exact de son `help:`.

| Code | Nom | Catégorie | Portée (§6.1) | `--fix` |
|---|---|---|---|---|
| FUR000 | invalid-syntax | erreurs | file | non |
| FUR001 | unused-foqa | suppressions | line | oui |
| FUR101 | function-too-long | taille | line | non |
| FUR102 | file-too-long | taille | file | non |
| FUR201 | halstead-file | halstead | file | non |
| FUR202 | halstead-function | halstead | line | non |
| FUR203 | cognitive-complexity | complexité | line | non |
| FUR401 | too-complex-class | conception | line | non |
| FUR402 | layer-violation | conception | line | non |
| FUR403 | demeter-chain | conception | line | non |
| FUR404 | too-many-instance-attributes | conception | line | non |

---

### FUR000 · invalid-syntax

- **Mesure** : le fichier (ou le chemin passé en argument) ne se lit pas, ne se décode pas, ne se tokenise pas ou ne se parse pas.
- **Position** : ligne et colonne de l'erreur de syntaxe ; 1:1 pour une erreur de lecture ou de décodage (rendu sans extrait, §5.1).
- **Messages** : `SyntaxError: {msg}` ; `Failed to decode file: {msg}` ; `Failed to read file: {msg}` (chemin inexistant, droits insuffisants).
- **Aides**, dans le même ordre : `Fix the syntax error; other checks are skipped for this file` ; ``Save the file as UTF-8, or declare its encoding with a `# -*- coding: … -*-` line`` ; `Check that the path exists and is readable`.
- **Conséquence** : les règles qui ont besoin de l'AST ou des tokens ne s'exécutent pas sur ce fichier ; FUR102 (purement textuelle) s'exécute. Le fichier est exclu des agrégats de métriques du rapport.
- **Ne peut être ni ignoré ni supprimé.**

### FUR001 · unused-foqa

Équivalent de ruff RUF100, dont il reprend le comportement (A17, A32, A39) : une directive qui ne sert plus finit par masquer de futures violations, elle doit disparaître.

- **Mesure**, après l'exécution de toutes les autres règles sélectionnées sur le fichier. Chaque identifiant d'une directive (de ligne ou de fichier) est classé, dans cet ordre :
  - `duplicated` : la règle est déjà nommée dans la même directive, par son code ou par son nom ; un identifiant inconnu répété compte aussi ;
  - identifiant qui ne correspond à aucune règle : **ignoré**, comme ruff ignore les codes qu'il ne connaît pas ; il ne supprime rien ;
  - `non-enabled` : code d'une règle qui n'est pas sélectionnée pour le fichier (`select`, `extend-select`, `ignore`, `per-file-ignores`, options de la ligne de commande) ;
  - `unused` : code d'une règle sélectionnée qui n'a supprimé **aucun** diagnostic ; `FUR000` et `FUR001`, non supprimables, sont toujours `unused` ;
  - sinon, le code a servi.
- Un `# foqa` global qui n'a rien supprimé est inutile, quelle que soit la sélection (comme ruff). Un `# furryp: foqa` global n'est jamais signalé, même s'il ne sert plus : il exempte tout son fichier de la règle, comme ruff (§6, A76).
- **Un seul diagnostic par directive** qui ne sert pas entièrement.
- **Position** : span de la directive dans son commentaire, du `#` de `foqa` jusqu'au dernier code (comme ruff pour `# noqa`).
- **Messages** : ``Unused `foqa` directive ({raisons})``, où `{raisons}` liste les catégories non vides séparées par `; `, dans l'ordre `unused`, `non-enabled`, `duplicated`. Chaque catégorie s'écrit ``{catégorie}: `{id}`, `{id}` `` (identifiants tels qu'écrits). Exemple : ``Unused `foqa` directive (unused: `FUR102`; non-enabled: `FUR403`; duplicated: `FUR403`)``. Directive globale : ``Unused blanket `foqa` directive``.
- **Aide** : ``Remove unused `foqa` directive``, comme RUF100 de ruff 0.17.3 (vérifié, A71).
- **Correction** (comme ruff, vérifié sur ruff 0.17.3) : une directive signalée est réécrite avec ses seuls codes qui ont servi, dans leur ordre et tels qu'écrits, au format compact (`# foqa:FUR101`, `# furryp: foqa:FUR102`, mot-clé en minuscules), et le texte qui la suit reste. Les codes `unused`, `non-enabled`, `duplicated` et inconnus sont retirés ; une directive non signalée n'est pas touchée. Si la directive devient vide, elle est retirée avec les blancs qui la précèdent et le texte qui la suit ; si un autre commentaire la suit directement, ce sont les blancs qui la suivent qui partent, et ce commentaire est conservé. Une ligne devenue vide (directive de fichier, ou directive de ligne seule sur sa ligne) est supprimée. Conséquence assumée, comme chez ruff : `furryp check --ignore FUR4 --fix` retire les codes `FUR4xx` des directives.
- Ne peut pas être supprimée par `foqa`, et `--add-foqa` ne la gèle jamais. **Options** : aucune.

### FUR101 · function-too-long

- **Mesure** : nombre de lignes de code (§10.1) de la ligne du premier statement du corps jusqu'à `end_lineno`. Signature, décorateurs, commentaires, lignes vides et docstring exclus. Une fonction sur une ligne (`def f(): return 1`) compte 1.
- **Portée** : toutes les fonctions. Les lignes d'une fonction imbriquée comptent dans son parent, **et** la fonction imbriquée est évaluée seule.
- **Options** : `max-lines: int = 26`.
- **Position** : span du nom.
- **Message** : ``Function `{name}` has too many lines of code ({count} > {max})``, avec le nom qualifié (§10.2).
- **Aide** : ``Long functions are hard to read and test; consider splitting this one``.
- **Exemple** : avec `max-lines = 3`, la fonction ci-dessous a 4 lignes de code (docstring, commentaire et ligne vide exclus) → violation.
  ```python
  def f(x):
      """Doc."""
      # commentaire
      y = x + 1
      y = y * 2

      z = call(y)
      return z
  ```

### FUR102 · file-too-long

- **Mesure** : nombre total de lignes physiques (§10.1), tout compris.
- **Options** : `max-lines: int = 1000`.
- **Position** : début de la première ligne au-delà de la limite (ligne `max + 1`), soulignée sur toute sa longueur.
- **Message** : `File has too many lines ({count} > {max})`
- **Aide** : ``Long files are hard to navigate; consider splitting this one into smaller modules``.

### FUR201 · halstead-file — FUR202 · halstead-function

- **Comptage par tokens** (pas par AST) :
  - Ignorés : tokens non significatifs (§10.1), tokens des docstrings, `FSTRING_START` / `FSTRING_END` / `TSTRING_START` / `TSTRING_END`, délimiteurs fermants `)` `]` `}` (une paire compte une fois, à l'ouverture), `FSTRING_MIDDLE` et `TSTRING_MIDDLE` vides (`tokenize` en produit après un format imbriqué : `f"{x:>{w}}"`).
  - **Opérateurs** : tokens `OP`, et `NAME` qui sont des mots-clés durs (`keyword.iskeyword`). Les mots-clés « souples » (`match`, `case`, `type`, `_`) sont des opérandes.
  - **Opérandes** : `NAME` non mots-clés, `NUMBER`, `STRING`, `FSTRING_MIDDLE`, `TSTRING_MIDDLE`.
  - Distincts : par texte exact du token.
- **Formules** : `n1, n2` (distincts), `N1, N2` (totaux) ; `n = n1 + n2` ; `N = N1 + N2` ; `volume = N × log2(n)` (0 si `n ≤ 1`) ; `difficulty = (n1 / 2) × (N2 / n2)` (0 si `n2 = 0`) ; `effort = difficulty × volume` ; `bugs = volume / 3000`.
- **Portée** : FUR201 = tous les tokens du fichier (ce n'est pas la somme des fonctions). FUR202 = tokens de la fonction, du mot-clé `def` (ou `async`) jusqu'à la fin de la fonction, signature et fonctions imbriquées comprises, décorateurs exclus.
- **Options** : FUR201 `metric = "volume"`, `max = 15000` ; FUR202 `metric = "volume"`, `max = 1200`.
- **Position** : FUR201 → tout le fichier : 1:1, sans extrait (§5.1) ; FUR202 → span du nom.
- **Messages** : `Halstead {metric} of the file is too high ({value:.1f} > {max})` ; ``Halstead {metric} of function `{name}` is too high ({value:.1f} > {max})``, avec le nom qualifié (§10.2).
- **Aide FUR201** : `This file does a lot; consider splitting it or simplifying it`.
- **Aide FUR202** : `This function does a lot; consider splitting it or simplifying it`.

### FUR203 · cognitive-complexity

Adaptation à Python de la spécification inspiré SonarSource (G. Ann Campbell), avec les choix furryp signalés « (furryp) ».

- Départ à **0**. Un niveau d'imbrication `N` part de 0.
- **Incréments structurels** (+1 + N) : `if` (pas `elif`), ternaire, `match` (+1 pour l'instruction entière, pas par `case`), `for`, `async for`, `while`, chaque gestionnaire `except` / `except*`.
- **Incréments hybrides** (+1, sans pénalité d'imbrication) : `elif`, `else` d'un `if`, `else` d'une boucle ou d'un `try` (furryp).
- **Incréments fondamentaux** (+1) :
  - chaque séquence d'opérateurs booléens identiques, c'est-à-dire chaque nœud `BoolOp` dont le parent n'est pas un `BoolOp` du même opérateur ;
  - chaque garde de `case` (furryp) ;
  - chaque clause `if` de compréhension (furryp) ;
  - +1 une seule fois si la fonction s'appelle elle-même directement : `name(...)` dans une fonction ; `self.name(...)` ou `cls.name(...)` dans une méthode, où un `name(...)` sans préfixe appelle une autre fonction et ne compte pas (`def open(self): return open(self.path)`). Un tel appel compte aussi depuis une fonction imbriquée ; en revanche, une fonction imbriquée qui s'appelle elle-même n'ajoute rien à son parent.
- **Augmentent l'imbrication** (N + 1 pour leur contenu) : corps de `if` / `elif` / `else`, des boucles, des `except`, des `case`, opérandes d'un ternaire, `lambda`, fonctions et classes imbriquées. Les fonctions imbriquées et les `lambda` n'ont **pas** d'incrément propre, et leur contenu compte **dans le parent** ; elles ne sont **pas** évaluées seules pour FUR203.
- **Incréments d'instruction** (furryp) : **chacun compte pour 1** (+1, sans pénalité d'imbrication) : `try`, `finally`, `with` (et `async with`), `break`, `continue`, `return`, `assert`, `pass`, et chaque `:=`.
  - **Pas de cumul** : si l'instruction qui porte l'un de ces éléments reçoit déjà un incrément d'une autre règle, seule la valeur la plus lourde compte ; le +1 ne s'ajoute donc pas. Les incréments d'une instruction sont ceux de son en-tête, de ses propres expressions et de ses clauses (`elif`, `except`, `else`), pas ceux des blocs imbriqués dans son corps. Les éléments de cette liste ne se neutralisent pas entre eux, et l'incrément de récursion (porté par la fonction) n'entre pas dans la comparaison.
  - Exemples : `return total` → +1 ; `return a and b` → +1 (la séquence booléenne seule) ; `return x if c else y` → le ternaire seul ; `if (m := f()):` → le `if` seul ; `try` / `except` / `finally` → les `except` seuls ; `try` / `finally` sans `except` ni `else` → +2 ; `with (x := f()):` → +2.
  - `try` et `with` n'augmentent pas l'imbrication de leur corps.
- **Ne comptent pas** (liste fermée : tout ce qui n'est pas listé ci-dessus vaut 0) : par exemple `raise`, `yield`, `await`, `del`, les affectations, les appels. Les annotations de la signature d'une fonction imbriquée valent 0, quel que soit leur contenu : le `def` ne les évalue pas.
- Distinguer `elif` d'un `else:` contenant un `if` : le `If` présent dans `orelse` est un `elif` si sa ligne source commence (après indentation) par `elif`.
- **Contributions** : chaque incrément est enregistré avec sa construction (`if`, `elif`, `else`, `for`, `while`, `except`, `match`, `ternary`, `boolean sequence`, `case guard`, `comprehension if`, `recursion`, `try`, `finally`, `with`, `break`, `continue`, `return`, `assert`, `pass`, `walrus`), sa ligne et ses points. C'est le détail du calcul, que l'aide ne cite pas.
- **Options** : `max: int = 16` (sur `Lib` de Python 3.14, 2,39 % des fonctions non imbriquées le dépassent avec `Lib/test`, et 5,46 % sans, A77).
- **Position** : span du nom. **Message** : ``Cognitive complexity of function `{name}` is too high ({value} > {max})``, avec le nom qualifié (§10.2).
- **Aide** : `Branches and nesting make this function hard to follow; consider simplifying its control flow`.

#### Exemples de référence pour FUR203 (à utiliser tels quels dans les tests)

```python
def sum_of_primes(limit):
    total = 0
    for i in range(2, limit):
        for j in range(2, i):
            if i % j == 0:
                break
        else:
            total += i
    return total


def classify(items, strict):
    result = []
    for item in items:
        if item.ok and (strict or item.forced):
            result.append(item)
        elif item.retry:
            result.append(item if strict else None)
    return [r for r in result if r]


def route(event):
    match event:
        case {"type": "click", "x": x} if x > 0:
            return handle(x)
        case Key(code=code):
            return code
        case _:
            return None
```

| Fonction | Cognitive |
|---|---|
| `sum_of_primes` | 9 = for 1 + for 2 + if 3 + break 1 + else de boucle 1 + return 1 |
| `classify` | 10 = for 1 + if 2 + and 1 + or 1 + elif 1 + ternaire 3 + if de compréhension 1 ; le `return` de la ligne 18 porte déjà le `if` de compréhension : pas de cumul |
| `route` | 5 = match 1 + garde 1 + 3 × return 1 |

### FUR401 · too-complex-class

Une classe est trop complexe quand les complexités de ses méthodes dépassent ensemble `max-class-complexity`.

- **Mesure** : somme des complexités cyclomatiques de ses **méthodes** : toutes les fonctions du corps de la classe, à toute profondeur de ses blocs (`if`, `try`, `with`, `for`, `while`, `match`), `@staticmethod`, dunders et propriétés compris. Aucun code ne passe sous silence, et FUR404 emploie la même définition (A55).
- **Complexité d'une fonction** : comme C901 de ruff 0.17.3 (A52, comparé sur toute `Lib`). 1, plus 1 pour chaque `if`, `elif`, `for`, `while`, `except`, `else` d'un `try`, `case` (sauf un dernier `case` irréfutable sans garde) et fonction imbriquée, dont le corps compte pour sa méthode. `else`, `with`, `finally`, `assert`, opérateurs booléens, ternaires, compréhensions et `lambda` n'ajoutent rien.
- **Classe imbriquée** : mesurée à part, dans une classe comme dans une méthode. C'est le seul écart avec C901, qui la compte dans la fonction.
- **Option** : `max-class-complexity = 80`.
- **Classes non mesurées** :
  - **classes de test** : une base dont le nom finit par `TestCase` (`unittest.TestCase`, `IsolatedAsyncioTestCase`…), ou une classe nommée `Test`, `Test` + majuscule, chiffre ou `_`, sans `__init__` (celles que pytest collecte) ;
  - **classes de dispatch** : au moins 5 méthodes, chaque `def` comptant pour une (A55), dont au moins la moitié partagent un même préfixe parmi `visit_`, `do_`, `handle_`, `on_`.
- **Position** : span du nom de la classe. **Message** : ``Class `{name}` is too complex ({value} > {max})``, avec le nom court, comme N801 de ruff. Diagnostic strictement au-dessus du maximum.
- **Aide** : ``Move a group of related methods to a new class``.

### FUR402 · layer-violation

- **Nom de module d'un fichier** : chemin relatif à la première racine de `source-roots` qui le contient, sans `.py`, en notation pointée ; `pkg/__init__.py` → `pkg`. Fichier hors racines, ou `__init__.py` d'une racine : règle non appliquée.
- **Imports considérés** : tous les `Import` / `ImportFrom` du fichier, à toute profondeur. Les imports relatifs sont résolus depuis le paquet du module ; un import relatif qui remonte au-dessus du premier niveau est ignoré, comme pour TID251 de ruff. Si `include-type-checking = false`, ceux du corps des blocs `TYPE_CHECKING` (test du §10.5) sont ignorés, mais pas ceux de leur `else`, qui est du code exécuté.
- **Cibles** (A45) : `import a.b` nomme `a.b`. `from X import y` nomme `X`, puis `X.y` ; `from X import *` nomme `X`. Un motif qui correspond à `X` n'est pas retesté sur `X.y` : `from app.infra import a, b` ne viole un contrat qu'une fois.
- **Correspondance de module** : un motif `a.b` correspond à `a.b` et `a.b.*` (frontière de segment : pas à `a.bc`). `*` remplace exactement un segment.
- **Types de contrats** :
  - `forbidden` : `{"type": "forbidden", "name": "...", "source": ["app.domain"], "forbidden": ["app.infra"]}` → aucun module de `source` n'importe un module de `forbidden`. Si plusieurs motifs conviennent, le premier dans l'ordre écrit est cité (A59).
  - `layers` : `{"type": "layers", "name": "...", "layers": ["app.api", ["app.service", "app.jobs"], "app.domain"]}` → du plus haut au plus bas. Un module d'une couche n'importe **jamais** une couche plus haute ; une sous-liste = même niveau, sans contrainte entre ses éléments ; les modules hors couches sont libres. Le niveau d'un module est celui de son motif le plus spécifique (le plus de segments, puis le moins de `*`), le plus haut à égalité (A48). Les couches ne sont pas strictes : un module peut importer toutes celles du dessous. Une dépendance précise à interdire, comme la view d'un MVP qui n'importe jamais le model, s'écrit avec `forbidden`.
  - `independence` : `{"type": "independence", "name": "...", "modules": ["app.billing", "app.shipping"]}` → aucun de ces modules n'importe un autre. Avec `*`, chaque module concret compte à part : `app.*` interdit à `app.billing` d'importer `app.shipping`, pas `app.billing.a` d'importer `app.billing.b` (A47).
- **Portée** (A48) : la règle couvre les cas évidents, c'est-à-dire ce qu'un import dit directement, quelle que soit sa forme. Une dépendance indirecte, un nom réexporté par un paquet ou `importlib` ne sont pas suivis : ce sont des choix que le développeur assume.
- **Validation** (§8.3), comme `banned-api` de ruff : type inconnu, clé manquante ou clé inconnue → code 2 (`missing key "name"`) ; un motif n'est pas contrôlé (`a..b` ne correspond simplement à rien).
- **Position** (A45) : span de l'instruction pour une cible `X` de `from X import y`, du nom importé sinon (`X.y`, ou `import a.b`). **Message** : ``Import of `{target}` breaks contract `{contract}`: `{source}` must not import `{forbidden}` ``, où `{source}` et `{forbidden}` sont les modules concrets désignés par les motifs (`*` remplacé, A47).
- **Aide**, selon le type de contrat :
  - `layers` : `A layer only imports the layers below it; consider inverting this dependency` ;
  - `forbidden` : `This dependency is forbidden; consider moving the shared code or inverting it` ;
  - `independence` : `These modules must stay independent; consider moving the shared code to a common module`.
- **Options** : `source-roots = ["."]`, `include-type-checking = true`, `contracts = []` (règle inactive sans contrat).

### FUR403 · demeter-chain

- **Chaîne** : suite d'accès `.attr` partant d'une racine, qui finit sur son dernier `.attr` (un appel ou un indice qui le suit n'en fait pas partie, A47). On descend par `.value` : `Attribute` (+1), `Subscript` (traversé sans compter) ; `Call` interrompt la chaîne si `count-calls = false` (`a.b().c.d` donne deux chaînes : `a.b` = 1 et `().c.d` = 2). Si `count-calls = true`, on traverse aussi `Call` (via `.func`). Ce que la chaîne ne traverse pas (indice, arguments, racine) forme ses propres chaînes. Toutes les expressions comptent, annotations et décorateurs compris.
- **Profondeur** = nombre d'`Attribute` de la chaîne. `a.b.c.d.do()` → 4.
- **Exemptions** :
  - si la racine est un `Name` de `ignore-roots`, le premier attribut ne compte pas (`self.repo.session.query()` → 2) ;
  - si `ignore-imported-modules` et la racine est un nom lié par `import x` / `import x as y` (portée du §10.5), la chaîne est ignorée (`os.path.join`).
- **Un seul diagnostic par chaîne maximale** (sur le nœud le plus externe).
- **Options** : `max-depth = 3`, `ignore-roots = ["self", "cls"]`, `ignore-imported-modules = true`, `count-calls = false`.
- **Position** : span de l'expression, jusqu'au dernier `.attr`, sur plusieurs lignes s'il le faut. **Message** : ``Attribute chain `{chain}` is too deep ({depth} > {max})`` (`chain` = `ast.unparse`, tronqué à 60 caractères, `…` compris ; le reste de la ligne source si la chaîne est trop profonde pour `ast.unparse`, à partir de quelques centaines d'attributs).
- **Aide** : `Long chains depend on the inner structure of other objects; consider asking the first object for what you need`.

### FUR404 · too-many-instance-attributes

Une classe a trop d'attributs quand elle affecte plus de `max-instance-attributes` noms distincts sur ses instances.

- **Mesure** : nombre de noms distincts affectés sur le premier paramètre (`self.x = …`, `self.x += …`, `self.x: T = …`, dépaquetage, `for self.x in …`, `with … as self.x`), dans toutes les méthodes de la classe (même définition que FUR401, A55), fonctions imbriquées et `lambda` comprises. Une fonction imbriquée ou un `lambda` qui redéfinit le nom du premier paramètre travaille sur un autre objet.
- **Ne comptent pas** : les attributs de classe, ceux des classes parentes, et les noms affectés par une méthode sans instance (`@classmethod`, `@staticmethod`, `abc.abstractclassmethod`, `abc.abstractstaticmethod`, `__new__`, `__init_subclass__`, `__class_getitem__`). `self.x: T` sans valeur n'affecte rien.
- **Option** : `max-instance-attributes = 20`.
- **Classes non mesurées** :
  - **classes de test** (voir FUR401) ;
  - **données déclarées**, reconnues par un décorateur ou une base directe : `dataclasses.dataclass`, `pydantic.dataclasses.dataclass`, `attr.s`, `attr.attrs`, `attr.attributes`, `attr.define`, `attr.frozen`, `attr.mutable`, `attrs.define`, `attrs.frozen`, `attrs.mutable` (attrs comme RUF008 de ruff 0.17.3) ; `pydantic.BaseModel`, `pydantic.BaseSettings`, `pydantic_settings.BaseSettings`, `NamedTuple` (`typing`, `typing_extensions`, `collections.namedtuple(…)`), `TypedDict` (`typing`, `typing_extensions`) et les enums (`enum.Enum`, `enum.IntEnum`, `enum.StrEnum`, `enum.Flag`, `enum.IntFlag`) ;
  - **classes de données par leurs méthodes** : leurs seules méthodes sont des dunders et des accesseurs, dont le corps se réduit, docstring mise à part, à `return self.x` ou `self.x = valeur` (`valeur` étant un paramètre). La forme du corps décide, pas le nom ni le décorateur.
- **Position** : span du nom de la classe. **Message** : ``Class `{name}` has too many attributes ({value} > {max})``. Diagnostic strictement au-dessus du maximum.
- **Aide** : ``Group the attributes that always go together in a separate object``.

## 12. Rapport HTML d'audit

### 12.1 Invocation

`furryp check [PATHS] --report-html audit.html` : analyse (sans corriger), calcule les métriques de **tous** les fichiers retenus, écrit **un seul fichier HTML autonome** (UTF-8) et n'écrit rien sur stdout (§5.6).

- Les **métriques** sont calculées pour tous les fichiers, quelle que soit la sélection de règles. Les **violations** respectent la sélection, `per-file-ignores` et `foqa`.
- Les fichiers en `FUR000` et ceux en erreur interne (§4.4) sont exclus des agrégats et listés dans une section dédiée. Le code de sortie reste celui de `check` : il compte tous les diagnostics, ceux de ces fichiers compris.

### 12.2 Contraintes techniques

- **Autonome et hors ligne** : CSS inline, aucune ressource externe (ni CDN, ni police, ni image distante), **aucun JavaScript**. Repli avec `<details>` / `<summary>`. Styles `@media print` pour l'impression d'audit.
- **Gabarits hors du code Python** : `furryp/report/templates/*.html` et `report.css`, chargés via `importlib.resources` (`read_text(encoding="utf-8")`), avec des marqueurs `string.Template` (`$title`). Le code Python ne contient **aucun** fragment HTML littéral : la mise en page reste modifiable et traduisible sans toucher au code, et les modules du rapport restent sous les limites de taille (FUR101, FUR102).
- Toute valeur dynamique (chemins, messages, noms) est échappée avec `html.escape`.
- Écriture : `encoding="utf-8"`, `newline="\n"` (§3.1), `errors="replace"` : un chemin non décodable sous Linux ne fait pas perdre le rapport, comme sur stdout (§5.7).
- Libellés du rapport **en anglais**, comme toute la sortie de furryp (A19), portés par les gabarits. Libellés de référence : catégories `Size`, `Complexity`, `Halstead`, `Design` ; sections `Summary`, `Analysis errors`, `Appendix: effective configuration` ; colonne des violations gelées `Suppressed`.
- **Déterministe** : même entrée = même sortie, à l'exception de l'horodatage, fourni par une horloge injectable (pour les tests).

### 12.3 Contenu

1. **En-tête** : `report.title`, date et heure ISO locales, version de furryp, version de Python, racine du projet, fichier de configuration, nombre de règles actives (sélection du projet, `FUR000` compris, sans déduire `per-file-ignores`), durée de l'analyse. Si un fichier n'a pas pu être analysé, un **bandeau d'avertissement** suit l'en-tête et renvoie vers les erreurs d'analyse (A65).
2. **Synthèse** (cartes) : fichiers analysés, fichiers en erreur, lignes, lignes de code, fonctions, classes, violations (celles des fichiers analysés, FUR001 comprise), densité (violations pour 1000 lignes de code), violations supprimées par `foqa`, directives `foqa` inutiles (FUR001), corrections disponibles, et **note A à E par catégorie**.
3. **Une section par catégorie** (Taille, Complexité, Halstead, Conception), chacune avec :
   - la note A–E et la part des fichiers en violation ;
   - un tableau d'agrégats (moyenne, médiane, max ; total si pertinent) ;
   - les violations par règle (code, nom, nombre, fichiers touchés, supprimées, corrigeables), pour les règles sélectionnées, y compris à 0 ;
   - le **Top N** des pires fichiers (`report.top-n`, 10 par défaut), avec le score de la catégorie et ses colonnes. **Seuls les fichiers qui ont au moins une violation dans la catégorie sont listés** : un fichier dont les scores sont corrects n'est pas un mauvais fichier (A64).
4. **Erreurs d'analyse** : liste complète (non tronquée) des fichiers en `FUR000` et de ceux en erreur interne, avec leur message.
5. **Annexe** : configuration effective (JSON) dans un `<details>`.

| Catégorie | Règles | Agrégats | Score du Top N (pire en premier) | Colonnes du Top N |
|---|---|---|---|---|
| Taille | FUR101, FUR102 | lignes et lignes de code par fichier ; lignes de code par fonction ; nombre de fonctions au-dessus du seuil | lignes de code du fichier | lignes, lignes de code, fonctions, plus longue fonction |
| Complexité | FUR203 | complexité cognitive par fonction non imbriquée (cf. A13) : moyenne, médiane, max, nombre au-dessus du seuil | somme des complexités cognitives du fichier | somme cognitive, max cognitive, fonction la plus complexe |
| Halstead | FUR201, FUR202 | par fichier : volume, difficulté, effort ; bugs estimés (total) ; volume par fonction | métrique configurée de `halstead-file` | volume, difficulté, effort, bugs |
| Conception | FUR401–FUR404 | classes (toutes) ; complexité de classe et attributs d'instance (moyenne, médiane, max), sur les classes que FUR401 et FUR404 évaluent ; part de ces classes au-dessus des seuils ; violations de contrats (FUR402) ; chaînes (FUR403) | nombre de violations de conception | violations, complexité de classe max, attributs max, contrats, chaînes |

**Note d'une catégorie** : `s` = part des fichiers analysés ayant au moins une violation (non supprimée, règle sélectionnée) dans la catégorie. Avec `rating-thresholds = [t1, t2, t3, t4]` : A si `s ≤ t1`, B si `s ≤ t2`, C si `s ≤ t3`, D si `s ≤ t4`, sinon E. **A ne veut donc pas dire « aucune violation »** : par défaut, il admet jusqu'à 20 % de fichiers en violation (A62). Couleurs du vert (A) au rouge (E) ; la lettre reste toujours affichée.

**Pas de note** : une catégorie dont aucune règle n'est sélectionnée, ou un rapport sans fichier analysé, n'a pas de note. Un `*` remplace la lettre, et une phrase donne la raison, dans la section et dans la synthèse (A63).

**Règle qui n'a pas tourné** : un chiffre tiré des violations d'une règle non sélectionnée est inconnu, pas nul. `–` remplace les violations de contrats et les chaînes (chacune selon sa règle, FUR402 et FUR403, dans les agrégats comme dans le Top N) et les directives `foqa` inutiles (FUR001). Une catégorie sans note n'affiche pas non plus que « aucun fichier n'est en violation ». Les mesures restent affichées, y compris les comptes de fonctions et de classes au-dessus d'un seuil : elles ne dépendent pas de la sélection (§12.1, A68).

Tri du Top N : du plus mauvais score au meilleur ; à égalité, le fichier le plus long d'abord (lignes physiques, comme FUR102), puis par chemin (A64).

## 13. Tests et critères d'acceptation

- **Framework** : `unittest` uniquement. Commande : `uv run python -m unittest discover -s tests -t .`
- **Fixtures** : `tests/fixtures/<nom-de-règle>/ok_*.py` (aucun diagnostic) et `ko_*.py` + `ko_*.expected` (une ligne `LIGNE:COLONNE CODE` par diagnostic attendu). Chaque fixture est testée avec **sa seule règle sélectionnée**. `tests` est exclu par `furryp.json`.
- **Exemples de référence** : les valeurs du §11 (FUR101, et FUR203 avec ses incréments) sont des tests obligatoires.
- **Contrat du help** : pour chaque diagnostic produit par les fixtures `ko_*`, le `help` est non vide, tient sur une ligne de 160 caractères au plus, et ne contient ni `foqa` (sauf pour FUR001), ni `ignore`, ni `per-file`. Les aides des exemples de référence sont vérifiées au caractère près.
- **Fiches `furryp rule`** : chaque règle du registre a sa fiche avec toutes les sections ; l'exemple « flagged » déclenche la règle et l'exemple « fixed » ne la déclenche pas.
- **`foqa`** : une directive placée sur la dernière ligne d'une instruction repliée (`):  # foqa:FUR101`) supprime bien le diagnostic de la première ligne ; FUR001 signale en un seul diagnostic par directive les codes inutiles, non activés et en double, ignore les identifiants inconnus, et sa correction est idempotente ; chaque forme invalide donne son avertissement, sur stderr, sans changer le code de sortie.
- **Snapshots** : le rendu terminal (§5) est testé contre des fichiers `tests/snapshots/*.txt` (avec `os.sep` paramétré), dont l'exemple de référence du §5.1 au caractère près.
- **Bout en bout** (`subprocess` + `sys.executable -m furryp`, dans un dossier temporaire) : codes de sortie, pieds de page, `--statistics`, `--show-settings` (sortie rechargeable), `--fix` idempotent (une seconde passe ne change rien), `--diff` sans écriture, `--add-foqa` (format compact, fin de ligne logique, idempotence, `check` à 0 ensuite), `furryp rule` (code, nom, `--all`, inconnu → 2), préservation CRLF / BOM / encodage, combinaisons interdites, configuration invalide.
- **Multi-plateforme** : la suite DOIT passer sous Windows et sous Linux (CI matricielle recommandée).
- **Discipline d'E/S** : `tests/test_io_discipline.py` parcourt l'AST de `furryp/` et échoue si un appel `open`, `Path.open`, `read_text`, `write_text` ou `TextIOWrapper` n'a pas d'`encoding=` explicite (hors mode binaire), ou si une écriture en mode texte n'a pas de `newline=`. Les appels `subprocess` des tests utilisent `encoding="utf-8"`, sauf pour vérifier les octets bruts de la sortie (fins de ligne), où rien n'est décodé.
- **Encodages et fins de ligne** : `furryp.json` en UTF-8 avec BOM et caractères non ASCII ; source déclarant `# -*- coding: latin-1 -*-` corrigée puis relue à l'identique hors édition ; sortie non ASCII avec `PYTHONIOENCODING=cp1252` dans l'environnement du sous-processus, qui doit rester de l'UTF-8 valide ; `--fix` sur un fichier aux fins de ligne mixtes ne modifie que les lignes éditées.
- **CI** : chemin inexistant → FUR000 et code 1 ; dossier impossible à lister → avertissement, code inchangé ; dossier sans fichier Python → avertissement et code 0 ; sortie en `\n` sur toutes les plateformes ; violations + erreur interne → 2 ; `--exit-zero` ne masque pas 2 ; `--statistics` sort en 1 s'il y a des violations.
- **Rapport** : génération sur fixtures ; présence des sections ; Top N limité à N ; HTML bien formé (vérifié via `html.parser`) ; aucune ressource externe (`http`, `<script` absents).
- **Dogfooding** : `test_dogfooding.py` vérifie que `furryp check furryp` renvoie 0 diagnostic.
- **Hors périmètre** : `test_scope.py` vérifie le §2.2 (options et commandes refusées, pas de couleurs, `.gitignore` et entrée standard non lus, un seul fichier de configuration, ce que ruff contrôle non signalé), et parcourt l'AST de `furryp/` : aucune dépendance tierce ni parallélisme, ni `untokenize`, ni `splitlines`, et `ast.unparse` à un seul endroit.

## 14. Phases de réalisation

Ordre :

1. Squelette, configuration, découverte des fichiers, `--show-settings`.
2. Pipeline de diagnostics, sortie terminal (nom + code + `help`), `foqa` par ligne logique, sélection, `--statistics`, `--exit-zero`, `furryp rule` ; règles FUR000, FUR001 (diagnostics), FUR102.
3. Corrections : `--fix`, `--diff`, `--add-foqa` ; correction de FUR001.
4. Phase réalisée, puis retirée avec ses règles après la phase 8 (A73).
5. Taille et métriques : lignes de code, Halstead, complexité cognitive et ses contributions ; FUR101, FUR201 à FUR203.
6. Conception : FUR401, FUR403, FUR402, FUR404.
7. Rapport HTML.
8. Dogfooding complet, vérification des seuils, vérification du README.

## 15. Arbitrages pris par défaut

Chaque arbitrage peut être changé ; il faut alors mettre à jour la section concernée. **Validé** = confirmé explicitement ; **Retiré** = décision annulée, conservée pour la traçabilité ; sans mention = choix par défaut.

| ID | Décision | Section |
|---|---|---|
| A01 | **Retiré.** Plus de règle `Final`. | — |
| A02 | **Validé.** Les valeurs en dur (nombres et chaînes) ne sont pas contrôlées. | 11 |
| A03 | **Retiré** (A73). Portait sur le marqueur de fin de fichier. | — |
| A04 | **Retiré** (A73). Portait sur les en-têtes de section. | — |
| A05 | **Validé.** Avec `--report-html`, codes de sortie identiques à `check` (0/1/2), stdout muet. | 5.6 |
| A06 | **Validé (révisé).** En-tête : `{name} [{code}]: {message}`, et `{name} [{code}] [*]: {message}` si corrigeable. | 5.1 |
| A07 | **Validé.** Les exclusions s'appliquent aussi aux fichiers passés explicitement (pas de `--force-exclude`). | 8.5 |
| A08 | Contrats de couches : imports directs seulement ; imports `TYPE_CHECKING` inclus (comme TID251 de ruff 0.17.3, vérifié). | FUR402 |
| A09 | Halstead par tokens (pas par AST), avec les définitions du §11. | FUR201 |
| A10 | **Retiré.** L'indice de maintenabilité est supprimé (doublon des autres métriques). | 11 |
| A11 | **Retiré.** La complexité cyclomatique enrichie est supprimée. | 11 |
| A12 | FUR203 : `else` de boucle / `try`, gardes de `case` et clauses `if` de compréhension comptent +1. | FUR203 |
| A13 | Fonctions imbriquées : comptées dans le parent **et** évaluées seules (FUR101, FUR202) ; comptées dans le parent seulement pour FUR203. | 11 |
| A14 | Pas de couleurs ANSI en v1. | 2.2 |
| A15 | **Validé.** Le dogfooding porte sur `furryp/` ; `tests/` n'est pas soumis aux règles, et `furryp.json` l'exclut (`extend-exclude`), décision de l'utilisateur après la phase 8. | 3, 9.4, 13 |
| A16 | Développement avec uv ; `uv_build` comme backend de build (natif uv) ; arborescence plate `furryp/` à la racine (`module-root = ""`). | 3 |
| A17 | **Validé (révisé).** Comme ruff, un identifiant inconnu dans `foqa` est ignoré : il ne supprime rien, et FUR001 ne le signale que s'il est répété (`duplicated`). | FUR001 |
| A18 | `--statistics` au format `count<TAB>code<TAB>[*] name` ; le détail suit ruff (A61). | 5.4 |
| A19 | **Validé (révisé).** Tout en anglais, comme ruff : CLI, messages, aides, fiches `furryp rule` et rapport HTML. | 12.2 |
| A20 | Couche `lint` dédiée à l'exécution des règles, pour que `fix` puisse ré-analyser sans dépendre de `cli`. | 9.1, 9.4 |
| A21 | **Validé.** Aucune correction automatique ne déplace du code. | 7.3 |
| A22 | **Validé.** `foqa` utilise des **codes** ; `--add-foqa` écrit le format compact `# foqa:FUR101,FUR403`. | 6.1 |
| A23 | **Retiré** (A73). Portait sur l'emplacement des constantes. | — |
| A24 | Les anciennes phases 5 (taille) et 6 (métriques) sont fusionnées. | 14 |
| A25 | **Validé (révisé).** Les codes étaient renumérotés sans trou tant qu'aucun n'était implémenté. Ce n'est plus le cas : FUR401 à FUR404 gardent leur code malgré le retrait de `FUR3xx` (A73), décision de l'utilisateur. | 11 |
| A26 | **Validé.** Seules des corrections sûres existent ; plus d'option `--unsafe-fixes`. | 7.1 |
| A27 | **Validé (révisé).** La complexité de McCabe d'une fonction n'est pas une règle (doublon de ruff C901). Elle sert seulement à FUR401, qui en fait la somme par classe, ce que ruff n'a pas (A52). | 2.2, FUR401 |
| A28 | **Validé.** Les espaces en fin de ligne et les lignes vides relèvent de ruff (W291, W293, `ruff format`). | 2.2 |
| A29 | **Validé (révisé).** Contrat du `help:` : toujours présent, simple et factuel, sans contributeurs ni contournement (A54). | 11.0 |
| A30 | **Validé.** `furryp rule <code>` (forme recommandée) et `--all`, fiches Markdown dont les exemples sont testés. | 4.6 |
| A31 | **Validé.** Une directive `foqa` vaut pour toute la **ligne logique**, et `--add-foqa` l'écrit en fin de ligne logique : elle reste valide après un repli par `ruff format`. E501 résiduel accepté pour les lignes impossibles à replier. | 6, 6.1 |
| A32 | **Validé (révisé).** Comme ruff (RUF100), FUR001 signale les codes de règles non sélectionnées pour le fichier (`non-enabled`), même quand elle est la seule règle sélectionnée, et sa correction les retire. FUR001 ne peut pas être supprimée par `foqa`. | FUR001 |
| A33 | **Validé.** FUR001 `unused-foqa`, équivalent de ruff RUF100, avec correction. | FUR001 |
| A34 | Analyse par `ast` + `tokenize`, corrections par éditions textuelles ; ni `ast.unparse`, ni `untokenize`, ni `libcst` pour réécrire (dépendance tierce, inutile tant qu'aucune correction ne restructure le code). | 7.1 |
| A35 | Aucun encodage implicite : sources lues en octets + `detect_encoding`, `furryp.json` en `utf-8-sig`, rapport en UTF-8 et `\n`, stdout/stderr forcés en UTF-8 ; réécriture en octets, fins de ligne préservées. | 3.1 |
| A36 | CI comme ruff : chemin inexistant ou fichier illisible → FUR000 (code 1), dossier impossible à lister → avertissement (code inchangé), aucun fichier → avertissement (code 0), 2 l'emporte sur 1, sortie en `\n` partout. | 4.4, 5.7 |
| A37 | **Validé.** Pas de section « dérogations » dans le rapport. | 12 |
| A38 | **Validé.** Licence Unlicense, auteur skire666. | 3 |
| A39 | **Validé (révisé).** furryp est aligné sur la philosophie de ruff. Priorité à ruff : si la spécification diverge du comportement réel de ruff, ou si elle est insuffisante pour arbitrer un comportement, ruff l'emporte. Le comportement est vérifié sur ruff (0.17.3 lors des phases 2 à 6), puis reporté dans la spécification. Si ruff n'a pas d'équivalent, la question est posée à l'utilisateur. Un écart avec ruff n'existe que sur décision de l'utilisateur (A43). **Précision de l'utilisateur (phase 6)** : le but de furryp est une bonne qualimétrie ; aligné sur ruff, il doit rester productif. L'effet réel d'un choix est donc mesuré, et un choix qui nuit à la qualité des mesures est signalé à l'utilisateur, chiffres à l'appui, au lieu d'être appliqué sans rien dire. | toutes |
| A40 | **Retiré** (A73). Portait sur le marqueur de fin de fichier. | — |
| A41 | **Validé.** Sorties des corrections comme ruff 0.17.3 : `--diff` sans changement n'affiche rien ; pied de `--fix` sans `(… fixed, … remaining)` si rien n'a été corrigé ; message de `--add-foqa` sur stderr, rien si aucun ajout ; aucune correction sur un fichier qui ne se parse pas. | 5.2, 5.3, 6.1, 7.2 |
| A42 | **Retiré** (A73), sauf le test `TYPE_CHECKING`, qui suit ruff (nom, attribut, alias) et sert à FUR402. | 10.5 |
| A43 | **Validé.** Les messages des règles de fonction citent le nom qualifié, sans `<locals>` (`Parser.load`, `outer.inner`). Récursion de FUR203 : dans une méthode, seuls `self.name(...)` et `cls.name(...)` comptent. **Écart assumé avec ruff** (A39), confirmé par l'utilisateur après vérification : le C901 de ruff 0.17.3 cite le nom court (`load`). | 10.2, FUR101, FUR201 à FUR203 |
| A44 | **Validé.** Choix sans équivalent dans ruff (ni Halstead ni complexité cognitive) : `FSTRING_MIDDLE` et `TSTRING_MIDDLE` vides non comptés ; annotations de la signature d'une fonction imbriquée à 0 pour FUR203. | FUR201, FUR203 |
| A45 | **Validé.** FUR402 suit TID251 de ruff 0.17.3 (vérifié), contre la lettre de la première version de la fiche (« span de l'instruction ») : diagnostic sur l'instruction si le module de `from X import y` correspond, sur le nom importé sinon, et un seul diagnostic quand `X` correspond (`from X import a, b`). Import relatif au-dessus du premier niveau ignoré. Comme `banned-api` : clés manquantes ou inconnues refusées, motifs non contrôlés. | FUR402 |
| A46 | **Retiré.** Méthode vide de LCOM4, supprimé avec cette mesure (A50). Le premier paramètre redéfini par une fonction imbriquée reste un autre objet, comme pour PLR6301 (FUR404). | FUR404 |
| A47 | **Validé (révisé).** Sans équivalent dans ruff : avec `*`, chaque module concret compte à part, et les messages citent les modules concrets ; une chaîne finit sur son dernier `.attr`. | FUR402, FUR403 |
| A48 | **Validé.** `layers` : le niveau d'un module est celui de son motif le plus spécifique (le plus de segments, puis le moins de `*`). Proposé d'abord comme « le premier dans l'ordre », puis changé : pour `forbidden`, l'ordre ne décide que du motif cité, alors qu'ici il décide s'il y a violation. L'utilisateur l'a confirmé en demandant que la règle reste fonctionnelle, par exemple pour un MVP (la view n'importe pas le model, ce qu'expriment des contrats `forbidden`, testés), sans suranalyser les cas complexes : couvrir les cas évidents, le reste est un choix que le développeur assume. | FUR402 |
| A49 | **Retiré.** Méthodes héritées et méthodes vides de LCOM4, supprimé avec cette mesure (A50). | — |
| A50 | **Validé.** LCOM4 est retiré sur décision de l'utilisateur : trop de faux positifs, trop difficile à expliquer. Même après correction complète du graphe, 18 % des alertes seulement étaient de vrais positifs (36 % avec les cas limites), car LCOM4 mesure l'état partagé, pas la responsabilité. FUR401 et FUR404 le remplacent. | FUR401, FUR404 |
| A51 | **Validé.** Public : développeurs seniors et juniors. Chaque règle se comprend en une phrase, se configure simplement, et son `help` dit en une phrase quoi corriger ou regarder. La précision passe avant la sévérité. | 11 |
| A52 | **Validé.** FUR401 : somme par classe de la complexité de C901. Sur les 16 119 fonctions de `Lib` que ruff 0.17.3 mesure (hors `site-packages`), 16 100 sont identiques ; les 19 autres contiennent une classe locale, mesurée à part sur décision de l'utilisateur. Un `lambda` n'ajoute donc rien, comme chez ruff, qui ne compte aucune expression. Exclusions : classes de test et de dispatch. Maximum : 70 (A74). | FUR401 |
| A53 | **Validé.** FUR404 : nom repris de pylint (R0902), que ruff n'implémente pas. Exclusions : classes de test, données déclarées, classes de données par leurs méthodes. Maximum : 14 (A74). | FUR404 |
| A54 | **Validé.** Sorties alignées sur ruff 0.17.3, sur décision de l'utilisateur : « le but est de faire un linter, comme ruff ». Le `help` est une phrase simple et factuelle, qui laisse le choix de la solution ; les contributeurs sont retirés de toutes les règles, car trop de détail oriente la correction vers ce qui fait baisser le score, au détriment de la vision d'ensemble (loi de Goodhart). ruff n'affiche même aucun `help:` pour C901 ou PLR0913 : le `help` reste obligatoire dans furryp (A29), c'est la forme la plus proche. Les messages de mesure finissent par `({valeur} > {max})`. Les extraits suivent ruff : span sur plusieurs lignes tracé dans une marge, pas d'extrait pour tout le fichier, pas de gouttière après un soulignement. Sous le `help:`, le diff de la correction s'affiche comme chez ruff. L'en-tête `{name} [{code}]:` reste différent, confirmé par l'utilisateur (A06), et les extraits que ruff raccourcit par `…` ne le sont pas, ce que l'utilisateur a confirmé après la revue de phase 6. | 5.1, 11.0 |
| A55 | **Validé.** Méthodes d'une classe, décision de l'utilisateur : « Il faut tout compter, pas de code qui passe sous silence. Le comportement doit rester uniforme. » FUR401 et FUR404 comptent donc les fonctions du corps à toute profondeur de ses blocs ; une classe de dispatch compte ses `def`. Écart avec PLR0904 de ruff, qui s'arrête au corps direct, mais qui mesure autre chose. Effet sur `Lib` : 17 classes changent, et 2 de plus dépassent FUR401 (`socket` 58 → 80, `BaseSubprocessTransport` 66 → 74), soit 3,21 % au lieu de 3,13 % ; FUR404 reste à 43 classes. Les deux branches d'un `if` s'additionnent : `Popen` passe de 123 à 310, ses versions Windows et POSIX étant comptées ensemble. | FUR401, FUR404 |
| A56 | **Validé.** FUR402 : une instruction repliée est soulignée en entier, comme TID251 de ruff 0.17.3 (vérifié). | FUR402 |
| A57 | **Validé.** Rendu comme ruff 0.17.3 : largeur d'affichage du soulignement, remplacement des caractères invisibles (différent dans l'extrait et dans le diff), et coupure du diff au-delà de 4 lignes identiques. La largeur est calculée par `unicodedata`, une approximation de la bibliothèque de ruff, juste sur 36 365 des 36 706 caractères testés ; les autres sont très rares (jamos hangul, voyelles indiennes, marques préposées arabes). | 5.1 |
| A58 | **Validé.** Textes de ruff 0.17.3 : pied de page ``[*] {n} fixable with `--fix`.`` ; plus de ``(fixable with `--fix`)`` dans les aides, ruff ne l'écrivant jamais (`[*]`, le pied de page et le diff le disent déjà). | 5.2, 11.0 |
| A59 | **Validé.** `forbidden` : le premier motif dans l'ordre écrit est cité. TID251 de ruff 0.17.3 ne suit pas cet ordre (`["app.infra", "app"]` et l'ordre inverse citent `app`), et son choix n'a pas de règle lisible. L'ordre écrit est stable et s'explique ; positions et nombre de diagnostics restent ceux de TID251. | FUR402 |
| A60 | **Validé.** `--diff` sur un chemin inexistant ou un fichier illisible : rien n'est affiché, code 0, comme ruff 0.17.3 avec E902 sélectionné, ce qui est le cas par défaut (vérifié). ruff n'écrit `warning: Failed to lint {path}: {raison}` que si E902 est désélectionné, par exemple avec `--select F401` ; FUR000 étant toujours actif (§4.5), ce cas n'existe pas dans furryp. Décision de l'utilisateur : « si ruff affiche un avertissement, furryp aussi ». | 5.3 |
| A61 | **Validé.** `--statistics` comme ruff 0.17.3 (vérifié), décision de l'utilisateur : pas de ligne vide avant le pied de page, pas de marqueur si aucune règle du tableau n'est corrigeable, rien d'affiché sans violation. À compte égal, furryp trie par code ; ruff suit un ordre interne qui n'est pas celui des codes. | 5.4 |
| A62 | **Validé.** `rating-thresholds` vaut `[0.20, 0.40, 0.60, 0.80]` par défaut, décision de l'utilisateur après la phase 8. A ne veut plus dire « aucune violation » : une note A exigeait 0 %, et aspirabot avait B en Size pour 2 fichiers sur 372. Répartition A/B/C/D/E sur 19 paquets de 5 fichiers ou plus de `Lib` 3.14.3 (sans `test`, `site-packages`, `idlelib`, `turtledemo` ni `venv`) : Size 4/6/7/1/1, Complexity 8/4/5/2/0, Halstead 5/7/5/1/1, Design 17/2/0/0/0, contre 0/4/6/7/2, 1/7/4/5/2, 0/5/7/5/2 et 10/7/2/0/0 avec `[0, 0.20, 0.40, 0.60]`. Sur aspirabot (372 fichiers) : A dans les 4 catégories. La valeur d'origine `[0, 0.05, 0.10, 0.20]` saturait, avec 15 paquets sur 19 en E pour Size. J'avais recommandé `[0.05, 0.20, 0.40, 0.60]` : barème de l'utilisateur retenu. **À savoir** : Design ne sépare plus guère les paquets (17 A sur 19). | 8.4, 12.3 |
| A63 | **Validé.** Une catégorie sans règle sélectionnée, ou un rapport sans fichier analysé, n'a pas de note : `*` à la place de la lettre, et sa raison. À la lettre, `s = 0` donnait A : `--select FUR4` aurait noté A en Size, Complexity et Halstead un paquet comme `asyncio`, noté C, C et C par défaut. Une catégorie dont une seule règle reste active reste notée. | 12.3 |
| A64 | **Validé.** Top N, décision de l'utilisateur : « Si le score est OK, il n'a pas besoin d'être affiché dans les pires », du plus mauvais au meilleur, et à égalité le fichier le plus long d'abord. Seuls les fichiers en violation dans la catégorie sont listés. Une note par fichier a été écartée. L'égalité vaut pour toutes les catégories : le départage de Conception par complexité de classe est retiré, et « le plus long » se lit en lignes physiques, comme FUR102 (confirmé par l'utilisateur). `report.top-n` reste configurable, sans plafond : « 10 éléments maximum » désigne le défaut (confirmé par l'utilisateur). | 8.4, 12.3 |
| A65 | **Validé.** Fichiers non analysables : philosophie de SonarQube, décision de l'utilisateur. Comme lui, l'analyse continue (réponse de son équipe sur son forum), un avertissement reste visible en haut de la page avec un lien vers le détail (sa documentation, qui ne parle pas explicitement des fichiers non analysables), et une règle suit les échecs de lecture (FUR000 ; `python:ParsingError` d'après son forum). Les erreurs internes sont listées avec les fichiers en FUR000 : sinon un fichier disparaîtrait du rapport sans trace, stderr n'accompagnant pas l'artefact. **Écart avec SonarQube, décidé par l'utilisateur** (« Ruff reste la norme ») : il sort en 0 par défaut (d'après son forum, non vérifié dans sa documentation), alors que furryp garde les codes de ruff (A36), pour qu'une faute de frappe en CI ne donne pas un faux succès. | 12.1, 12.3 |
| A66 | `--report-html` écrit comme `--output-file` de ruff 0.17.3 (vérifié) : dossiers parents créés, code 2 si la cible ne peut pas être écrite, aucun fichier en cas d'erreur de configuration, avertissement et rapport écrit s'il n'y a aucun fichier Python. | 5.6 |
| A67 | Rapport, sans équivalent dans ruff : la carte des violations ne compte que les fichiers analysés (§12.1), donc elle peut être inférieure au `Found N errors` de `check`, dont le code de sortie reste identique (confirmé par l'utilisateur) ; les tableaux par règle ne montrent que les règles sélectionnées ; les agrégats de Conception portent sur les classes évaluées par la règle (hors test, dispatch, données) ; « contrats » et « chaînes » sont les violations de FUR402 et FUR403 ; la durée vient de la même horloge injectable que l'horodatage, pour un fichier identique à horloge fixe ; un gabarit par catégorie, les libellés étant portés par les gabarits (§12.2) ; un Top N vide garde l'en-tête de son tableau, et la section des erreurs vide n'affiche que sa phrase ; les mesures sont lues fichier par fichier, à l'intérieur de la gestion des erreurs par fichier ; entiers `1,234`, réels à 2 décimales, parts `33.3% (1/3)`, médiane toujours réelle ; `errors="replace"` à l'écriture (§12.2) ; sections ouvertes à l'écran, annexe fermée à l'écran et imprimée ; échelle `#056f05`, `#58a618`, `#f7c531`, `#e87a3e`, `#b82a2a`, la lettre restant toujours affichée. | 12.2, 12.3 |
| A68 | **Validé.** Un chiffre tiré d'une règle qui n'a pas tourné est inconnu, pas nul : `–`, et pas de phrase rassurante dans une catégorie sans note. Signalé par la revue de phase 7, recommandation suivie par l'utilisateur : avec `--select FUR1`, le rapport affichait `Contract violations: 0` et « No file has a violation » à côté du `*`. C'est le raisonnement d'A63, étendu aux chiffres. Les mesures restent affichées : elles ne viennent pas de la règle (§12.1). | 12.3 |
| A69 | **Validé.** Les agrégats de Conception comptent aussi les classes vides : « il faut tout compter » (A55), recommandation suivie par l'utilisateur, et confirmée après les mesures de la phase 8. Sur `Lib` de Python 3.14 (572 fichiers, sans `test`, `site-packages`, `idlelib`, `turtledemo` ni `venv`), 712 classes sur les 2451 évaluées par FUR401 ont une complexité de 0 (29,0 %) : moyenne 11,04, médiane 2, 3,06 % au-dessus de 70, contre 15,56, 5 et 4,31 % sans elles. Pour FUR404, 675 classes sur 1377 n'ont aucun attribut. | 12.3 |
| A70 | Ligne de commande comme ruff 0.17.3 (vérifié, phase 8) : pas d'abréviation d'option (`--stat`, `--sel`) ; un élément vide ou entouré de blancs dans `--select`, `--extend-select` ou `--ignore` est un identifiant inconnu, code 2. Avant, `--select ""` désactivait toutes les règles et sortait en 0 : un faux succès en CI. | 4.2, 4.5 |
| A71 | **Validé (révisé).** Forme des directives et avertissements comme `# noqa` dans ruff 0.17.3, décision de l'utilisateur après la phase 8 : « Suivre ruff ». Le premier mot-clé d'un commentaire compte, même invalide, et un avertissement explique pourquoi une directive est sans effet. **Conséquence acceptée** : `--add-foqa` n'est pas idempotent après une directive invalide, comme `--add-noqa`. J'avais proposé l'inverse. La forme remplace l'expression de référence d'origine, trouvée en défaut sur un projet réel : un commentaire citant `` `# foqa` `` était signalé, puis vidé par `--fix`. Aide de FUR001 : texte de RUF100. **Comparaison sur 153 formes** (effet, RUF100, avertissements, texte après `--fix`) : 149 identiques ; 3 ne diffèrent que par la casse du mot-clé, que ma comparaison ne ramenait pas, et 1 parce que `F401` se déclenche vraiment dans son exemple, pas la règle qui le remplace. **Différences restantes** : un nom de règle existante est lu comme un code (§4.5, ruff n'a que des codes) ; le format compact (A22) ; `--add-foqa` écrit l'avertissement une fois, et ruff deux, car il relit le fichier ; aucun avertissement sur un fichier qui ne se tokenise pas, faute de tokens (§6). | 6, 6.1, FUR001 |
| A72 | Cohabitation avec `ruff format`, mesurée en phase 8 et rejouée après le retrait de FUR301 à FUR304, limites identiques à ruff 0.17.3 (vérifié). **Instruction composée sur une ligne** : la directive ajoutée par `--add-foqa` suit le corps après formatage et n'agit plus, comme `--add-noqa` ; reproduit sur un exemple, aucun cas sur `Lib`. **Retrait d'une directive par FUR001** : `ruff format` peut encore changer le code, comme après RUF100 (exception du §7.1). Sur `Lib` de Python 3.14.3 avec `test` (1842 fichiers rapportés par `ruff format` sur ma copie, 1840 sur celle de la revue de phase 8, 1699 réécrits) : `--add-foqa` puis `ruff format` laisse 750 diagnostics, parce que le formatage change les mesures ; `ruff format` d'abord en laisse 4, puis 3 après un second tour, tous en FUR000. Retrait de 5818 directives : 132 fichiers à reformater. Sur aspirabot (372 fichiers), tout passe, déjà formaté. | 6.1, 7.1 |
| A73 | **Validé.** FUR301 à FUR304 et le modèle de sections (`ModuleLayout`) sont retirés, décision de l'utilisateur après la phase 8. Conséquences : 11 règles ; seule FUR001 a une correction ; plus de catégorie Structure dans le rapport, donc 4 notes ; les codes restants ne changent pas (A25) ; `FUR3` n'est plus un préfixe valide (code 2 avec suggestion). Les arbitrages qui n'avaient plus d'objet sont marqués « Retiré ». Le code de furryp ne porte plus ni ces en-têtes ni ce marqueur : `AGENTS.md` est aligné, à la demande de l'utilisateur. | 2.1, 7.3, 8.4, 11, 12.3 |
| A74 | **Validé.** Seuils de la phase 8, décision de l'utilisateur : aucune valeur ne change, et les phrases qui annonçaient 1 à 5 % sont corrigées. Part signalée sur `Lib` de Python 3.14.8 sans `test`, puis 3.14.3 avec et sans `test` : FUR203 4,25 / 1,62 / 3,92 % ; FUR401 3,21 / 1,00 / 3,06 % ; FUR404 2,81 / 1,20 / 2,70 % ; FUR202 5,69 / 5,70 / 5,56 % ; FUR101 6,61 / 6,10 / 6,39 % ; FUR102 9,16 / 11,35 / 8,47 % ; FUR201 9,31 / 13,57 / 8,33 % ; FUR403 0,01 / 0,03 / 0,01 %. | 8.4, FUR203, FUR401, FUR404 |
| A75 | **Validé.** Aides de FUR201 et FUR202, décision de l'utilisateur : `does a lot` remplace `holds a lot of logic`, trompeur sur du code d'interface (complexité cognitive médiane de 1 sur les 74 alertes de FUR202 d'aspirabot). La signature reste comptée dans FUR202 : plus simple à expliquer, alors que 28 de ces 74 alertes passeraient sans elle. Le nombre de paramètres relève de PLR0913 de ruff. | FUR201, FUR202 |
| A76 | **Validé.** FUR001 et `--add-foqa` comme ruff 0.17.3, trouvé par la revue de phase 8, recommandation suivie par l'utilisateur. **Directive de fichier d'abord** : elle supprime le diagnostic, et une directive de ligne qui le couvre aussi est signalée comme inutile. **`# furryp: foqa` global** : il exempte tout son fichier de FUR001, directives de ligne comprises. **Dernière ligne sans fin de ligne** : `--add-foqa` lui en ajoute une s'il la modifie. **À savoir** : un `# furryp: foqa` devenu inutile n'est plus signalé et continue de tout masquer dans son fichier ; `--add-foqa` n'en écrit jamais, et les violations restent comptées dans la colonne « Suppressed » du rapport. **Différences restantes** : une directive qui nomme FUR001 ne la supprime pas, alors que ruff accepte `# noqa: RUF100` (A32) ; un fichier sans aucune fin de ligne reçoit `\n` sur toutes les plateformes, alors que ruff écrit celle du système (`\r\n` sous Windows). | 6, 6.1, FUR001 |
| A77 | **Validé.** Seuils par défaut, décision de l'utilisateur, qui remplacent ceux d'A74 : `function-too-long` 26 (au lieu de 25), `file-too-long` 1000 (1200), `halstead-file` 15000 (40000), `halstead-function` 1200 (1000), `cognitive-complexity` 16 (20), `too-complex-class` 80 (70), `too-many-instance-attributes` 20 (14).
| A78 | **Validé.** Anomalies de `uvx ruff check .` (ruff 0.17.3, `pyproject.toml` du projet, 57 fichiers `.py`, `tests/` exclu par `extend-exclude`), recommandation suivie par l'utilisateur : 57 → 0, sans toucher aux seuils ni ajouter de suppression. Trois conséquences sur la structure : `ALL_RULES` est défini dans `rules/catalog.py` et réexporté par `rules/__init__.py` (RUF067) ; les messages d'erreur vivent dans les classes d'exception (TRY003) ; `Html` du rapport est un dataclass gelé et non plus un `str` (FURB189 : le `UserString` conseillé par ruff casse `join` et `write_text`). Les sorties ne changent pas : sortie par défaut et `--statistics` identiques sur une copie de `tests/`, rapport HTML identique hors date et temps d'analyse. L'arborescence du §9.1 reçoit aussi les modules qui y manquaient : `schema.py`, `errors.py`, `paths.py`, `fix_preview.py`. | 9.1, 9.2 |
| A79 | **Validé.** Largeur de ligne de 120 colonnes, décision de l'utilisateur (`line-length` de `pyproject.toml`), appliquée par `uvx ruff format .` (ruff 0.17.3) : 38 fichiers, AST identique sur les 57 modules de `furryp/` (`tests/` exclu par `extend-exclude`). **Effet mesuré sur `furryp/`** : 6 565 → 6 057 lignes physiques, 4 297 → 3 789 lignes de code (−11,8 %), longueur moyenne d'une fonction 5,55 → 4,95, fonctions de 20 lignes ou plus 4 → 1, maximum inchangé (24). Aucun seuil ne change, mais à code égal FUR101 et FUR102 sont moins serrés sur ce projet. **Docstrings** : `ruff format` ne les replie pas. Sur 65 paragraphes qui perdraient au moins une ligne à 120 colonnes (79 lignes), seuls les 17 qui tiennent en entier sur une ligne sont rejoints, l'utilisateur ne voulant pas reprendre tout l'existant ; 48 restent tels quels (62 lignes). **Exemple de FUR101** : il reposait sur un appel replié, que `skip-magic-trailing-comma` rejoint (5 → 3 lignes, plus de violation) ; la SPEC annonçait déjà 4 lignes pour 3 depuis `f89568d`. Il est réécrit sans repli (4 lignes) dans la SPEC, la fiche et le test. | FUR101 |