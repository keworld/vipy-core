"""Macro loading and expansion helpers for the Vietnamese input method."""
import csv
import logging
import os


logger = logging.getLogger(__name__)


def load_macros(path: str, macros: dict[str, str]) -> int:
    """Load macros from *path* without replacing configured macros."""
    configured_path = path
    if not os.path.isabs(configured_path):
        here = os.path.dirname(__file__)
        candidates = (
            os.path.join(here, configured_path),
            os.path.join(here, "..", "data", configured_path),
            os.path.expanduser(
                os.path.join(
                    "~/.config/fcitx5-vipy/data",
                    os.path.basename(configured_path),
                )
            ),
        )
        configured_path = next(
            (candidate for candidate in candidates
             if os.path.isfile(candidate)),
            candidates[0],
        )

    loaded = 0
    try:
        with open(configured_path, "r", encoding="utf-8") as macro_file:
            for line_number, row in enumerate(csv.reader(macro_file), 1):
                line = ",".join(row).rstrip("\n\r")
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if len(row) >= 2:
                    trigger, replacement = row[0], ",".join(row[1:])
                elif "\t" in line:
                    trigger, replacement = line.split("\t", 1)
                elif "=>" in line:
                    trigger, replacement = line.split("=>", 1)
                elif "=" in line:
                    trigger, replacement = line.split("=", 1)
                else:
                    logger.warning(
                        "Bỏ qua macro không hợp lệ tại %s:%d",
                        configured_path,
                        line_number,
                    )
                    continue

                trigger = trigger.strip()
                replacement = replacement.strip()
                if not trigger:
                    logger.warning(
                        "Bỏ qua macro rỗng tại %s:%d",
                        configured_path,
                        line_number,
                    )
                    continue
                if trigger not in macros:
                    macros[trigger] = replacement
                    loaded += 1
    except OSError as exc:
        logger.warning("Không thể tải macro từ %s: %s", configured_path, exc)
    return loaded


def apply_macro(text: str, macros: dict[str, str], enabled: bool = True) -> str:
    """Expand one macro using the original case-sensitive/case-insensitive order."""
    if not enabled or not text:
        return text
    return macros.get(text, macros.get(text.lower(), text))
