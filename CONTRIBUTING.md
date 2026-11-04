# Contribuer à furryp

## Mise en place

- **uv** : installez [uv](https://docs.astral.sh/uv/), puis lancez `uv sync` à la racine. Toutes les commandes passent ensuite par `uv run`, par exemple `uv run furryp rule FUR101`. L'usage de l'outil est décrit dans [USAGE.md](USAGE.md).
- **ruff** et **basedpyright** : seules dépendances du projet, en développement uniquement. `uv sync` les installe aux versions fixées dans `uv.lock` ; ils se lancent avec `uv run ruff` et `uv run basedpyright`, et se configurent dans `pyproject.toml`.
- **VS Code** : installez les extensions Python (`ms-python.python`) et Ruff (`charliermarsh.ruff`), choisissez l'interpréteur `.venv`, puis réglez Ruff comme formateur Python avec `editor.formatOnSave` activé.

## Vérification avant commit

```bash
uv run ruff format
uv run ruff check
uv run basedpyright
uv run furryp check furryp
uv run python -m unittest discover -s tests -t .
```

Aucun hook ni CI ne lance ces commandes à votre place. Si l'une échoue, corrigez le code : ne relâchez aucun seuil et n'ajoutez ni `# foqa`, ni `per-file-ignores`, ni `# type: ignore`, ni `# pyright: ignore` sans l'accord du mainteneur.

## Conventions

- [docs/SPEC.md](docs/SPEC.md) fait foi. Si elle est ambiguë ou diverge de ruff, le comportement réel de ruff prime.
- [AGENTS.md](AGENTS.md) détaille les règles de code : couches, limites de taille, encodages explicites, tests en `unittest`, texte visible par l'utilisateur en anglais.
- Une règle n'est terminée qu'avec son aide (`help`, SPEC §11.0) et sa fiche `furryp/rules/docs/<code>.md` (SPEC §4.6).

## Publier une version

1. Lancez `uv version --bump patch` (ou `minor`, `major`), qui met à jour `pyproject.toml` et `uv.lock`, puis reportez le numéro dans `__version__` de `furryp/__init__.py`.
2. Relancez les vérifications ci-dessus, committez sur `main`, puis lancez `git tag vX.Y.Z` et `git push origin main vX.Y.Z`.
3. Il n'y a pas de publication PyPI : furryp s'installe depuis le dépôt. `uv build` produit au besoin le wheel et le sdist dans `dist/`.
