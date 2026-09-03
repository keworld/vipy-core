from dataclasses import dataclass
from functools import lru_cache
import unicodedata as ud
from typing import List


@dataclass(frozen=True)
class Diacritic:
    name: str      # 'breve' | 'circumflex' | 'horn'
    char: str      # ký tự kết quả: ă â ê ô ơ ư
    base: str      # âm gốc: a a e o u


@dataclass(frozen=True)
class Tone:
    name: str
    index: int
    combining: str


@dataclass(frozen=True)
class Mark:
    index: int
    name: str
    on_vowel: bool = True # False với mark biến đổi phụ âm

class VietnamesePhonology:

    PLAIN_VOWELS = 'aeiouy'

    DIACRITICS = {
        d.char: d for d in (
            Diacritic('breve', 'ă', 'a'),
            Diacritic('circumflex', 'â', 'a'),
            Diacritic('circumflex', 'ê', 'e'),
            Diacritic('circumflex', 'ô', 'o'),
            Diacritic('horn', 'ơ', 'o'),
            Diacritic('horn', 'ư', 'u'),
        )
    }

    TONES = {
        t.index: t for t in (
            Tone('acute', 1, '\u0301'),
            Tone('grave', 2, '\u0300'),
            Tone('hook', 3, '\u0309'),
            Tone('tilde', 4, '\u0303'),
            Tone('dot', 5, '\u0323'),
        )
    }

    MARKS = {
        m.index: m for m in (
            Mark(1, 'breve'), # trăng
            Mark(2, 'circumflex'), # mũ
            Mark(3, 'horn'), # móc
            Mark(4, 'stroke', on_vowel=False) # đ
        )
    }

    # --- PHỤ ÂM ---
    CONSONATS = {
        'single': {
            'initial': (
                'b', 'c', 'd', 'đ', 'g', 'h', 'k', 'l',
                'm', 'n', 'p', 'q', 'r', 's', 't', 'v', 'x'
            ),
            'final': ('c', 'm', 'n', 'p', 't'),
        },
        'double': {
            'initial': (
                'ch', 'gh', 'gi', 'kh', 'nh', 'ng', 'ph', 'qu', 'th', 'tr'
            ),
            'final': ('ch', 'nh', 'ng'),
        },
        'triple': {
            'initial': ('ngh',),
            'final': (),
        },
    }

    # --- NGUYÊN ÂM ---
    VOWELS = {
        'single': (
            'a', 'ă', 'â', 'e', 'ê', 'i', 'o', 'ô', 'ơ', 'u', 'ư', 'y'
        ),
        'double': (
            'ai', 'ao', 'au', 'ay', 'âu', 'ây', 'eo', 'ia', 'iê', 'iu',
            'oa', 'oă', 'oe', 'oi', 'ôi', 'ơi', 'ua', 'uâ', 'uơ', 'uô',
            'ui', 'uy', 'ưa', 'ươ', 'ưi', 'ưu', 'uê', 'yê', 'êu',
        ),
        'triple': (
            'iêu', 'oai', 'oao', 'oay', 'oeo', 'uai', 'uay', 'uây',
            'uôi', 'uyu', 'uyê', 'ươu', 'yêu'
        ),
    }

    # --- Precomputed lookup (tính 1 lần khi import, KHÔNG đổi logic) ---
    _ALL_VOWELS = (
        VOWELS['single'] + VOWELS['double'] + VOWELS['triple']
    )
    _VOWEL_SET = frozenset(_ALL_VOWELS)
    # bare(vowel) -> vowel gốc. Dùng cú pháp lambda vì bare là method
    _BARE_TO_VOWEL = {
        ''.join(ch for ch in __import__('unicodedata').normalize('NFD', v)
                if not __import__('unicodedata').combining(ch)
                and ch not in 'đĐ') or v: v
        for v in _ALL_VOWELS
    }
    _BARE_VOWEL_SET = set(_BARE_TO_VOWEL.keys())

    # --- Precomputed onset prefixes ---
    _ALL_ONSETS = (
            CONSONATS['single']['initial']
            + CONSONATS['double']['initial']
            + CONSONATS['triple']['initial']
    )
    _ALL_FINALS = (
            CONSONATS['single']['final']
            + CONSONATS['double']['final']
    )
    # mọi prefix của mọi onset (kể cả full)
    _ONSET_PREFIXES = frozenset(
        _o[:_i] for _o in _ALL_ONSETS for _i in range(1, len(_o) + 1)
    )
    _FINAL_PREFIXES = frozenset(
        _f[:_i] for _f in _ALL_FINALS for _i in range(1, len(_f) + 1)
    )
    _ONSET_PREFIXES = _ONSET_PREFIXES
    _FINAL_PREFIXES = _FINAL_PREFIXES

    # =========================================================
    # helpers
    # =========================================================
    @staticmethod
    def _strip_combining(string: str) -> str:
        """Tách bỏ mọi dấu combining (thanh + phụ), trả về ký tự gốc."""
        if string.isascii():  # fast-path: 'dung', 'DUNG'...
            return string  # ASCII không thể chứa combining mark
        return ''.join(
            ch for ch in ud.normalize('NFD', string)
            if not ud.combining(ch)
        )

    def _is_onset(self, s: str) -> bool:
        c = self.CONSONATS
        return (s in c['single']['initial']
                or s in c['double']['initial']
                or s in c['triple']['initial'])

    def _is_final(self, s: str) -> bool:
        c = self.CONSONATS
        return s in c['single']['final'] or s in c['double']['final']

    # =========================================================
    # PRIVATE FUNCTION
    # =========================================================
    def _valid_tone_index(self, string: str) -> int:
        """Vị trí đặt dấu thanh.
        - qu/gi đầu từ: nguyên âm của chúng tính như phụ âm
        - cụm 'ươ'/'uơ': dấu vào 'ơ'; cụm 'ưa': dấu vào 'ư'
        - nguyên âm đã có dấu phụ (ă â ê ô ơ ư): dấu thanh trên chữ đó
        - vần đóng: dấu vào nguyên âm cuối
        - vần mở: dấu vào nguyên âm áp chót (oa/oe/uy -> âm đầu)"""
        signed, bare, onset, rest, final = self._split_syllable(string.lower())

        vowel_b = rest[:len(rest) - len(final)]
        if not vowel_b:
            # 'gi' một mình ('gì', 'gí', 'gị'...): 'i' vẫn là nguyên âm,
            # dấu thanh đặt trên 'i' — index 1 trong chuỗi 'gi'
            if onset == 'gi':
                return 1
            return -1

        # cụm nguyên âm dạng CÓ DẤU (NFC: 1 ký tự = 1 index)
        vowel_s = signed[len(onset):len(onset) + len(vowel_b)]
        base = len(onset)

        # qu/gi: bỏ nguyên âm đầu của chúng
        if onset.endswith('q') and vowel_b.startswith('u'):
            return base + 1
        if onset == 'gi' and vowel_b.startswith('i') and len(vowel_b) > 1:
            return 1

        # cụm ươ, uơ -> 'ơ'; cụm ưa -> 'ư'
        if vowel_s.startswith('ươ') or vowel_s.startswith('uơ'):
            return base + 1
        if vowel_s.startswith('ưa'):
            return base + 0

        # uê / iê / yê / uô / ê...: thanh nằm trên chữ đã có mũ/móc
        for i, ch in enumerate(vowel_s):
            if ch in self.DIACRITICS:
                return base + i

        if final:  # vần đóng: nguyên âm cuối
            pos = len(vowel_b) - 1
        else:  # vần mở: áp chót
            pos = max(len(vowel_b) - 2, 0)
            if vowel_b in ('oa', 'oe', 'uy'):
                pos = 0
        return base + pos

    def _split_syllable(self, string: str):
        """Chuẩn hóa và tách âm tiết thành signed, bare, onset, rest, final."""
        signed = ud.normalize('NFC', string)
        bare = self.bare(signed)

        onset = ''
        for size in (3, 2, 1):
            if bare[:size] and self._is_onset(bare[:size]):
                onset = bare[:size]
                break
        rest = bare[len(onset):]

        final = ''
        for size in (2, 1):
            tail = rest[-size:]
            if tail and self._is_final(tail):
                final = tail
                break

        return signed, bare, onset, rest, final

    def _vowel_of(self, string: str) -> str:
        """Tách cụm nguyên âm ở dạng CÓ DẤU.
        Dùng bare chỉ để xác định vị trí onset/final (phụ âm luôn không dấu)."""
        signed, bare, onset, rest, final = self._split_syllable(string)

        # cắt trên chuỗi CÓ DẤU bằng chỉ số lấy từ bare
        # (NFC: mỗi ký tự có dấu = 1 codepoint, nên độ dài khớp)
        end = len(bare) - len(final)
        return signed[len(onset):end]

    @staticmethod
    def _restore_case(original: str, lowered_result: str) -> str:
        """Phục hồi hoa/thường theo vị trí: chữ nào ở gốc là HOA
        thì lấy ký tự KẾT QUẢ ở vị trí đó và viết hoa."""
        out = []
        for i, ch in enumerate(lowered_result):
            src = original[i] if i < len(original) else ''
            out.append(ch.upper() if src.isupper() else ch)
            #            ↑ uppercase KẾT QUẢ (đ → Đ), không phải ký tự gốc
        return ''.join(out)


    # =========================================================
    # PUBLIC API
    # =========================================================
    def is_consonant(self, string: str) -> bool:
        string = string.lower()
        return self._is_onset(string) or self._is_final(string)

    def is_vowel(self, string: str) -> bool:
        """Có dấu phụ: khớp đúng bảng VOWELS (âi ≠ ai).
        Không dấu: so bare để 'uo' khớp 'uô'/'ươ' khi đang gõ."""
        if not string:
            return False
        lowered = string.lower()
        signed = lowered if ud.is_normalized('NFC', lowered) else ud.normalize('NFC', lowered)

        stripped = self.strip_tone(signed)
        if any(ch in self.DIACRITICS for ch in stripped):
            return stripped in self._VOWEL_SET
        s = self.bare(signed)
        if not s:
            return False
        return s in self._BARE_VOWEL_SET

    def is_onset_prefix(self, string: str) -> bool:
        """prefix hợp lệ của phụ âm đầu (kể cả prefix chưa hoàn chỉnh)."""
        return bool(string) and string in self._ONSET_PREFIXES

    def is_nucleus_prefix(self, string: str) -> bool:
        s = self.bare(string)
        if not s:
            return False
        return any(self.bare(vv).startswith(s) for vv in self._ALL_VOWELS)

    def is_rhyme_prefix(self, string: str) -> bool:
        s = self.bare(string)
        if self.is_nucleus_prefix(s):
            return True
        for i in range(1, len(s)):
            vowel_part, final_part = s[:i], s[i:]
            vowel_ok = self.is_vowel(vowel_part) or self.is_nucleus_prefix(vowel_part)
            final_ok = final_part in self._FINAL_PREFIXES
            if vowel_ok and final_ok:
                return True
        return False

    def is_valid_shape(self, string: str) -> bool:
        """Âm tiết hoàn chỉnh: nucleus (đã bỏ thanh) phải có trong VOWELS.
        Vần triple (iêu, ươu, uây...) không nhận phụ âm cuối."""
        no_tone = self.strip_tone(ud.normalize('NFC', string.lower()))
        bare = self.bare(no_tone)
        if not bare:
            return False
        # tách phụ âm đầu
        onset = ''
        for size in (3, 2, 1):
            if bare[:size] and self._is_onset(bare[:size]):
                onset = bare[:size]
                break
        rest = bare[len(onset):]
        if not rest:
            return False
        # tách phụ âm cuối
        final = ''
        for size in (2, 1):
            tail = rest[-size:]
            if tail and self._is_final(tail):
                final = tail
                break
        vowel_b = rest[:len(rest) - len(final)]
        if not vowel_b:
            return False
        vowel_s = no_tone[len(onset):len(onset) + len(vowel_b)]

        if vowel_s not in self._VOWEL_SET:
            return False
        if vowel_s in self.VOWELS['triple'] and final:
            return False
        return True

    def can_grow(self, string: str) -> bool:
        """Kiểm tra chuỗi có thể là tiền tố của một từ hợp lệ không (dùng khi đang gõ)."""
        string = string.lower()
        bare = self.bare(string)
        if not bare:
            return True

        # tách phần đã xác định: onset (đủ hoặc prefix)
        onset = ''
        for size in (3, 2, 1):
            head = bare[:size]
            if self._is_onset(head) or self.is_onset_prefix(head):
                onset = head
                break
        rest = bare[len(onset):]

        if not rest:
            return True  # mới chỉ có onset, chưa có gì để judge

        # rest phải là prefix của phần vần
        return self.is_rhyme_prefix(rest)

    def strip_tone(self, string: str) -> str:
        tone_chars = {t.combining for t in self.TONES.values()}  # hoặc gán ở __init__/class-level
        nfd = ud.normalize('NFD', string)
        if not any(ch in tone_chars for ch in nfd):
            return ud.normalize('NFC', nfd)  # không có tone → chỉ cần NFC lại
        out = [ch for ch in nfd if ch not in tone_chars]
        return ud.normalize('NFC', ''.join(out))

    @staticmethod
    def strip_mark(string: str, mark_idx: int) -> str:
        """
        Bỏ một dấu phụ (mark) cụ thể, giữ nguyên dấu thanh và các dấu phụ khác.
        :param string: chuỗi ký tự nền
        :param mark_idx: 1 (breve), 2 (circumflex), 3 (horn), 4 (stroke)
        """
        # Xử lý riêng mark 4 (stroke) vì 'đ'/'Đ' không phân tách trong chuẩn NFD
        if mark_idx == 4:
            return string.replace('đ', 'd').replace('Đ', 'D')

        # Bảng ánh xạ mark_idx sang mã Unicode của dấu phụ tương ứng
        mark_combinings = {
            1: '\u0306',  # breve (dấu trăng của ă)
            2: '\u0302',  # circumflex (dấu mũ của â, ê, ô)
            3: '\u031B',  # horn (dấu móc của ơ, ư)
        }

        target_combining = mark_combinings.get(mark_idx)

        # Nếu mark_idx không nằm trong [1, 2, 3, 4], trả về chuỗi gốc
        if not target_combining:
            return string

        out = []
        # Phân tách chuỗi để bóc đúng ký tự dấu phụ cần xóa
        for ch in ud.normalize('NFD', string):
            if ch == target_combining:
                continue
            out.append(ch)

        # Gom lại thành dạng dựng sẵn (NFC)
        return ud.normalize('NFC', ''.join(out))

    def _bare_vowel(self, string: str) -> str:
        """Strip tone + mark nhưng GIỮ nguyên đ — dùng nội bộ khi đặt mark."""
        return self._strip_combining(string.lower())  # không replace đ

    def bare(self, string: str) -> str:
        return self._bare_cached(string)

    @staticmethod
    @lru_cache(maxsize=4096)
    def _bare_cached(string: str) -> str:
        result = VietnamesePhonology._strip_combining(string)
        return result.replace('đ', 'd').replace('Đ', 'D')

    def reconstruction(self, string: str) -> str:
        # 1. Trích xuất toàn bộ trạng thái
        bare_str = self.bare(string)
        marks = self.word_mark(string)  # Trả về list[int], vd: [3, 4] hoặc [0]
        tone_idx = self.word_tone(string)

        word = bare_str

        # 2. Ráp dấu phụ (mark) trước
        # Lặp qua từng mark để xử lý các từ có nhiều mark (vd: 'Đường' có mark 3 và 4)
        for mark_idx in marks:
            if mark_idx != 0:
                word = self.place_mark(word, mark_idx)

        # 3. Ráp dấu thanh (tone) sau cùng
        # place_tone tự động bỏ qua nếu tone_idx = 0 theo đặc tả
        word = self.place_tone(word, tone_idx)

        return word

    def word_tone(self, string: str) -> int:
        for ch in ud.normalize('NFD', string):
            if not ud.combining(ch):
                continue
            for t in self.TONES.values():
                if ch == t.combining:
                    return t.index
        return 0

    def word_mark(self, string: str) -> list[int]:
        # 1. Chuyển về chữ thường để đồng bộ (xử lý 'Đ', 'TẰNG',...)
        string = string.lower()
        marks = set()

        # 2. Xử lý ngoại lệ chữ 'đ' (phụ âm, không nằm trong DIACRITICS)
        if 'đ' in string:
            for m in self.MARKS.values():
                if m.name == 'stroke':
                    marks.add(m.index)
                    break

        # 3. Tách dấu thanh (Tone) để đưa nguyên âm về dạng chuẩn có trong DIACRITICS
        # Các mã unicode combining của 5 dấu thanh tiếng Việt: sắc, huyền, hỏi, ngã, nặng
        tone_chars = {'\u0301', '\u0300', '\u0309', '\u0303', '\u0323'}

        # Dùng NFD để phân tách, lọc bỏ dấu thanh, sau đó dùng NFC gom lại.
        # Quá trình này biến đổi các từ như 'tằng', 'giằng' thành 'tăng', 'giăng'.
        nfd_string = ud.normalize('NFD', string)
        clean_string = ud.normalize('NFC', ''.join(ch for ch in nfd_string if ch not in tone_chars))

        # 4. Quét đối chiếu các nguyên âm (lúc này 'ằ' đã trở về 'ă')
        for ch in clean_string:
            if ch in self.DIACRITICS:
                d = self.DIACRITICS[ch]
                for m in self.MARKS.values():
                    if m.name == d.name:
                        marks.add(m.index)
                        break

        # Trả về mảng mark đã sắp xếp, nếu không có mark nào thì trả về [0]
        return sorted(list(marks)) if marks else [0]

    def _transform_tone(self, string: str, tone: int) -> str:
        if tone not in self.TONES:
            return string

        tone_obj = self.TONES[tone]
        no_tone = ud.normalize('NFC', self.strip_tone(string))
        idx = self._valid_tone_index(no_tone)

        if idx < 0:
            return string

        chars = list(no_tone)

        # Validation layer: Đảm bảo ký tự đích tại idx phải là một nguyên âm.
        # self.bare() xử lý an toàn các ký tự đã có dấu phụ (vd: 'Â' -> 'a')
        target_char = self.bare(chars[idx]).lower()
        if target_char not in "aeiouy":
            return string

        chars[idx] = ud.normalize('NFC', chars[idx] + tone_obj.combining)
        return ''.join(chars)

    def place_tone(self, string: str, tone: int) -> str:
        if tone not in self.TONES:
            return string
        lowered = self._transform_tone(string.lower(), tone)
        return self._restore_case(string, lowered)

    def _transform_mark(self, string: str, mark: int) -> str:
        if mark not in self.MARKS:
            return string

        mark_name = self.MARKS[mark].name
        # stroke: thay 'd' đầu từ bằng 'đ'
        if mark_name == 'stroke':
            if string.startswith('d'):
                return 'đ' + string[1:]
            return string

        tone_idx = self.word_tone(string)
        bare = self._bare_vowel(string)
        chars = list(bare)
        for i, ch in enumerate(chars):
            if ch not in self.PLAIN_VOWELS:
                continue

            target = None
            for d in self.DIACRITICS.values():
                if d.name == mark_name and d.base == ch:
                    target = d.char
                    break
            if target is None:
                continue

            # --- quy tắc đặc biệt cho 'uo' + horn ---
            # 'uo' ở cuối từ -> chỉ 'o' mang horn: 'ươ'? không, là 'uơ'
            # 'uo' có phần đuôi theo sau -> cả 'u' và 'o' mang horn: 'ươ...'
            if mark_name == 'horn' and ch == 'u' and i + 1 < len(chars) and chars[i + 1] == 'o':
                after = chars[i + 2:]
                # nếu không có gì sau 'uo' -> horn chỉ đặt trên 'o'
                # (xử lý ở vòng lặp kế tiếp khi gặp 'o')
                if after:
                    chars[i] = 'ư'  # horn cho 'u'
                    chars[i + 1] = 'ơ'  # horn cho 'o'
                    result = ''.join(chars)
                    if tone_idx:
                        result = self.place_tone(result, tone_idx)
                    return result
                else:
                    # bỏ qua 'u', để vòng lặp xử lý 'o'
                    continue

            chars[i] = target
            result = ''.join(chars)
            if tone_idx:
                result = self.place_tone(result, tone_idx)
            return result

        return string

    def place_mark(self, string: str, mark: int) -> str:
        if mark not in self.MARKS:
            return string
        lowered = self._transform_mark(string.lower(), mark)
        return self._restore_case(string, lowered)

    def has_vowel(self, string: str) -> bool:
        """Kiểm tra chuỗi có chứa nguyên âm không (hỗ trợ mọi định dạng hoa/thường/có dấu)."""
        # Ép về chữ thường và tách toàn bộ dấu ra khỏi chữ cái gốc.
        # VD: 'Â' -> 'â' -> NFD phân tách thành: 'a' + '\u0302' (dấu mũ)
        nfd_string = ud.normalize('NFD', string.lower())

        # Chỉ cần kiểm tra xem trong chuỗi phân tách có xuất hiện ký tự gốc hay không
        return any(ch in self.PLAIN_VOWELS for ch in nfd_string)

    def can_place_mark(self, string: str, mark_index: int) -> bool:
        """Đặt mark lên từ có cho ra cụm nguyên âm hợp lệ không?
        Kiểm tra trên ký tự CÓ DẤU (uă ≠ ua)."""
        string = string.lower()
        if not string:
            return False
        mark = self.MARKS[mark_index]

        out = self.place_mark(string, mark_index)
        if out == string:
            return False

        # Mark phụ âm: chỉ cần thay đổi xảy ra ('d'→'đ'), không liên quan nguyên âm
        if not mark.on_vowel:
            return True

        # Mark nguyên âm: kết quả phải có vấn hợp lệ
        vowel = self._vowel_of(out)          # vd: 'uă', 'ưa', 'â'

        return vowel in self._VOWEL_SET                # so TRỰC TIẾP, không bare

    # =========================================================
    # MULTI-MARK API
    # =========================================================
    def vowel_components(self, string: str) -> List[str]:
        """Phân tích chuỗi nguyên âm (có thể mang dấu) thành các thành phần đơn.
        'ươ' -> ['u', 'o'], 'uya' -> ['u', 'y', 'a'], 'qủa' -> ['u', 'a'].
        Dùng để biết số nguyên âm và thứ tự của chúng (quyết định vị trí dấu thanh)."""
        bare = self._strip_combining(string.lower())
        return [ch for ch in bare if ch in self.PLAIN_VOWELS]

    def mark_position(self, string: str, mark_index: int) -> int:
        """Trả về index trong string nơi mark_index sẽ được đặt, -1 nếu không hợp lệ.
        Ví dụ: mark_position('uo',  3) -> 1   ('o' mang móc -> 'uơ')
               mark_position('uoc', 3) -> 0   ('u' mang móc -> 'ươc')
               mark_position('aa',  3) -> -1  (horn không áp được)"""
        if mark_index not in self.MARKS:
            return -1
        out = self.place_mark(string, mark_index)
        if out == string:
            return -1
        in_bare = self._bare_vowel(string.lower())
        out_bare = self._bare_vowel(out.lower())
        if len(in_bare) != len(out_bare):           # vd stroke 'd'->'đ': giữ độ dài
            for i, (a, b) in enumerate(zip(in_bare, out_bare)):
                if a != b:
                    return i
            return -1
        for i, (a, b) in enumerate(zip(in_bare, out_bare)):
            if a != b:
                return i
        return -1
