"""Rendering of ``--show-settings`` (SPEC §5.5).

The JSON part lists every key, defaults included, and can be saved as is as a ``furryp.json`` file.
"""

from furryp.config.loader import Configuration
from furryp.config.schema import settings_json

NO_CONFIG_FILE = "(none, defaults)"


def render_settings(configuration: Configuration) -> str:
    """Return the text printed by ``furryp check --show-settings``."""
    config_file = configuration.config_file
    lines = (
        f"Project root: {configuration.project_root}",
        f"Config file: {NO_CONFIG_FILE if config_file is None else config_file}",
        settings_json(configuration.settings),
    )
    return "\n".join(lines)
