# furryp — instructions permanentes pour Claude Code

Linter Python local inspiré de ruff. Python 3.14, bibliothèque standard uniquement.
La spécification normative est `docs/SPEC.md` : lis les sections utiles à la tâche (inutile de tout relire à chaque fois).

## Règles d'or

- `docs/SPEC.md` fait foi. En cas d'ambiguïté, ou si elle diverge de ruff : **vérifie d'abord le comportement réel de ruff** (`uv run ruff`, version notée), qui a la priorité, sauf pour les écarts assumés du §2.3 ; si ruff n'a pas d'équivalent, **pose la question** au lieu d'inventer.
- **Le but reste une bonne qualimétrie** : aligné sur ruff, furryp doit rester productif. Avant de retenir un choix, mesure son effet réel (par exemple sur la bibliothèque standard) ; si un choix, même validé ou venant de ruff, nuit à la qualité des mesures, signale-le chiffres à l'appui au lieu de l'appliquer sans rien dire.
- Trace toujours l'arbitrage et l'écart, y compris un écart avec ruff que j'ai décidé : le signalement dans ton résumé, et une proposition de report dans `docs/SPEC.md` (la section concernée, et le §2.3 pour un écart avec ruff).
- **Aucune dépendance tierce**, ni à l'exécution ni pour les tests (`unittest` uniquement). N'installe rien.
- Ne modifie jamais `docs/SPEC.md`, `AGENTS.md`, `CLAUDE.md` ni `README.md` (guide utilisateur, décrit le comportement attendu) sans demande explicite.
- Pour faire passer le dogfooding ou basedpyright, ne relâche **jamais** un seuil et n'ajoute **jamais** de `# foqa`, de `per-file-ignores`, de `# type: ignore` ni de `# pyright: ignore` sans mon accord explicite : corrige le code.

## Conventions de code

Chaque module de `furryp/` respecte les règles qu'il implémente :

1. Une docstring de module.
2. Tous les imports en tête de module, juste après la docstring. Aucun import dans une fonction.
3. Les constantes sont en MAJUSCULES. Une valeur qui dépend d'une fonction ou d'une classe du même module (table de correspondance, instance par défaut) se place juste après ce dont elle dépend.
4. `if __name__ == "__main__":` en dernier.
5. La mise en forme relève de `ruff format` : lignes vides, fin de fichier, espaces en fin de ligne.
6. Fonctions ≤ 26 lignes de code, complexité cognitive ≤ 16. Fichiers ≤ 1000 lignes (vise moins de 600).
7. Chaînes d'attributs de profondeur 3 au plus (`node.value.func` oui, `node.value.func.attr.x` non) : ajoute des accesseurs dans `furryp/core/ast_utils.py`.
8. Classes : complexité ≤ 80, attributs d'instance ≤ 20. Objets valeur en `@dataclass(frozen=True, slots=True)`.
9. Couches, du haut vers le bas : `cli` → (`output` | `report` | `fix`) → `lint` → `config` → `rules` → `metrics` → `core`. Jamais d'import vers une couche plus haute.
10. HTML et CSS uniquement dans `furryp/report/templates/`, jamais dans du code Python.
11. Python 3.14 : `ast.Constant` uniquement (`ast.Num` / `ast.Str` n'existent plus) ; `col_offset` est en octets UTF-8, à convertir via `furryp/core/positions.py` ; pas de `from __future__ import annotations`.
12. Annotations de type complètes. Docstrings et tout texte visible par l'utilisateur en anglais : messages, aides, fiches `furryp rule`, rapport HTML.
13. **Entrées/sorties** (SPEC §3.1) : jamais d'encodage implicite. `encoding=` explicite sur tout `open`, `read_text`, `write_text` (y compris `importlib.resources`), `newline=` explicite sur toute écriture en mode texte. Sources lues en octets + `tokenize.detect_encoding`, réécrites avec `write_bytes`. Ne compte jamais sur `PYTHONUTF8` : sous Windows, Python 3.14 lit en cp1252 par défaut.
14. **Réécriture** (SPEC §7.1) : éditions textuelles ciblées uniquement. Jamais `ast.unparse`, `tokenize.untokenize` ni `libcst` pour produire du code.
15. Chaque règle livrée a une aide (`help`) conforme au contrat du §11.0 de `docs/SPEC.md` et sa fiche `furryp/rules/docs/<code>.md` (§4.6). Une règle sans aide conforme ni fiche n'est pas terminée.

## Commandes

- Environnement : **uv**. `uv sync` après toute modification de `pyproject.toml`. Toutes les commandes passent par `uv run`.
- Tests : `uv run python -m unittest discover -s tests -t .`
- Dogfooding : `uv run furryp check furryp`
- Typage : `uv run basedpyright`
- Fiche d'une règle : `uv run furryp rule FUR101`
- **Interdit** : `uv add`, `uv pip install`, `pip install`, `uv init` (furryp n'a aucune dépendance d'exécution, ruff et basedpyright sont ses seules dépendances de développement, et `uv init` écraserait la structure). ruff et basedpyright se lancent avec `uv run` (ex. `uv run ruff format`, `uv run basedpyright`) ; un autre outil externe ponctuel passe par `uvx`.
- Le code et les tests doivent fonctionner à l'identique sous Windows et Linux : `pathlib` pour les chemins, `subprocess` avec `encoding="utf-8"` dans les tests.

## Fin de tâche (obligatoire)

1. Tests verts, dogfooding vert et `uv run basedpyright` sans erreur ; aides et fiches des règles livrées présentes.
2. Un résumé de 10 lignes maximum, puis arrête-toi.
