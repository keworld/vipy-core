"""
VietnameseEngine — State Orchestrator Fcitx5 (giao tiếp qua C++ wrapper)
và cho adapter (InputManager).

Hợp đồng API:
  - process_key_event(keysym, mods, is_release) -> dict:
      {
        "consumed": bool,   # True = nuốt phím, False = cho app tự xử lý
        "commit":   str,    # text cần commit ("" nếu không commit)
        "preedit":  str,    # text đang gõ dở
        "cursor":   int,    # vị trí cursor trong preedit (= len(preedit))
      }
  - get_preedit() -> (text, cursor)
  - activate() / deactivate() / reset()
  - set_config(key, value) / get_config(key) / save()
"""
import csv
import logging
import os

from .vietnamese_phonology import VietnamesePhonology
from .input_schema import TelexSchema, VNISchema, Action
from .syllable_dict import SyllableDict

# ---------------------------------------------------------------------------
# KeySym constants (X11/FcitxKeySym)
# ---------------------------------------------------------------------------
KEY_BACKSPACE = 0xFF08
KEY_RETURN    = 0xFF0D
KEY_ESCAPE    = 0xFF1B
KEY_TAB       = 0xFF09
KEY_SPACE     = 0x0020

NAVIGATION_KEYS = frozenset({
    0xFF51,  # Left
    0xFF52,  # Up
    0xFF53,  # Right
    0xFF54,  # Down
    0xFF50,  # Home
    0xFF57,  # End
    0xFF55,  # Prior (PageUp)
    0xFF56,  # Next (PageDown)
    0xFFFF,  # Delete
})

# Modifier bit — phải khớp fcitx5 KeyState (C++ phía wrapper tự map).
MOD_SHIFT = 1 << 0
MOD_CTRL  = 1 << 1
MOD_ALT   = 1 << 2

HOTKEY_MASK = MOD_CTRL | MOD_ALT

logger = logging.getLogger(__name__)


def _keysym_to_char(keysym: int, mods: int) -> str:
    """Dịch keysym chữ/số thành ký tự, tôn trọng Shift."""
    if keysym == KEY_SPACE:
        return " "
    if 0x61 <= keysym <= 0x7A:                       # a-z
        ch = chr(keysym)
        return ch.upper() if (mods & MOD_SHIFT) else ch
    if 0x30 <= keysym <= 0x39:                       # 0-9
        return chr(keysym)
    return ""


class VietnameseInputMethod:
    def __init__(self, config: dict = None):
        self._phon = VietnamesePhonology()
        self._config = {
            "input_method": "telex",   # "telex" | "vni"
            "enable_lone_w": True,
            "enable_spell_check": True,
            "enable_macro": True,
            "enable_auto_decompose": True,
            "macros": {},
            "macro_file": "dict/vietnamese.macro",
            "append_commit_char": True,
        }
        if config:
            self._config.update(config)
        self._schema = None
        self._dict = SyllableDict.get_instance()
        self._surrounding_text = ""
        self._surrounding_cursor_pos = 0
        self._load_schema(self._config["input_method"])
        if self._config["enable_macro"]:
            self.load_macro()
        self.reset()

    # ------------------------------------------------------------------
    # Vòng đời (mirrors InputMethodEngineV3)
    # ------------------------------------------------------------------
    def activate(self) -> None:
        pass

    def deactivate(self) -> str:
        """Rời khỏi IME: trả về buffer dở để C++ commit, rồi tự reset."""
        pending = self.get_commit_text()[0]
        self.reset()
        return pending

    def reset(self) -> None:
        """Reset khi đổi focus/context: VỨT buffer, KHÔNG commit."""
        self._base = ""
        self._literal = ""
        self._preedit = ""
        self._raw_text = ""
        self._lone_w_pending = False

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------
    def _flush(self, consumed: bool = False) -> dict:
        """Commit buffer hiện tại (nếu có) và trả result; buffer bị reset."""
        if self._preedit:
            buf = self.get_commit_text()[0]
            self.reset()
            return self._result(consumed=consumed, commit=buf)
        return self._result(consumed=consumed)

    def process_key(self, keysym: int, mods: int, is_release: bool) -> dict:
        if is_release:
            return self._result(consumed=False)

        # Hotkey Ctrl/Alt: flush buffer (nếu có) rồi thả phím cho app.
        if mods & HOTKEY_MASK:
            return self._flush()

        # Phím điều hướng: flush buffer, KHÔNG nuốt phím.
        if keysym in NAVIGATION_KEYS:
            return self._flush()

        if keysym == KEY_TAB:
            return self._flush()

        if keysym == KEY_ESCAPE:
            # Hủy preedit (Unikey behavior).
            if self._preedit:
                self.reset()
                return self._result(consumed=True)
            return self._result(consumed=False)

        # Các keysym này kết thúc/ngắt từ và không bao giờ được đưa vào
        # pipeline Telex/VNI. Khi không có preedit, trả phím cho ứng dụng.
        if keysym in (KEY_RETURN, KEY_SPACE):
            return self._flush()

        if keysym == KEY_BACKSPACE:
            if self._preedit:
                self._raw_text = self._raw_text[:-1]
                if self._literal:
                    self._literal = self._literal[:-1]
                else:
                    self._base = self._base[:-1]

                self._sync_preedit()

                self._lone_w_pending = False
                return self._result(consumed=True)
            return self._result(consumed=False)   # để app tự xóa

        ch = _keysym_to_char(keysym, mods)
        if not ch:
            # Phím lạ (punctuation, F1...): flush buffer, thả phím qua.
            return self._flush()

        # --- Phím gõ thực sự: đi vào pipeline Telex/VNI ---
        self._raw_text += ch
        if self._literal:
            self._literal += ch
            self._sync_preedit()
            return self._result(consumed=True)

        word = self._base
        literal = ""

        if self._lone_w_pending and ch.lower() == "w":
            # ww -> escape: xóa ư vừa chèn, xuất w thường (chuẩn Telex)
            word = word[:-1]
            literal = "W" if ch.isupper() else "w"
            action_type = "lone_w_escape"
        else:
            action = self._schema.match(word, ch)
            action_type = action.type
            match action:
                case Action(type="none"):
                    new_word = word + ch
                    if self._can_grow(new_word):
                        word += ch
                    else:
                        literal = ch
                case Action(type="mark", value=mark_val):
                    word = self._phon.place_mark(word, mark_val)
                case Action(type="tone", value=tone_val):
                    word = self._phon.place_tone(word, tone_val)
                case Action(type="toggle_tone"):
                    word = self._phon.strip_tone(word)
                    literal = ch
                case Action(type="toggle_mark", value=mark_val):
                    word = self._phon.strip_mark(word, mark_val)
                    literal = ch
                case Action(type="lone_w"):
                    word += "Ư" if ch.isupper() else "ư"
                    action_type = "lone_w"      # giữ cờ

        word = self._phon.reconstruction(word)
        self._base = word
        self._literal += literal
        self._sync_preedit()

        # Chỉ nhánh lone_w giữ cờ; mọi nhánh khác xóa cờ.
        self._lone_w_pending = (action_type == "lone_w")

        return self._result(consumed=True)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------
    def get_preedit_text(self) -> tuple:
        """
        Trả về chuỗi văn bản tạm thời chưa gõ xong
        (text, len)
        """
        return self._preedit, len(self._preedit)

    def get_commit_text(self) -> tuple:
        """
        Trả về chuỗi sau khi biến đổi để chèn thẳng vào ứng dụng
        (text, len)
        """
        text = self._preedit
        if (self._config["enable_spell_check"]
                and self._config["enable_auto_decompose"]
                and (self._literal
                     or (self._base
                         and not self._dict.is_valid_word(self._base)))):
            text = self._raw_text or text
        text = self._apply_macro(text)
        if (text == self._preedit and self._raw_text != self._preedit
                and self._config["enable_macro"]):
            raw_macro = self._apply_macro(self._raw_text)
            if raw_macro != self._raw_text:
                text = raw_macro
        return text, len(text)

    def get_raw_text(self) -> tuple:
        """
        Trả về chuỗi nguyên bản chưa qua xử lý gì
        (text, len)
        """
        return self._raw_text, len(self._raw_text)
    # ------------------------------------------------------------------
    # Cấu hình
    # ------------------------------------------------------------------
    def set_config(self, key: str, value) -> None:
        if key not in self._config:
            return
        if key in {"enable_lone_w", "enable_spell_check",
                   "enable_macro", "enable_auto_decompose"}:
            self._config[key] = bool(value)
            if key == "enable_lone_w" and self._schema.name() == "telex":
                self._schema.set_lone_w(self._config[key])
        elif key == "input_method":
            self._config[key] = value
            self._load_schema(value)
        elif key == "macros":
            if not isinstance(value, dict):
                raise TypeError("macros phải là dict[str, str]")
            self._config[key] = {
                str(trigger): str(replacement)
                for trigger, replacement in value.items()
            }
        elif key == "macro_file":
            self._config[key] = str(value)
            if self._config["enable_macro"]:
                self.load_macro()
        else:
            self._config[key] = value
        if key == "enable_macro" and self._config[key]:
            self.load_macro()
        self.reset()

    def get_config(self, key: str):
        return self._config.get(key)

    def load_macro(self, path=None) -> int:
        """Nạp macro từ file, giữ nguyên macro đã cấu hình thủ công.

        Mỗi dòng CSV có dạng ``trigger,replacement``. Dòng trống và dòng bắt
        đầu bằng ``#`` bị bỏ qua. Vẫn chấp nhận format TSV/``=`` cũ để tương
        thích với file macro người dùng đã có.
        Trả về số macro mới được nạp.
        """
        configured_path = path or self._config["macro_file"]
        if not os.path.isabs(configured_path):
            configured_path = os.path.join(
                os.path.dirname(__file__), configured_path
            )
        loaded = 0
        try:
            with open(configured_path, "r", encoding="utf-8") as macro_file:
                for line_number, row in enumerate(csv.reader(macro_file), 1):
                    line = ",".join(row)
                    line = line.rstrip("\n\r")
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
                            configured_path, line_number
                        )
                        continue
                    trigger = trigger.strip()
                    replacement = replacement.strip()
                    if not trigger:
                        logger.warning(
                            "Bỏ qua macro rỗng tại %s:%d",
                            configured_path, line_number
                        )
                        continue
                    if trigger not in self._config["macros"]:
                        self._config["macros"][trigger] = replacement
                        loaded += 1
        except OSError as exc:
            logger.warning("Không thể tải macro từ %s: %s", configured_path, exc)
        return loaded

    def set_surrounding_text(self, text, cursor_pos):
        """
        Nhận văn bản đứng trước/sau con trỏ từ InputManager.
        Giúp bộ gõ nhận biết ngữ cảnh từ đã gõ trước đó để
        xử lý việc nhấn Backspace hoặc bỏ dấu lùi thông minh.
        """
        if text is None:
            text = ""
        self._surrounding_text = str(text)
        try:
            cursor_pos = int(cursor_pos)
        except (TypeError, ValueError):
            cursor_pos = len(self._surrounding_text)
        self._surrounding_cursor_pos = max(
            0, min(cursor_pos, len(self._surrounding_text))
        )

    # ------------------------------------------------------------------
    # Nội bộ
    # ------------------------------------------------------------------
    def _can_grow(self, text: str) -> bool:
        # Dictionary validation must happen after reconstruction(). Before
        # that step, Telex input can be a transitional spelling such as
        # "nguơ" while the final form will be "người".
        return self._phon.can_grow(text)

    def _apply_macro(self, text: str) -> str:
        if not self._config["enable_macro"] or not text:
            return text
        macros = self._config["macros"]
        return macros.get(text, macros.get(text.lower(), text))

    def _sync_preedit(self) -> None:
        """Đồng bộ chuỗi hiển thị từ phần tiếng Việt và phần literal."""
        self._preedit = self._base + self._literal

    def _load_schema(self, name: str) -> None:
        self._schema = VNISchema() if name.lower() == "vni" else TelexSchema()
        self.reset()

    def _result(self, consumed: bool, commit: str = "") -> dict:
        return {
            "consumed": consumed,
            "commit": commit,
            "preedit": self._preedit,
            "cursor": len(self._preedit),
        }
