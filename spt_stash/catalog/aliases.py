#!/usr/bin/env python3
"""SPT Stash — catalog alias table, deduplicated."""

# key: lowercase, alphanumeric-only token derived from folder/dll name
# value: lowercase hyphenated slug that appears in the mod's sp-mod.com link/title
ALIASES = {
    "tyfonuifixes": "ui-fixes",
    "uifixes": "ui-fixes",
    "drakiaxyzquesttracker": "quest-tracker",
    "deminvincibility": "invincibility",
    "handsarenotbusy": "hands-are-not-busy",
    "borkelrnvg": "borkels-realistic-night-vision-goggles",
    "borkelrnvgserver": "borkels-realistic-night-vision-goggles",
    "amandsgraphics": "amandss-graphics",
    "amandssense": "amands-sense",
    "sain": "sain-solarints-ai-modifications",
    "solarintsainservermod": "sain-solarints-ai-modifications",
    "boxesatref": "boxes-at-ref",
    "svm": "server-value-modifier",
    "tarkinladders": "climbable-ladders",
    "tarkinhideoutuirevamp": "tarkin",
    "rairaihiddencaches": "rais-hidden-caches",
    "wttclientcommonlib": "wtt-commonlib",
    "wttservercommonlib": "wtt-commonlib",
    "moxopixelmenuoverhaul": "wtt-menu-overhaul",
    "drakiaxyzwaypoints": "waypoints-expanded-navmesh",
    "lacypvetweaks": "lacys-pve-tweaks",
    "acidphantasmbepinexconfigurationmanager": "acids-scalable-bepinex-panel",
    "bepinexconfigurationmanager": "acids-scalable-bepinex-panel",
    "acidphantasmarmbandsforall": "armbands-for-all",
    "wttcontentbackport": "wtt-content-backport",
    "wttcontentbackportclient": "wtt-content-backport",
    "randomizzatoremorecases": "more-cases-updated",
}
