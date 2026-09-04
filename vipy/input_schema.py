from dataclasses import dataclass
from abc import ABC, abstractmethod

from .vietnamese_phonology import VietnamesePhonology

@dataclass(frozen=True)
class Action:
    value: int # mark= 1...4 | tone = 1...5
    type: str = "none" # none | mark | tone | toggle_mark | toggle_tone | lone_w

class InputSchema(ABC):
    PHON = VietnamesePhonology()
    TONE_KEYS: dict = {}
    MARK_KEYS: tuple = ()
    MARK_PAIRS: dict = {}

    @abstractmethod
    def name(cls) -> str: ...

    @classmethod
    def match(cls, base_string: str, key: str) -> Action:
        """
        Kiểm tra xem một key lên một chuỗi là mark gì hay tone gì.
        """
        key = key.lower()
        if not base_string:
            return Action(value=0, type='none')

        # 1) Kiểm tra Tone
        if key in cls.TONE_KEYS:
            tone = cls.TONE_KEYS[key]
            base_tone = cls.PHON.word_tone(base_string)

            # Toggle Tone
            if tone == base_tone:
                return Action(value=tone, type='toggle_tone')

            # Place Tone
            if cls.PHON.has_vowel(base_string) and cls.PHON.can_grow(base_string):
                toned = cls.PHON.place_tone(base_string, tone)
                if toned != base_string:
                    return Action(value=tone, type='tone')
            return Action(value=0, type='none')

        # 2) Kiểm tra Mark
        if key in cls.MARK_KEYS:
            bare = cls.PHON.strip_tone(base_string)
            base_marks = cls.PHON.word_mark(bare)  # Lấy danh sách mark một lần để tái sử dụng

            # 2a. Xử lý Stroke (Đổi d -> đ / D -> Đ)
            # Fix: Phải kiểm tra cả 'đ' và 'Đ' vì base_string có thể đã mang mark
            for d_char, d_stroke in [('d', 'đ'), ('D', 'Đ')]:
                if (bare.startswith(d_char) or bare.endswith(d_char) or
                        bare.startswith(d_stroke) or bare.endswith(d_stroke)):

                    mark = cls.MARK_PAIRS.get(d_char.lower() + key)
                    # Toggle Mark cho Stroke
                    if mark in base_marks:
                        return Action(value=mark, type='toggle_mark')

                    # Place Mark cho Stroke
                    if mark == 4 and cls.PHON.can_place_mark(bare, 4):
                        return Action(value=4, type='mark')

            # 2b. Xử lý Mark trên Vowel
            vowels = cls.PHON.vowel_components(bare)
            if vowels:
                for ch in reversed(vowels):
                    pair_key = ch + key
                    mark = cls.MARK_PAIRS.get(pair_key)
                    if mark is not None:
                        # Fix: Bổ sung điều kiện kiểm tra Toggle Mark cho Vowel
                        if mark in base_marks:
                            return Action(value=mark, type='toggle_mark')

                        # Place Mark
                        if cls.PHON.mark_position(bare, mark) != -1 or cls.PHON.can_place_mark(bare, mark):
                            return Action(value=mark, type='mark')

        return Action(value=0, type='none')

    @classmethod
    def is_mark(cls, key: str) -> int:
        """
        Kiểm tra một key có phải là một mark hay không.
        :param key: 'w' | 'a' | '8' | '9'
        :return: mark index (1...4) nếu hợp lệ, ngược lại trả về -1
        """
        k = key.lower()
        if k not in cls.MARK_KEYS:
            return  -1

        # Tìm mark value tương ứng trong MARK_PAIRS dựa trên key
        for pair, mark_val in cls.MARK_PAIRS.items():
            if pair.endswith(k):
                return mark_val
        return  -1

    @classmethod
    def is_tone(cls, key: str) -> int:
        """
        Kiểm tra một key có phải là một tone hay không.
        :param key: 'f' | 's' | '1' | '2'
        :return: tone index (1...5) nếu hợp lệ, ngược lại trả về -1
        """
        return cls.TONE_KEYS.get(key.lower(), -1)

class TelexSchema(InputSchema):
    TONE_KEYS = {'s': 1, 'f': 2, 'r': 3, 'x': 4, 'j': 5}
    MARK_KEYS = ('w', 'a', 'e', 'o', 'd')
    MARK_PAIRS = {
        'aa': 2,
        'aw': 1,
        'ee': 2,
        'oo': 2,
        'ow': 3,
        'uw': 3,
        'dd': 4,
    }
    LONE_W_ENABLED = True

    @classmethod
    def name(cls) -> str:
        return 'telex'

    @classmethod
    def set_lone_w(cls, enabled: bool) -> None:
        cls.LONE_W_ENABLED = enabled

    @classmethod
    def match(cls, base_string: str, key: str) -> Action:
        # 1. Thử mark/tone bình thường trước (uw, ow, aw, dd, tone ..)
        action = super().match(base_string, key)
        if action.type != 'none':
            return action

        # 2. Không match được gif -> nếu key là 'w' và lone_w bật -> chèn ư
        if cls.LONE_W_ENABLED and key.lower() == 'w':
            return Action(value= 1 if key.isupper() else -1, type= 'lone_w')

        return action

class VNISchema(InputSchema):
    TONE_KEYS = {'1': 1, '2': 2, '3': 3, '4': 4, '5': 5}
    MARK_KEYS = ('6', '7', '8', '9')
    MARK_PAIRS = {
        'a8': 1,
        'a6': 2,
        'e6': 2,
        'o6': 2,
        'o7': 3,
        'u7': 3,
        'd9': 4,
    }

    @classmethod
    def name(cls) -> str:
        return 'vni'