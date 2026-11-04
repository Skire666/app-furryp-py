# Utiliser furryp

`furryp` est un linter Python local, sans aucune dépendance, inspiré de **ruff**. Il mesure la **taille**, la **complexité** et la **conception** du code. Il complète ruff sans le remplacer : il ne formate rien et ne contrôle ni le style, ni les espaces, ni l'ordre des imports.

Si vous découvrez furryp, lisez les sections 1 à 3. Le reste sert de référence.

## TLDR :

```bash

# pour lancer les tests avec l'env
uv sync
uv run python -m unittest discover -s tests -t .

# installer en tant que commande, utilisable partout
uv tool install --editable ./

# dans le dossier du projet à analyser, spécifier le dossier
clear ; furryp check __src__

# aperçu : liste ce qui serait supprimé, sans rien toucher
git clean -ndX

# supprime vraiment
git clean -fdX
```

## Aide-mémoire

| Je veux… | Commande |
|---|---|
| Compter les violations, par règle | `furryp check --statistics` |
| Voir le détail | `furryp check` |
| Analyser un dossier ou un fichier | `furryp check src/ tests/test_x.py` |
| Comprendre une règle | `furryp rule FUR202` |
| Lancer une seule règle ou une famille | `furryp check --select FUR403` ou `--select FUR4` |
| Voir ce que `--fix` changerait | `furryp check --diff` |
| Retirer les directives `foqa` inutiles | `furryp check --fix` |
| Geler les violations existantes | `furryp check --add-foqa`, puis `ruff format` |
| Produire le rapport d'audit | `furryp check --report-html audit.html` |
| Voir la configuration réellement utilisée | `furryp check --show-settings` |

## 1. Installer

Il faut **Python 3.14** ou plus récent, et de préférence [uv](https://docs.astral.sh/uv/).

| Méthode | Commande | À choisir si… |
|---|---|---|
| Outil global (recommandé) | `uv tool install --editable <chemin-vers-furryp>` | Vous voulez la commande `furryp` partout. Elle suit les modifications du dépôt de furryp. |
| Sans rien installer | `uv run --project <chemin-vers-furryp> furryp check` | Vous voulez essayer une fois. Lancez-la depuis le projet à analyser. |
| Dépendance d'un projet | `uv add --dev <chemin-vers-furryp>`, puis `uv run furryp check` | Toute l'équipe du projet doit avoir la même version. |
| Sans uv | `python -m pip install <chemin-vers-furryp>` | uv n'est pas disponible. Sous Windows, `py -3.14 -m pip install …` si plusieurs Python coexistent. |

Les deux dernières méthodes installent une copie figée : réinstallez pour obtenir une nouvelle version de furryp.

**N'utilisez pas `uvx --from <chemin-vers-furryp> furryp`** : uv garde en cache la version construite, et la commande peut lancer un ancien furryp sans rien signaler, même avec `--refresh` ou `--reinstall`. Seul `--no-cache` y échappe.

Pour vérifier :

```bash
furryp --version
```

La commande affiche `furryp 1.0.2`. Si `furryp` n'est pas reconnue après `uv tool install`, lancez `uv tool update-shell`, puis rouvrez le terminal.

Dans la suite, `furryp` désigne la commande installée. Sans installation, écrivez `uv run --project <chemin-vers-furryp> furryp` à la place.

## 2. Démarrer sur un projet

**Placez-vous à la racine du projet analysé**, là où se trouve son `pyproject.toml`. C'est à partir de ce dossier que furryp cherche sa configuration. Si vous lancez furryp depuis un autre projet en lui passant un chemin, il appliquera la configuration de cet autre projet.

```bash
furryp check --statistics
furryp check
furryp rule FUR202
```

Sans argument, furryp analyse tous les fichiers `*.py` du dossier courant, récursivement, sauf les dossiers usuels (`.venv`, `venv`, `build`, `dist`, `__pycache__`…). Pour une liste de chemins, passez-les en arguments : `furryp check src/ tests/test_x.py`.

Seuls `--fix` et `--add-foqa` modifient vos fichiers source. `--report-html` écrit seulement le rapport.

## 3. Lire la sortie

```
demeter-chain [FUR403]: Attribute chain `order.customer.address.city.rate` is too deep (4 > 3)
 --> src\billing.py:5:12
  |
4 | def total(order):
5 |     return order.customer.address.city.rate * 2
  |            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
help: Long chains depend on the inner structure of other objects; consider asking the first object for what you need

unused-foqa [FUR001] [*]: Unused `foqa` directive (unused: `FUR101`)
 --> src\billing.py:8:21
  |
8 | def legacy(order):  # foqa:FUR101
  |                     ^^^^^^^^^^^^^
9 |     return order.id
  |
help: Remove unused `foqa` directive
  |
7 |
  - def legacy(order):  # foqa:FUR101
8 + def legacy(order):
9 |     return order.id
  |

Found 2 errors.
[*] 1 fixable with `--fix`.
```

- **Première ligne** : `nom-de-la-règle [CODE]: message`. Pour une règle de mesure, le message finit par `(valeur > seuil)`. `[*]` signale une correction automatique.
- **`-->`** : `fichier:ligne:colonne`, cliquable dans VS Code.
- **Extrait** : le code en cause, souligné, avec son contexte. Une violation qui vise tout le fichier n'a pas d'extrait.
- **`help:`** : toujours présent. Il résume le problème et vous laisse choisir la solution. Le détail est dans `furryp rule <CODE>`. Si une correction existe, son diff suit (`-` retiré, `+` ajouté).
- **Pied de page** : le total, puis le nombre de corrections disponibles.

Les messages d'erreur et les avertissements vont sur stderr, le reste sur stdout. La sortie est en anglais, sans couleur et en UTF-8 sur toutes les plateformes.

### Codes de sortie

| Code | Signification |
|---|---|
| 0 | Aucune violation, ou `--exit-zero`, ou `--add-foqa` terminé, ou `--diff` sans changement. |
| 1 | Au moins une violation, ou `--diff` qui proposerait un changement. Un chemin inexistant compte comme une violation (`FUR000`). |
| 2 | Erreur : option invalide, configuration invalide, règle inconnue, rapport impossible à écrire, erreur interne. Le code 2 l'emporte sur le code 1, même avec `--exit-zero`. |

## 4. Les règles

Une violation apparaît **strictement au-dessus** du seuil.

| Code | Nom | Ce qui est mesuré | Seuil | Niveau | `--fix` |
|---|---|---|---|---|---|
| FUR000 | `invalid-syntax` | Fichier illisible ou syntaxe invalide. Toujours actif. | — | fichier | non |
| FUR001 | `unused-foqa` | Directive `foqa` inutile, de règle non activée ou en double | — | ligne | **oui** |
| FUR101 | `function-too-long` | Lignes de code du corps d'une fonction, hors signature, décorateurs, commentaires, lignes vides et docstring | 26 | ligne | non |
| FUR102 | `file-too-long` | Lignes totales du fichier, tout compris | 1000 | fichier | non |
| FUR201 | `halstead-file` | Volume Halstead du fichier | 15000 | fichier | non |
| FUR202 | `halstead-function` | Volume Halstead d'une fonction, signature comprise | 1200 | ligne | non |
| FUR203 | `cognitive-complexity` | Complexité cognitive d'une fonction | 16 | ligne | non |
| FUR401 | `too-complex-class` | Somme des complexités des méthodes d'une classe. Classes de test et de dispatch non mesurées. | 80 | ligne | non |
| FUR402 | `layer-violation` | Import interdit par un contrat de couches. Inactive sans contrat (section 7.4). | — | ligne | non |
| FUR403 | `demeter-chain` | Profondeur d'une chaîne d'attributs : `a.b.c.d.e` vaut 4 | 3 | ligne | non |
| FUR404 | `too-many-instance-attributes` | Noms distincts affectés sur `self`. Classes de test et de données non mesurées. | 20 | ligne | non |

Le **niveau** décide de la forme de la directive `foqa` (section 8).

Les codes se groupent par famille : `FUR0` (erreurs et directives), `FUR1` (taille), `FUR2` (Halstead et complexité cognitive), `FUR4` (conception). `FUR3` n'existe pas.

Quand une même fonction déclenche plusieurs règles, c'est un seul problème : refactorez-la une fois, puis relancez.

Pour le détail d'une règle : `furryp rule FUR403` explique la mesure, ses raisons, les options avec vos valeurs effectives, comment bien corriger, ce qu'il ne faut pas faire, et donne un exemple.

## 5. La commande `furryp check`

```bash
furryp check [CHEMINS] [OPTIONS]
```

| Option | Effet |
|---|---|
| `--config CHEMIN` | Utilise ce fichier de configuration. La racine du projet devient son dossier. |
| `--select RÈGLES` | Remplace la sélection de la configuration. |
| `--extend-select RÈGLES` | Ajoute à la sélection. |
| `--ignore RÈGLES` | Retire de la sélection. L'emporte toujours sur `--select`. |
| `--statistics` | Affiche le compte par règle au lieu du détail. |
| `--diff` | Affiche les corrections sous forme de diff, sans rien écrire. |
| `--fix` | Applique les corrections et écrit les fichiers. Avec `--diff`, c'est `--diff` qui s'applique. |
| `--add-foqa` | Ajoute une directive `foqa` sur chaque violation restante, écrit les fichiers et quitte. |
| `--report-html CHEMIN` | Écrit le rapport HTML. Rien sur stdout. Les dossiers manquants sont créés. |
| `--show-settings` | Affiche la configuration effective et quitte, sans analyser. |
| `--exit-zero` | Sort en 0 même s'il reste des violations. Une erreur sort toujours en 2. |

**`RÈGLES`** est une liste séparée par des virgules, de codes, de préfixes ou de noms. L'option peut être répétée. Ces écritures sont équivalentes :

```bash
furryp check --select FUR1,FUR403
furryp check --select FUR1 --select demeter-chain
```

Une option s'écrit en entier : `--stat` est refusé. Une règle inconnue, un élément vide ou entouré de blancs (`--select ""`, `--select "FUR1, FUR2"`) donne le code 2.

**Combinaisons refusées** (code 2) :

- `--add-foqa` avec `--fix`, `--diff`, `--statistics`, `--show-settings` ou `--report-html` ;
- `--report-html` avec `--fix`, `--diff`, `--statistics` ou `--show-settings` ;
- `--statistics` avec `--fix` ou `--diff` ;
- `--show-settings` avec `--fix`, `--diff` ou `--statistics`.

## 6. La commande `furryp rule`

```bash
furryp rule FUR203
furryp rule cognitive-complexity
furryp rule --all
```

Elle affiche la fiche d'une règle ou de toutes, en Markdown. Elle lit la configuration comme `check`, et accepte aussi `--config`.

## 7. La configuration

### 7.1 Où la mettre

Créez **`furryp.json` à côté du `pyproject.toml`** de votre projet. furryp remonte depuis le dossier courant jusqu'au premier `pyproject.toml` : ce dossier est la racine du projet, et tous les chemins de la configuration lui sont relatifs. Sans `pyproject.toml`, la racine est le dossier courant.

- Sans `furryp.json`, les valeurs par défaut s'appliquent.
- Priorité : ligne de commande, puis `furryp.json`, puis valeurs par défaut.
- Ne mettez dans le fichier que ce que vous changez. Sous `rules`, seules les clés écrites changent.
- JSON n'a pas de commentaires : donnez des noms parlants à vos contrats.
- Une clé inconnue ou une valeur invalide arrête furryp avec le code 2 et une suggestion : `error: furryp.json: rules.function-too-long.max_lines: unknown key (did you mean "max-lines"?)`.

`furryp check --show-settings` affiche la configuration effective, valeurs par défaut comprises. Sa partie JSON peut servir de point de départ.

### 7.2 Réglages généraux

| Clé | Défaut | Rôle |
|---|---|---|
| `include` | `["**/*.py"]` | Fichiers à analyser. |
| `exclude` | dossiers usuels (`.git`, `.venv`, `venv`, `env`, `__pycache__`, `build`, `dist`, `node_modules`, caches…) | Le remplacer retire aussi ces valeurs. |
| `extend-exclude` | `[]` | Ajoute à `exclude`, sans le remplacer. C'est ce qu'il faut en général. |
| `select` | `["FUR"]` | Règles actives : codes, préfixes ou noms. `FUR` = toutes. |
| `extend-select` | `[]` | Ajoute à la sélection. |
| `ignore` | `[]` | Retire de la sélection. L'emporte toujours. |
| `per-file-ignores` | `{}` | Règles retirées pour certains fichiers : `{"tests/**": ["FUR101"]}`. |
| `rules` | voir 7.3 | Options par règle, sous le **nom** de la règle. |
| `report` | voir 7.5 | Options du rapport. |

**Motifs de chemin** : un motif **sans `/`** vise un nom de dossier ou de fichier à n'importe quel niveau (`migrations`, `*.egg-info`). Un motif **avec `/`** vise un chemin relatif à la racine, `**` accepté (`src/generated`, `src/**/*.py`). Les exclusions valent aussi pour un fichier passé explicitement en argument : il n'est alors pas analysé.

`FUR000` reste actif quoi qu'on écrive dans `ignore`.

### 7.3 Réglages par règle

| Règle | Option | Défaut | Rôle |
|---|---|---|---|
| `function-too-long` | `max-lines` | 26 | Lignes de code au maximum. |
| `file-too-long` | `max-lines` | 1000 | Lignes au maximum. |
| `halstead-file` | `metric` | `"volume"` | Mesure utilisée : `volume`, `difficulty`, `effort` ou `bugs`. |
| `halstead-file` | `max` | 15000 | Maximum de cette mesure. |
| `halstead-function` | `metric` | `"volume"` | Comme ci-dessus. |
| `halstead-function` | `max` | 1200 | Maximum de cette mesure. |
| `cognitive-complexity` | `max` | 16 | Complexité au maximum. |
| `too-complex-class` | `max-class-complexity` | 80 | Somme des complexités au maximum. |
| `too-many-instance-attributes` | `max-instance-attributes` | 20 | Attributs au maximum. |
| `demeter-chain` | `max-depth` | 3 | Profondeur au maximum. |
| `demeter-chain` | `ignore-roots` | `["self", "cls"]` | Racines dont le premier attribut ne compte pas : `self.repo.session.query()` vaut 2. |
| `demeter-chain` | `ignore-imported-modules` | `true` | Ignore une chaîne qui part d'un `import x`, comme `os.path.join`. |
| `demeter-chain` | `count-calls` | `false` | Si `true`, une chaîne continue à travers un appel : `a.b().c.d` vaut 3 au lieu de 2. |
| `layer-violation` | `source-roots` | `["."]` | Racines du code, pour nommer les modules (7.4). |
| `layer-violation` | `include-type-checking` | `true` | Compte aussi les imports d'un bloc `if TYPE_CHECKING:`. |
| `layer-violation` | `contracts` | `[]` | Contrats de couches (7.4). |

Les seuils sont à titre indicatif. Ajustez-les à votre projet.

### 7.4 Contrats de couches

`layer-violation` vérifie que les imports respectent votre architecture. Elle ne fait rien tant que vous n'écrivez pas de contrat.

**Commencez par `source-roots`.** Le nom d'un module est le chemin de son fichier relatif à la racine qui le contient. Avec `"source-roots": ["src"]`, `src/app/view.py` s'appelle `app.view`. Choisissez la racine qui donne les noms écrits dans vos imports : si le code écrit `from models.user import User`, le dossier qui contient `models/` est la racine. Un fichier hors des racines n'est pas contrôlé.

Trois types de contrats existent :

| Type | Ce qu'il impose | Clés |
|---|---|---|
| `forbidden` | Aucun module de `source` n'importe un module de `forbidden`. | `name`, `source`, `forbidden` |
| `layers` | Du plus haut au plus bas, un module n'importe jamais une couche plus haute. Une sous-liste forme un même niveau. Les modules hors couches sont libres. | `name`, `layers` |
| `independence` | Aucun de ces modules n'importe un autre. | `name`, `modules` |

**Motifs de module** : `a.b` vise `a.b` et tout ce qui est dessous, mais pas `a.bc`. `*` remplace exactement un segment : `app.*.view` vise `app.billing.view`, et `independence` sur `app.*` sépare `app.billing` de `app.shipping`. Un motif peut viser une bibliothèque : `"forbidden": ["tkinter"]`.

**`layers` n'est pas strict** : un module peut importer toutes les couches au-dessous de la sienne. Pour interdire une dépendance précise, écrivez un `forbidden`.

Tous les imports comptent : absolus, relatifs, dans une fonction ou dans un bloc `try`. Une dépendance indirecte, un nom réexporté par un paquet ou `importlib` ne sont pas suivis.

Exemple pour une architecture MVP. La vue ne connaît ni le modèle ni le présentateur, et le domaine ne connaît pas l'interface :

```json
{
  "rules": {
    "layer-violation": {
      "source-roots": ["src"],
      "contracts": [
        {
          "type": "layers",
          "name": "one-way",
          "layers": ["app.presenters", ["app.views", "app.services"], "app.repositories", "app.models", "app.shared"]
        },
        {
          "type": "forbidden",
          "name": "view-imports",
          "source": ["app.views"],
          "forbidden": ["app.models", "app.services", "app.repositories"]
        },
        {
          "type": "forbidden",
          "name": "service-imports",
          "source": ["app.services"],
          "forbidden": ["app.views", "tkinter"]
        },
        {
          "type": "independence",
          "name": "separate-features",
          "modules": ["app.services.billing", "app.services.shipping"]
        }
      ]
    }
  }
}
```

Le message cite le contrat : ``Import of `app.models.user` breaks contract `view-imports`: `app.views` must not import `app.models` ``.

Si deux contrats visent le même import, il est signalé deux fois : évitez de répéter dans un `forbidden` ce que `layers` interdit déjà.

### 7.5 Le rapport

| Clé sous `report` | Défaut | Rôle |
|---|---|---|
| `top-n` | 10 | Nombre de pires fichiers par catégorie. |
| `title` | `"furryp — audit"` | Titre du rapport. |
| `rating-thresholds` | `[0.20, 0.40, 0.60, 0.80]` | Limites des notes A, B, C et D (section 11). |

### 7.6 Exemple complet

```json
{
  "include": ["src/**/*.py"],
  "extend-exclude": ["src/generated"],
  "ignore": ["FUR201"],
  "per-file-ignores": { "src/legacy/**": ["FUR101", "FUR403"] },
  "rules": {
    "function-too-long": { "max-lines": 30 },
    "cognitive-complexity": { "max": 12 },
    "demeter-chain": { "ignore-roots": ["self", "cls", "ctx"] },
    "layer-violation": {
      "source-roots": ["src"],
      "contracts": [
        { "type": "forbidden", "name": "domain-without-infra", "source": ["app.domain"], "forbidden": ["app.infra"] }
      ]
    }
  },
  "report": { "title": "Mon projet — audit", "top-n": 20 }
}
```

## 8. Ignorer une violation : `foqa`

```python
def legacy_entry_point(args):  # foqa:FUR101
    ...


result = order.customer.address.city.upper()  # foqa:FUR403
```

| Forme | Portée |
|---|---|
| `# foqa:FUR101,FUR403` | Ces règles, sur toute l'instruction du commentaire, même répartie sur plusieurs lignes. C'est ainsi qu'on vise les règles de niveau **ligne**. |
| `# furryp: foqa:FUR102,FUR201` | Ces règles, sur tout le fichier. Le commentaire doit être seul sur sa ligne, n'importe où dans le fichier. C'est ainsi qu'on vise les règles de niveau **fichier**. |
| `# foqa` | Toutes les règles sur l'instruction. À éviter, c'est trop large. |
| `# furryp: foqa` | Toutes les règles sur tout le fichier. À éviter aussi : `FUR001` ne regarde plus ce fichier, et cette directive n'est jamais signalée, même quand elle ne sert plus. |

- Utilisez les codes. Les noms de règles sont acceptés (`# foqa:demeter-chain`), mais plus longs.
- La directive peut suivre un autre commentaire et cohabiter avec `# noqa`, dans les deux ordres.
- Du texte peut suivre : `# foqa:FUR101 code hérité`.
- `FUR000` et `FUR001` ne peuvent pas être ignorés par `foqa`.
- Les violations ignorées restent comptées dans le rapport HTML, colonne « Suppressed ».
- Une directive devenue inutile est signalée par `FUR001`, et `--fix` la retire.
- Si une directive de fichier et une directive de ligne visent la même violation, celle de fichier la supprime, et `FUR001` signale celle de ligne.

**Comme `# noqa` dans ruff, la forme compte** :

| Écriture | Effet |
|---|---|
| `# foqa FUR101` (sans deux-points) | Directive globale : elle ignore **tout**. |
| `# foqa:FUR999` (code inconnu) | Ne supprime rien, sans avertissement. `furryp rule --all` liste les codes. |
| `# foqa.  # foqa:FUR403` | Seul le **premier** mot-clé d'un commentaire compte. Il est ici invalide : rien n'est supprimé. |
| `# foqa.`, `# foqa:`, `# foqa:FUR101;` | Invalide : aucun effet, et un avertissement. |
| `x = 1  # furryp: foqa` | Directive de fichier après du code : aucun effet, et un avertissement. |

Les avertissements vont sur stderr et ne changent pas le code de sortie :

```
warning: Invalid `# foqa` directive on w.py:1: expected `:` followed by a comma-separated list of codes (e.g., `# foqa:FUR101,FUR403`).
warning: Missing or joined rule code(s) at w.py:4: expected rule code between commas
```

`--fix` et `--diff` les répètent à chaque passe, tant que la directive est là.

## 9. Les corrections automatiques

Seule `FUR001` a une correction : elle réécrit une directive avec les codes qui servent encore, ou la retire si elle n'en a plus. **Aucune correction ne déplace ni ne réécrit votre code.**

```bash
furryp check --diff
furryp check --fix
```

Le fichier garde son encodage, son BOM et ses fins de ligne. Lancez `ruff format` après `--fix` : comme après `RUF100`, il peut rejoindre une ligne que la directive avait fait replier.

`--fix` retire aussi les codes des règles que vous avez désactivées : avec `--ignore FUR4 --fix`, tous les `# foqa:FUR4xx` disparaissent. Lancez-le donc avec votre sélection complète.

## 10. Adopter furryp sur un projet existant

1. **Mesurer** : `furryp check --statistics`.
2. **Choisir** : écrivez `furryp.json`, avec vos seuils et vos contrats de couches.
3. **Formater** : si le projet n'est pas encore formaté, lancez `ruff format` d'abord. Le formatage change certaines mesures, et une directive posée trop tôt peut devenir fausse.
4. **Geler la dette** : `furryp check --add-foqa`, puis `ruff format`.
5. **Vérifier** : `furryp check` doit afficher `All checks passed!`. Sinon, relancez les étapes 4 et 5. Committez ce changement à part.
6. **Suivre** : `furryp check --report-html audit.html` à intervalles réguliers. La colonne « Suppressed » montre la dette gelée.
7. **Résorber** : corrigez au fil des modifications. Quand une violation gelée disparaît, `FUR001` le signale et `--fix` retire la directive.

Désormais, seules les nouvelles violations apparaissent.

**Ce que fait `--add-foqa`** : il ajoute `  # foqa:CODES` en fin d'instruction pour une règle de niveau ligne, et une seule ligne `# furryp: foqa:CODES` en tête de fichier pour une règle de niveau fichier. Il complète une directive déjà présente et respecte un `# foqa` global. Si la dernière ligne qu'il modifie n'a pas de fin de ligne, il lui en ajoute une. Il ne touche pas à un fichier en `FUR000`, et n'ajoute rien à une seconde exécution, sauf après une directive invalide, comme `--add-noqa` de ruff : corrigez-la d'abord.

## 11. Le rapport HTML

```bash
furryp check --report-html audit.html
```

C'est un seul fichier, sans script ni ressource externe : il s'ouvre hors ligne et s'imprime. Il contient :

- une **synthèse** : fichiers, lignes, fonctions, classes, violations, densité pour 1000 lignes de code, violations ignorées, directives inutiles, corrections disponibles, et une note par catégorie ;
- une **section par catégorie** (Size, Complexity, Halstead, Design) : mesures, violations par règle et pires fichiers. Seuls les fichiers en violation y figurent, du pire au meilleur, et à égalité le plus long d'abord ;
- les **fichiers non analysables**, annoncés par un bandeau en haut de page ;
- la **configuration effective**, en annexe.

**La note** dépend de la part de fichiers ayant au moins une violation dans la catégorie :

| Note | A | B | C | D | E |
|---|---|---|---|---|---|
| Part des fichiers | ≤ 20 % | ≤ 40 % | ≤ 60 % | ≤ 80 % | au-delà |

**A ne veut donc pas dire « aucune violation ».** Un `*` remplace la lettre si aucune règle de la catégorie n'est sélectionnée, ou si aucun fichier n'a été analysé. Un `–` remplace un chiffre qui dépend d'une règle qui n'a pas tourné.

Les mesures sont calculées pour tous les fichiers, même si leur règle est désactivée. Les violations respectent la sélection et les `foqa`. Le code de sortie reste celui de `check`.

Ces mesures suivent les définitions de furryp : elles ne sont pas directement comparables à celles de SonarQube ou de radon.

## 12. L'intégration continue

```bash
furryp check
furryp check --report-html furryp-report.html --exit-zero
```

La première commande fait échouer le job s'il reste une violation. La seconde produit un rapport à publier sans le faire échouer. La sortie est la même sous Windows et sous Linux.

- Un chemin mal saisi produit `FUR000` et le code 1, pas un faux succès.
- Un dossier sans aucun fichier Python donne un avertissement et le code 0, comme ruff : vérifiez les chemins de votre pipeline.

Hook [pre-commit](https://pre-commit.com) local, avec furryp installé par `uv tool install`. Les exclusions de `furryp.json` s'appliquent aux fichiers que pre-commit passe en argument.

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

## 13. Cohabiter avec ruff

furryp tourne à côté de ruff, et lui laisse tout ce que ruff contrôle déjà.

- **À ruff** : complexité de McCabe d'une fonction (`C901`), espaces en fin de ligne (`W291`, `W293`), lignes vides (`ruff format`), tri des imports (`I001`).
- **Style** : furryp ne signale jamais le style produit par `ruff format`, mais un repli peut faire dépasser un seuil de mesure.
- **Directives** : `# noqa` et `# foqa` cohabitent sur une même ligne.
- **Repli** : quand `ruff format` replie une instruction et déplace un `# foqa` sur sa dernière ligne, la directive reste valide.
- **Longueur de ligne** : ruff exclut `# noqa` du calcul de `E501`, mais pas `# foqa`. Après `--add-foqa`, lancez `ruff format`. Seule une ligne impossible à replier peut garder un `E501`.
- **Une limite** : une instruction composée sur une ligne, comme `def f(x): return x  # foqa:FUR202`, devient deux lignes. Le commentaire suit alors `return`, et la directive n'agit plus. `# noqa` a la même limite. Formater avant `--add-foqa` l'évite.
- **Recouvrement** : `function-too-long` (lignes de code) et `PLR0915` de ruff (nombre d'instructions) mesurent la taille différemment. Gardez les deux, ou choisissez-en une.

Pour travailler avec un assistant de code, des consignes à copier se trouvent dans le `README.md`, section 11.

## 14. Dépannage

| Symptôme | Cause et solution |
|---|---|
| `unknown key (did you mean "max-lines"?)` | Les clés s'écrivent avec des tirets. |
| `unknown rule or prefix "FUR3"` | Cette famille n'existe pas : voir la section 4. |
| Beaucoup plus de violations que prévu, ou des règles inconnues de ce guide | Ancienne version en cache : n'utilisez pas `uvx --from` (section 1). Vérifiez avec `furryp rule --all`. |
| Un `# foqa` semble sans effet | Code mal saisi, forme invalide, ou directive plus tôt dans le commentaire. Une forme invalide donne un avertissement sur stderr ; un code inconnu, non. |
| `unused-foqa [FUR001]` après un refactoring | La violation gelée a disparu : `furryp check --fix`. |
| `unused-foqa [FUR001]` … `(non-enabled: …)` | La directive cite une règle désactivée pour ce fichier. Réactivez la règle ou retirez le code. |
| `layer-violation` ne signale rien | Sans contrat, la règle ne fait rien. Sinon, vérifiez `source-roots` : les noms de modules doivent être ceux de vos imports. |
| `invalid-syntax [FUR000]` sur un fichier | Il ne se parse pas en Python 3.14 : seule la longueur y est vérifiée. |
| `Failed to read file` | Le chemin n'existe pas ou n'est pas lisible. |
| `Failed to decode file` | Enregistrez le fichier en UTF-8, ou ajoutez une ligne `# -*- coding: … -*-`. |
| `warning: No Python files found` ou un fichier attendu n'est pas analysé | Il est exclu par `include`, `exclude` ou `extend-exclude`, même passé en argument. `furryp check --show-settings` montre la configuration effective. |
| Une configuration inattendue s'applique | Vous n'êtes pas à la racine du bon projet. La première ligne de `--show-settings` indique la racine, la deuxième le fichier lu. |
| Caractères illisibles dans une console Windows | furryp écrit toujours en UTF-8. Utilisez le terminal de VS Code ou Windows Terminal. |
| Rien ne s'affiche avec `--report-html` | C'est voulu : seul le fichier est écrit. Le code de sortie dit s'il y a des violations. |
