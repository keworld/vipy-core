"""
VietnameseEngine — State Orchestrator Fcitx5 (giao tiếp qua C++ wrapper)
và cho adapter (InputManager).

Hợp đồng API:
  - process_key(key, mods, is_release) -> dict:
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

from .vietnamese_phonology import VietnamesePhonology
from .input_schema import TelexSchema, VNISchema, Action
from .syllable_dict import SyllableDict
from .macro import apply_macro, load_macros

# ---------------------------------------------------------------------------
# Special key tokens passed by the Fcitx wrapper.
# ---------------------------------------------------------------------------
KEY_BACKSPACE = "BackSpace"
KEY_RETURN    = "Return"
KEY_ESCAPE    = "Escape"
KEY_TAB       = "Tab"
KEY_SPACE     = "Space"

NAVIGATION_KEYS = frozenset({
    "Left", "Up", "Right", "Down", "Home", "End",
    "PageUp", "PageDown", "Delete",
})

# Modifier bit — phải khớp fcitx5 KeyState (C++ phía wrapper tự map).
MOD_SHIFT = 1 << 0
MOD_CTRL  = 1 << 1
MOD_ALT   = 1 << 2

HOTKEY_MASK = MOD_CTRL | MOD_ALT

class VietnameseEngine:
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

    def process_key(self, key: str, mods: int = 0, is_release: bool = False) -> dict:
        if is_release:
            return self._result(consumed=False)

        # Hotkey Ctrl/Alt: flush buffer (nếu có) rồi thả phím cho app.
        if mods & HOTKEY_MASK:
            return self._flush()

        # Phím điều hướng: flush buffer, KHÔNG nuốt phím.
        if key in NAVIGATION_KEYS:
            return self._flush()

        if key == KEY_TAB:
            return self._flush()

        if key == KEY_ESCAPE:
            # Hủy preedit (Unikey behavior).
            if self._preedit:
                self.reset()
                return self._result(consumed=True)
            return self._result(consumed=False)

        # Các phím đặc biệt này kết thúc/ngắt từ và không bao giờ được đưa vào
        # pipeline Telex/VNI. Khi không có preedit, trả phím cho ứng dụng.
        if key in (KEY_RETURN, KEY_SPACE):
            return self._flush()

        if key == KEY_BACKSPACE:
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

        if not isinstance(key, str) or len(key) != 1 or not key.isalnum():
            # Phím lạ (punctuation, F1...): flush buffer, thả phím qua.
            return self._flush()

        # --- Phím gõ thực sự: đi vào pipeline Telex/VNI ---
        self._raw_text += key
        if self._literal:
            self._literal += key
            self._sync_preedit()
            return self._result(consumed=True)

        word = self._base
        literal = ""

        if self._lone_w_pending and key.lower() == "w":
            # ww -> escape: xóa ư vừa chèn, xuất w thường (chuẩn Telex)
            word = word[:-1]
            literal = "W" if key.isupper() else "w"
            action_type = "lone_w_escape"
        else:
            action = self._schema.match(word, key)
            action_type = action.type
            match action:
                case Action(type="none"):
                    new_word = word + key
                    if self._phon.can_grow(new_word):
                        word += key
                    else:
                        literal = key
                case Action(type="mark", value=mark_val):
                    word = self._phon.place_mark(word, mark_val)
                case Action(type="tone", value=tone_val):
                    word = self._phon.place_tone(word, tone_val)
                case Action(type="toggle_tone"):
                    word = self._phon.strip_tone(word)
                    literal = key
                case Action(type="toggle_mark", value=mark_val):
                    word = self._phon.strip_mark(word, mark_val)
                    literal = key
                case Action(type="lone_w"):
                    word += "Ư" if key.isupper() else "ư"
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
        if self._base and self._config["enable_spell_check"]:
            # SyllableDict lưu từ ở dạng chữ thường; giữ nguyên hoa/thường
            # của preedit nhưng chuẩn hóa riêng giá trị dùng để tra cứu.
            invalid = not self._dict.is_valid_word(self._base.lower())
        else:
            invalid = bool(self._base and
                           not self._phon.is_valid_shape(self._base))
        needs_recovery = bool(self._literal) or invalid
        if self._config["enable_auto_decompose"] and needs_recovery:
            text = self.decompose(text)
        elif self._config["enable_spell_check"] and needs_recovery:
            text = self._raw_text or text
        text = self._apply_macro(text)
        if (text == self._preedit and self._raw_text != self._preedit
                and self._config["enable_macro"]):
            raw_macro = self._apply_macro(self._raw_text)
            if raw_macro != self._raw_text:
                text = raw_macro
        return text, len(text)

    def decompose(self, word: str) -> str:
        """Return the original keystrokes for direct commitment to the app."""
        return self._raw_text or word

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
        """Nạp macro từ file, giữ nguyên macro đã cấu hình thủ công."""
        return load_macros(
            path or self._config["macro_file"],
            self._config["macros"],
        )

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

    def _apply_macro(self, text: str) -> str:
        return apply_macro(
            text,
            self._config["macros"],
            self._config["enable_macro"],
        )

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
