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

from .vietnamese_phonology import VietnamesePhonology
from .input_schema import TelexSchema, VNISchema, Action

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


class VietnameseEngine:
    def __init__(self, config: dict = None):
        self._phon = VietnamesePhonology()
        self._config = {
            "input_method": "telex",   # "telex" | "vni"
            "append_commit_char": True,
        }
        if config:
            self._config.update(config)
        self._schema = None
        self._load_schema(self._config["input_method"])
        self.reset()

    # ------------------------------------------------------------------
    # Vòng đời (mirrors InputMethodEngineV3)
    # ------------------------------------------------------------------
    def activate(self) -> None:
        pass

    def deactivate(self) -> str:
        """Rời khỏi IME: trả về buffer dở để C++ commit, rồi tự reset."""
        pending = self._base
        self.reset()
        return pending

    def reset(self) -> None:
        """Reset khi đổi focus/context: VỨT buffer, KHÔNG commit."""
        self._base = ""
        self._lone_w_pending = False

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------
    def _flush(self, consumed: bool = False) -> dict:
        """Commit buffer hiện tại (nếu có) và trả result; buffer bị reset."""
        if self._base:
            buf = self._base
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
            if self._base:
                self.reset()
                return self._result(consumed=True)
            return self._result(consumed=False)

        if keysym == KEY_RETURN or keysym == KEY_SPACE:
            return self._flush()

        if keysym == KEY_BACKSPACE:
            if self._base:
                self._base = self._base[:-1]
                self._lone_w_pending = False
                return self._result(consumed=True)
            return self._result(consumed=False)   # để app tự xóa

        ch = _keysym_to_char(keysym, mods)
        if not ch:
            # Phím lạ (punctuation, F1...): flush buffer, thả phím qua.
            return self._flush()

        # --- Phím gõ thực sự: đi vào pipeline Telex/VNI ---
        word = self._base
        literal = ""
        action_type = "none"   # mặc định, được ghi đè bởi các nhánh bên dưới

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
                    word += ch
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
        word += literal
        self._base = word

        # Chỉ nhánh lone_w giữ cờ; mọi nhánh khác xóa cờ.
        self._lone_w_pending = (action_type == "lone_w")

        return self._result(consumed=True)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------
    def get_preedit(self) -> tuple:
        return self._base, len(self._base)

    # ------------------------------------------------------------------
    # Cấu hình
    # ------------------------------------------------------------------
    def set_config(self, key: str, value) -> None:
        if key not in self._config:
            return
        self._config[key] = value
        if key == "input_method":
            self._load_schema(value)
        else:
            self.reset()

    def get_config(self, key: str):
        return self._config.get(key)

    def save(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Nội bộ
    # ------------------------------------------------------------------
    def _load_schema(self, name: str) -> None:
        self._schema = VNISchema() if name.lower() == "vni" else TelexSchema()
        self.reset()

    def _result(self, consumed: bool, commit: str = "") -> dict:
        return {
            "consumed": consumed,
            "commit": commit,
            "preedit": self._base,
            "cursor": len(self._base),
        }
