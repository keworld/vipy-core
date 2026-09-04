import logging
import os

logger = logging.getLogger(__name__)

_BASE_VOWEL = {
    'á': 'a', 'à': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
    'ă': 'a', 'ắ': 'a', 'ằ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
    'â': 'a', 'ấ': 'a', 'ầ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
    'é': 'e', 'è': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
    'ê': 'e', 'ế': 'e', 'ề': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
    'í': 'i', 'ì': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
    'ó': 'o', 'ò': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
    'ô': 'o', 'ố': 'o', 'ồ': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
    'ơ': 'o', 'ớ': 'o', 'ờ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
    'ú': 'u', 'ù': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
    'ư': 'u', 'ứ': 'u', 'ừ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
    'ý': 'y', 'ỳ': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
    'đ': 'd',
}

_STRIP_TONES = {
    'á': 'a', 'à': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
    'ắ': 'ă', 'ằ': 'ă', 'ẳ': 'ă', 'ẵ': 'ă', 'ặ': 'ă',
    'ấ': 'â', 'ầ': 'â', 'ẩ': 'â', 'ẫ': 'â', 'ậ': 'â',
    'é': 'e', 'è': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
    'ế': 'ê', 'ề': 'ê', 'ể': 'ê', 'ễ': 'ê', 'ệ': 'ê',
    'í': 'i', 'ì': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
    'ó': 'o', 'ò': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
    'ố': 'ô', 'ồ': 'ô', 'ổ': 'ô', 'ỗ': 'ô', 'ộ': 'ô',
    'ớ': 'ơ', 'ờ': 'ơ', 'ở': 'ơ', 'ỡ': 'ơ', 'ợ': 'ơ',
    'ú': 'u', 'ù': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
    'ứ': 'ư', 'ừ': 'ư', 'ử': 'ư', 'ữ': 'ư', 'ự': 'ư',
    'ý': 'y', 'ỳ': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
}
_TONE_LETTERS = frozenset(_STRIP_TONES)


class SyllableDict:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SyllableDict()
            cls._instance.load_once()
        return cls._instance

    def __init__(self):
        self.words = set()
        self._tone_stripped_words = set()
        self.prefixes = set()

    def load_once(self):
        configured = os.environ.get("FCITX_TELEX_DICT")
        here = os.path.dirname(__file__)
        if configured:
            candidates = [configured]
            if not os.path.isabs(configured):
                candidates.append(os.path.join(here, configured))
        else:
            candidates = [
                os.path.join(here, "dict", "vietnamese.cm.dict"),
                os.path.join(here, "..", "data", "vietnamese.cm.dict"),
                os.path.expanduser(
                    "~/.config/fcitx5-vipy/data/vietnamese.cm.dict"
                ),
                os.path.join(os.getcwd(), "dict", "vietnamese.cm.dict"),
            ]
        path = next((c for c in candidates if os.path.isfile(c)), candidates[0])
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line_number, line in enumerate(f):
                    line = line.strip()
                    if line_number == 0 and line.isdigit():
                        continue          # dòng đếm của hunspell .dic
                    slash = line.find('/')
                    if slash != -1:
                        line = line[:slash]
                    if line:
                        self.words.add(line.lower())
            self._tone_stripped_words = {
                "".join(_STRIP_TONES.get(c, c) for c in word)
                for word in self.words
            }
            self._build_prefixes()
        except OSError as exc:
            logger.warning('Không thể tải từ điển từ %s: %s', path, exc)

    def _build_prefixes(self):
        self.prefixes.clear()
        for w in self.words:
            # 1. Tiền tố có dấu đầy đủ
            for i in range(1, len(w) + 1):
                sub = w[:i]
                self.prefixes.add(sub)
                if 'ươ' in sub:
                    self.prefixes.add(sub.replace('ươ', 'uơ'))
                if 'ưo' in sub:
                    self.prefixes.add(sub.replace('ưo', 'uơ'))

            # 2. Tiền tố khi bỏ dấu thanh (giữ nguyên ă, â, ê, ô, ơ, ư, đ)
            st = "".join(_STRIP_TONES.get(c, c) for c in w)
            for i in range(1, len(st) + 1):
                sub = st[:i]
                self.prefixes.add(sub)
                if 'ươ' in sub:
                    self.prefixes.add(sub.replace('ươ', 'uơ'))
                if 'ưo' in sub:
                    self.prefixes.add(sub.replace('ưo', 'uơ'))

            # 3. Tiền tố nguyên âm gốc không dấu (dùng khi đang gõ dở trước khi bỏ dấu)
            base = "".join(_BASE_VOWEL.get(c, c) for c in w)
            for i in range(1, len(base) + 1):
                self.prefixes.add(base[:i])
                if base.startswith('d'):
                    self.prefixes.add(('đ' + base[1:])[:i])

    def is_valid_prefix(self, prefix_low: str) -> bool:
        if not prefix_low:
            return True
        if not self.prefixes:
            return True
        return prefix_low in self.prefixes

    def is_valid_word(self, word_low: str) -> bool:
        """kiểm tra từ HOÀN CHỈNH (có dấu) có trong từ điển không."""
        if not word_low:
            return True
        if not self.words:
            return True  # không tải được từ điển -> không chặn
        if word_low in self.words:
            return True
        # fallback: từ bỏ dấu thanh (nếu dict không đủ dấu)
        if any(char in _TONE_LETTERS for char in word_low):
            return False
        st = "".join(_STRIP_TONES.get(c, c) for c in word_low)
        return st in self._tone_stripped_words
