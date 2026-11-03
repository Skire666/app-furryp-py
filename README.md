# furryp — guide de prise en main

`furryp` est un linter Python local, sans aucune dépendance (bibliothèque standard uniquement), inspiré de **ruff** : mêmes réflexes en ligne de commande, même style de sortie. Il ne remplace pas ruff, il le complète. Il contrôle deux choses :

- la **taille et la complexité** du code : longueur des fonctions et des fichiers, Halstead, complexité cognitive ;
- la **conception** : complexité et attributs des classes, contrats de couches, loi de Déméter.

Chaque violation est accompagnée d'une aide en une phrase. furryp sait aussi retirer seul les directives devenues inutiles, geler la dette existante et produire un rapport HTML d'audit.

---

## 1. Installation

Prérequis : **Python 3.14** ou plus récent. Rien d'autre.

Avec [uv](https://docs.astral.sh/uv/) (recommandé) :

```bash
# commande `furryp` disponible partout (suit les modifications du dépôt de furryp)
uv tool install --editable <chemin-vers-furryp>

# ou comme outil de développement d'un projet précis, puis `uv run furryp check`
uv add --dev <chemin-vers-furryp>

# ou en ponctuel, sans rien installer, depuis le projet à analyser
uv run --project <chemin-vers-furryp> furryp check
```

Sans uv : `python -m pip install <chemin-vers-furryp>` (sous Windows, `py -3.14 -m pip install …` si plusieurs versions de Python coexistent).

Vérification :

```bash
furryp --version
```

Sans installation, depuis la racine du dépôt de furryp : `python -m furryp check <chemins>`.

## 2. Démarrage en 2 minutes

```bash
furryp check                      # analyse le dossier courant
furryp check src/ tests/test_x.py # analyse des chemins précis
furryp check --statistics         # combien de violations, par règle
furryp rule FUR203                # comprendre une règle avant de corriger
furryp check --diff               # aperçu des corrections automatiques, sans rien écrire
furryp check --fix                # applique les corrections automatiques
furryp check --report-html audit.html   # rapport d'audit, rien sur le terminal
```

## 3. Lire la sortie

```
function-too-long [FUR101]: Function `load_config` has too many lines of code (31 > 25)
  --> src\app\config.py:42:5
   |
41 | @cache
42 | def load_config(path: Path) -> Config:
   |     ^^^^^^^^^^^
43 |     """Load and validate the configuration."""
44 |     raw = path.read_text(encoding="utf-8")
   |
help: Long functions are hard to read and test; consider splitting this one

Found 1 error.
```

- **1re ligne** : `nom-de-la-règle [CODE]: message`. Dans une règle de mesure, le message se termine par la **valeur mesurée** et le **seuil** : `(31 > 25)`. `[*]` après le code signale une correction automatique disponible.
- **`-->`** : `fichier:ligne:colonne` (cliquable dans VS Code).
- **Extrait** : la portion de code en erreur, soulignée comme par ruff, avec jusqu'à 2 lignes de contexte. Une erreur qui vise tout le fichier n'a pas d'extrait.
- **`help:`** : toujours présent : une phrase simple sur le problème, qui vous laisse le choix de la solution. Le détail de chaque règle est dans `furryp rule <code>`. Si une correction automatique existe, son diff s'affiche juste dessous (`-` retiré, `+` ajouté), comme dans ruff.
- **Pied de page** : le total, puis le nombre de violations corrigeables avec `--fix`.

Le **nom** sert à lire ; le **code** (`FUR101`) sert à agir : `foqa`, `--select`, `furryp rule`. Les deux sont acceptés partout.

| Code de sortie | Signification |
|---|---|
| 0 | Aucune violation (ou `--exit-zero`). |
| 1 | Au moins une violation (ou `--diff` qui proposerait des changements). Un chemin inexistant passé en argument compte comme une violation (`FUR000`). |
| 2 | Erreur : option invalide, configuration invalide, règle inconnue, erreur interne. Le code 2 l'emporte sur le code 1, même avec `--exit-zero`. |

### Comprendre une règle : `furryp rule`

```bash
furryp rule FUR203        # forme recommandée (le nom fonctionne aussi)
furryp rule --all         # toutes les fiches
```

Chaque fiche explique ce qui est mesuré, pourquoi, les options (avec les valeurs **effectives** de votre configuration), comment bien corriger, ce qu'il ne faut pas faire, et un exemple avant / après.

## 4. Les règles

| Code | Nom | Ce qui est mesuré | Seuil par défaut | `--fix` |
|---|---|---|---|---|
| FUR000 | `invalid-syntax` | Fichier illisible ou syntaxe invalide (non désactivable) | — | non |
| FUR001 | `unused-foqa` | Directive `foqa` inutile, de règle non activée ou en double | — | **oui** |
| FUR101 | `function-too-long` | Lignes de code d'une fonction (hors vides, commentaires, docstring) | 25 | non |
| FUR102 | `file-too-long` | Lignes totales du fichier | 1200 | non |
| FUR201 | `halstead-file` | Volume Halstead du fichier | 40000 | non |
| FUR202 | `halstead-function` | Volume Halstead d'une fonction | 1000 | non |
| FUR203 | `cognitive-complexity` | Complexité cognitive d'une fonction | 20 | non |
| FUR401 | `too-complex-class` | Somme des complexités des méthodes d'une classe | 70 | non |
| FUR402 | `layer-violation` | Import interdit par un contrat de couches | contrats à définir | non |
| FUR403 | `demeter-chain` | Profondeur d'une chaîne `a.b.c.d` | 3 | non |
| FUR404 | `too-many-instance-attributes` | Nombre d'attributs d'instance d'une classe | 14 | non |

Les seuils s'inspirent de la bibliothèque standard de Python 3.14, où ils signalent entre 1 et 14 % des cas selon la règle (bien moins pour `demeter-chain`). Ajustez-les à votre projet (section 5). La seule correction automatique, le retrait d'une directive inutile, est **sûre** : elle ne touche jamais au comportement du code.

### Bien corriger, et ce qu'il ne faut pas faire

| Règle | Bonne correction | À éviter (la règle passe, le problème reste) |
|---|---|---|
| `function-too-long` | Extraire une étape cohérente dans une fonction bien nommée. | Coller plusieurs instructions sur une ligne ; découper en `_part1` / `_part2` sans logique. |
| `halstead-*` | Réduire ce que fait chaque fonction ; supprimer la duplication. | Raccourcir les noms de variables. |
| `cognitive-complexity` | Simplifier le déroulé : retours anticipés, extraction des branches imbriquées, conditions nommées. | Déplacer la même imbrication dans une fonction appelée une seule fois. |
| `too-complex-class` | Déplacer un groupe de méthodes liées dans une nouvelle classe. | Déplacer la logique dans une classe parente ou un mixin. |
| `too-many-instance-attributes` | Regrouper dans un objet à part les attributs qui vont toujours ensemble. | Cacher les attributs dans un dictionnaire. |
| `layer-violation` | Inverser la dépendance (interface dans la couche basse). | Importer dans une fonction ou via `importlib` pour masquer l'import. |
| `demeter-chain` | Demander le service au premier objet de la chaîne (`order.total()`). | Découper la chaîne en variables intermédiaires : le couplage est identique. |
| `unused-foqa` | `furryp check --fix`. | Ajouter le code ailleurs pour « faire servir » la directive. |

Quand une même fonction déclenche plusieurs règles (longueur, Halstead, cognitive), c'est **un seul problème** : refactorez la fonction une fois, puis relancez.

## 5. Configuration

### Où et comment

furryp cherche `pyproject.toml` en remontant depuis le dossier courant, puis lit **`furryp.json` à côté**. Sans ce fichier, les valeurs par défaut s'appliquent. `--config chemin.json` force un autre fichier.

```bash
furryp check --show-settings   # affiche la configuration complète, défauts inclus
```

La sortie de `--show-settings` contient toutes les clés avec leurs valeurs. Pour créer votre `furryp.json`, n'en gardez que ce que vous changez. Priorité : options de la ligne de commande, puis `furryp.json`, puis valeurs par défaut.

### Exemple

```json
{
  "extend-exclude": ["tests/fixtures", "migrations"],
  "ignore": ["FUR201"],
  "per-file-ignores": { "tests/**": ["FUR101", "FUR403"] },
  "rules": {
    "function-too-long": { "max-lines": 30 },
    "cognitive-complexity": { "max": 12 },
    "layer-violation": {
      "source-roots": ["src"],
      "contracts": [
        { "type": "forbidden", "name": "domain-sans-infra", "source": ["app.domain"], "forbidden": ["app.infra"] },
        { "type": "layers", "name": "couches", "layers": ["app.api", "app.service", "app.domain"] }
      ]
    }
  }
}
```

- **Fichiers** : `include` (défaut `**/*.py`), `exclude` (dossiers usuels : `.venv`, `build`, `__pycache__`…), `extend-exclude` pour ajouter sans remplacer. Un motif sans `/` vise un nom de dossier ou de fichier à n'importe quel niveau ; un motif avec `/` vise un chemin relatif à la racine (`**` accepté). Les exclusions s'appliquent même aux fichiers passés explicitement.
- **Règles actives** : `select` (défaut `["FUR"]`, tout), `extend-select`, `ignore`. On peut viser une famille par préfixe : `FUR2` = complexité, `FUR4` = conception. `ignore` l'emporte toujours.
- **Réglages par règle** : sous `rules`, par nom de règle. Une clé inconnue ou une valeur invalide arrête furryp (code 2) avec une suggestion (`did you mean "max-lines"?`). `furryp rule <code>` liste les options d'une règle.
- **Contrats de couches** : trois types. `forbidden` (A n'importe jamais B), `layers` (du plus haut au plus bas : on n'importe jamais vers le haut) et `independence` (des modules frères qui ne s'importent pas entre eux).

La même sélection se règle en ligne de commande : `--select FUR1,FUR203`, `--ignore FUR403`, `--extend-select FUR4`.

## 6. Ignorer une violation : `foqa`

```python
def legacy_entry_point(args):  # foqa:FUR101
    ...

result = order.customer.address.city.upper()  # foqa:FUR403
```

- `# foqa:CODES` : ignore ces règles pour les violations qui commencent dans **la même instruction** que le commentaire (toutes ses lignes si elle est répartie sur plusieurs). Le commentaire peut donc être sur la dernière ligne d'un appel ou d'une signature repliée, là où `ruff format` le déplace.
- `# furryp: foqa:CODES` sur sa propre ligne, n'importe où dans le fichier : ignore ces règles **pour tout le fichier**. C'est indispensable pour les règles de niveau fichier (`FUR102`, `FUR201`). Placée après du code, elle n'a aucun effet.
- `# foqa` seul ignore tout sur l'instruction : à éviter, c'est trop large. `# foqa FUR101`, sans deux-points, ignore tout aussi, comme `# noqa E501` dans ruff.
- Utilisez les **codes** (les noms sont acceptés, mais plus longs).
- `FUR000` et `FUR001` ne peuvent pas être ignorés par `foqa`.
- `# foqa` et `# noqa` (ruff) cohabitent sur la même ligne, dans n'importe quel ordre.
- Comme pour `# noqa` dans ruff, seule la première directive d'un commentaire compte. Une directive mal formée (`# foqa.`, `# foqa:FUR101;`) n'a aucun effet, et un avertissement sur stderr l'indique.

Les violations ignorées n'apparaissent plus dans le terminal, mais elles restent **comptées dans le rapport HTML**. Une directive qui ne sert plus à rien (le problème a été corrigé, la règle n'est pas activée pour ce fichier, ou le code est en double) est signalée par **`unused-foqa` (FUR001)** et retirée par `--fix` : les `foqa` ne s'accumulent pas. Comme dans ruff, un `# furryp: foqa` global exempte son fichier de cette règle, et il n'est donc jamais signalé. Comme ruff le fait pour `# noqa`, un code inconnu (faute de frappe) est ignoré : il ne supprime rien et n'est pas signalé.

## 7. Adopter furryp sur un projet existant

Le premier lancement sur un projet existant produit souvent beaucoup de violations. La démarche conseillée :

1. **Mesurer** : `furryp check --statistics`.
2. **Choisir ses règles** : ajustez `select`, `ignore` et les seuils dans `furryp.json`.
3. **Geler la dette** : `furryp check --add-foqa` ajoute un `# foqa:CODE` sur chaque violation restante (ou une ligne `# furryp: foqa:…` en tête de fichier pour les règles de niveau fichier). Lancez ensuite `ruff format` : si une ligne est devenue trop longue, ruff la replie et la directive reste valide. Si le projet n'est pas encore formaté, lancez `ruff format` avant `--add-foqa`, et une seconde fois après. Committez ce changement à part. Désormais, seules les **nouvelles** violations apparaissent.
4. **Suivre** : `furryp check --report-html audit.html` à intervalles réguliers. La colonne « Suppressed » montre la dette gelée qui reste à résorber.
5. **Résorber** : corrigez au fil des modifications. Dès qu'une violation gelée disparaît, `unused-foqa` le signale, et `furryp check --fix` retire la directive.

## 8. Le rapport HTML d'audit

```bash
furryp check --report-html audit.html
```

Le rapport est un seul fichier HTML : il s'ouvre hors ligne, s'imprime et ne contient aucun script. Il présente :

- une **synthèse** : fichiers, lignes, fonctions, classes, violations, densité pour 1000 lignes de code, violations ignorées par `foqa`, directives `foqa` inutiles, corrections disponibles, et une note de A à E par catégorie ;
- une **section par catégorie** (Size, Complexity, Halstead, Design) : moyennes, médianes, maximums, violations par règle et les **10 pires fichiers** (réglable via `report.top-n`) : seuls les fichiers en violation sont listés, du pire score au meilleur, et à égalité le fichier le plus long d'abord ;
- les fichiers **non analysables** (erreur de syntaxe, fichier illisible, erreur interne), annoncés par un bandeau en haut du rapport ;
- la **configuration effective**, en annexe.

Les métriques sont calculées pour tous les fichiers, même pour les règles désactivées ; les violations, elles, respectent la sélection et les `foqa`.

Note de catégorie : la part de fichiers ayant au moins une violation dans la catégorie. A ≤ 20 %, B ≤ 40 %, C ≤ 60 %, D ≤ 80 %, E au-delà (réglable via `report.rating-thresholds`). A ne veut donc pas dire « aucune violation ». Une catégorie dont aucune règle n'est sélectionnée, ou un rapport sans fichier analysé, n'a pas de note : un `*` remplace la lettre, avec la raison.

**À savoir pour un audit** : les mesures suivent les définitions de furryp (Halstead compté sur les tokens, complexité cognitive adaptée à Python). Elles ne sont pas directement comparables à celles de SonarQube ou de radon.

## 9. Intégration continue

furryp s'utilise tel quel en CI, comme ruff : `0` si rien n'est à signaler, `1` sinon, `2` en cas d'erreur. La sortie est sans couleur, déterministe et toujours en UTF-8, quelle que soit la plateforme.

```bash
uv tool install <chemin-ou-dépôt-de-furryp>                   # ou : python -m pip install …
furryp check                                                  # échoue (code 1) s'il reste une violation
furryp check --report-html furryp-report.html --exit-zero    # rapport à publier comme artefact, sans faire échouer
```

Hook [pre-commit](https://pre-commit.com) local. furryp doit être installé avec `uv tool install` (section 1). pre-commit passe les fichiers modifiés en argument ; les exclusions de `furryp.json` s'appliquent quand même :

```yaml
repos:
  - repo: local
    hooks:
      - id: furryp
        name: furryp
        entry: furryp check
        language: system
        types: [python]
```

À savoir :

- un chemin mal saisi produit une violation `FUR000` (code 1), pas un faux succès ;
- un dossier qui ne contient **aucun** fichier Python donne un avertissement et le code 0 (comme ruff) : vérifiez les chemins de votre pipeline ;
- pour une CI multi-plateforme, faites tourner le même job sous Windows et Linux : furryp ne dépend ni de l'encodage du système ni des fins de ligne.

## 10. Cohabiter avec ruff

furryp est conçu pour tourner **à côté** de ruff, et **ruff a toujours la priorité**. Ce qui suit a été vérifié avec ruff 0.17.3.

- **Laissez à ruff** : la complexité de McCabe d'une fonction (`C901`), les espaces en fin de ligne (`W291`, `W293`), les lignes vides (`ruff format`), le tri des imports (`I001`). furryp ne les contrôle pas.
- **Compatible** :
  - furryp ne signale jamais le style produit par `ruff format`, mais un repli peut faire dépasser un seuil de mesure ;
  - après le retrait d'une directive par `--fix`, relancez `ruff format` : comme après `RUF100`, il peut rejoindre une ligne que la directive avait fait replier ;
  - `# noqa` et `# foqa` cohabitent sur une même ligne ;
  - quand `ruff format` replie une instruction et déplace un `# foqa` sur sa dernière ligne, la directive reste valide.
- **Point d'attention** : ruff exclut `# noqa` du calcul de longueur de ligne (`E501`), mais pas `# foqa`. Après `--add-foqa`, lancez `ruff format`. Seule une ligne impossible à replier (une longue chaîne, par exemple) peut garder un `E501`.
- **Recouvrement partiel** : `function-too-long` (lignes de code) et `PLR0915` de ruff (nombre d'instructions) mesurent la taille différemment. Gardez les deux, ou choisissez-en une.

## 11. Utiliser furryp avec un assistant de code (LLM)

La sortie est conçue pour être lue telle quelle par un humain comme par un LLM : positions exactes, valeur mesurée et seuil dans le message des règles de mesure, `help:` qui résume le problème, code de règle visible, ordre stable d'une exécution à l'autre.

Consignes à copier dans le fichier d'instructions de votre agent (`CLAUDE.md`, `AGENTS.md`…) :

```markdown
## furryp
- Commencer par `furryp check --statistics`, puis traiter une famille à la fois (`--select FUR1`, `--select FUR4`…).
- Avant de corriger une règle pour la première fois, lire sa fiche : `furryp rule <CODE>`.
- Lire la ligne `help:` : elle résume le problème sans imposer de solution. Regarder la fonction ou la classe dans son ensemble avant de corriger.
- Lancer `furryp check --diff` avant `furryp check --fix`.
- Une fonction qui déclenche plusieurs règles = un seul refactoring, pas un correctif par règle.
- Ne jamais ajouter de `# foqa`, de `per-file-ignores`, ni relever un seuil dans `furryp.json` sans accord humain explicite.
- Ne jamais contourner une règle : pas d'instructions collées sur une ligne, pas de variables intermédiaires pour casser une chaîne d'attributs, pas d'import dans une fonction ou via importlib pour masquer une dépendance.
```

## 12. Dépannage

| Symptôme | Cause et solution |
|---|---|
| `error: furryp.json: rules.function-too-long.max_lines: unknown key` | Faute de frappe : les clés s'écrivent avec des tirets (`max-lines`). Le message propose la bonne clé. |
| `unused-foqa [FUR001]` après un refactoring | La violation gelée a disparu : `furryp check --fix` retire la directive. |
| `unused-foqa [FUR001]` … `(non-enabled: …)` | La directive cite une règle désactivée pour ce fichier (`select`, `ignore`, `per-file-ignores`, options `--select` / `--ignore`). Comme ruff, FUR001 la signale : réactivez la règle ou retirez le code. |
| Un `# foqa` semble sans effet | Code mal saisi : comme ruff, un code inconnu est ignoré sans avertissement. `furryp rule --all` liste les codes valides. Autre cause : une forme invalide (`# foqa.`, `# foqa:FUR101;`) annule la directive, ou une directive plus tôt dans le commentaire la masque ; un avertissement le signale sur stderr, sauf si cette première directive est valide. |
| `invalid-syntax [FUR000]` sur un fichier | Le fichier ne se parse pas en Python 3.14 : les autres règles ne s'appliquent pas à ce fichier, seule la longueur est vérifiée. |
| Un fichier attendu n'est pas analysé | Il est exclu (`exclude`, `extend-exclude`), même s'il est passé explicitement en argument. `--show-settings` montre la configuration effective. |
| Caractères illisibles dans une console Windows | furryp écrit toujours en UTF-8 (y compris redirigé vers un fichier ou un journal de CI). Utilisez le terminal de VS Code ou Windows Terminal, qui affichent l'UTF-8. |
| `invalid-syntax [FUR000]: Failed to read file` | Le chemin passé en argument n'existe pas ou n'est pas lisible. |
| `invalid-syntax [FUR000]: Failed to decode file` | Le fichier n'est pas en UTF-8 et ne déclare pas son encodage : enregistrez-le en UTF-8, ou ajoutez une ligne `# -*- coding: … -*-`. |
| Les fins de ligne ont changé après `--fix` | Ne devrait jamais arriver : furryp réécrit en binaire et ne touche qu'aux lignes corrigées. Si c'est le cas, c'est un bug à signaler. |
| Le rapport n'affiche rien dans le terminal | C'est voulu : `--report-html` n'écrit que le fichier. Le code de sortie indique toujours s'il y a des violations. |

Pour aller plus loin : `furryp rule --all` pour les fiches de toutes les règles, et `SPEC.md` pour la spécification complète.

---

Auteur : skire666 · Licence : [Unlicense](https://unlicense.org) (domaine public) · Toute la sortie de furryp (terminal, aides, fiches, rapport HTML) est en anglais.
