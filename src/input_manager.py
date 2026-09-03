from PySide6.QtCore import QObject, QEvent, Qt, Signal
from PySide6.QtWidgets import QLineEdit, QTextEdit, QPlainTextEdit, QApplication
from PySide6.QtGui import QTextCharFormat, QTextCursor

try:
    from .vietnamese_input_method import VietnameseEngine
except ImportError:
    from vietnamese_input_method import VietnameseEngine

# ---------------------------------------------------------------------------
# Map Qt.Key -> FcitxKeySym (X11 keysym)
# ---------------------------------------------------------------------------
_QT_TO_KEYSYM = {
    Qt.Key_Backspace: 0xFF08,
    Qt.Key_Return:    0xFF0D,
    Qt.Key_Enter:     0xFF0D,
    Qt.Key_Escape:    0xFF1B,
 Qt.Key_Tab:       0xFF09,
    Qt.Key_Left:      0xFF51,
    Qt.Key_Up:        0xFF52,
    Qt.Key_Right:     0xFF53,
    Qt.Key_Down:      0xFF54,
    Qt.Key_Home:      0xFF50,
    Qt.Key_End:       0xFF57,
    Qt.Key_PageUp:    0xFF55,
    Qt.Key_PageDown:  0xFF56,
    Qt.Key_Delete:    0xFFFF,
}

MOD_SHIFT = 1 << 0
MOD_CTRL  = 1 << 1
MOD_ALT   = 1 << 2

_QT_MOD_TO_FCITX = {
    Qt.ShiftModifier:    MOD_SHIFT,
    Qt.ControlModifier:  MOD_CTRL,
    Qt.AltModifier:      MOD_ALT,
}

# Phím điều hướng: nếu engine không xử lý thì commit preedit
# trước khi thả phím qua, nếu không preedit sẽ "ma".
_NAVIGATION_KEYS = {
    Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down,
    Qt.Key_Home, Qt.Key_End,
    Qt.Key_PageUp, Qt.Key_PageDown,
}


def _qt_event_to_keys(event) -> tuple:
    """QKeyEvent -> (keysym, mods). (0, mods) nếu không map được."""
    qt_key = event.key()

    mods = 0
    for qt_mod, bit in _QT_MOD_TO_FCITX.items():
        if event.modifiers() & qt_mod:
            mods |= bit

    if Qt.Key_Space <= qt_key <= Qt.Key_ydiaeresis:
        keysym = qt_key
    elif qt_key in _QT_TO_KEYSYM:
        keysym = _QT_TO_KEYSYM[qt_key]
    else:
        return 0, mods

    # Chuẩn hóa keysym chữ hoa về chữ thường (quy ước X11/fcitx5).
    if 0x41 <= keysym <= 0x5A:            # 'A'-'Z'
        keysym += 0x20

    return keysym, mods


class InputManager(QObject):
    """Qt adapter: cầu nối giữa QKeyEvent và VietnameseEngine.

    Adapter tự track preedit span (khoảng text nó đã ghi lên widget
    thay mặt engine). Mọi thay thế đều dựa trên span đã biết, KHÔNG
    suy diễn từ text trên widget.
    """
    enabledChanged = Signal(bool)

    def __init__(self, app=None, config: dict = None,
                 commit_on_focus_out: bool = True):
        super().__init__(app if isinstance(app, QObject) else None)
        self.engine = VietnameseEngine(config)
        self.commit_on_focus_out = commit_on_focus_out
        if app is not None and hasattr(app, "installEventFilter"):
            app.installEventFilter(self)
        self._enabled = True # engine đang bật hay tắt.
        # --- Preedit span state ---
        # Khi preedit active: span dài _preedit_len ký tự, NGAY TRƯỚC
        # cursor. Cursor luôn nằm ở cuối span.
        self._preedit_len = 0
        self._preedit_widget = None
        self._preedit_extra_widget = None

    # ------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------
    @staticmethod
    def _cursor_pos_in_block(widget):
        """(text, cursor_pos) của block chứa cursor."""
        if isinstance(widget, QLineEdit):
            return widget.text(), widget.cursorPosition()
        cursor = widget.textCursor()
        return cursor.block().text(), cursor.positionInBlock()

    @staticmethod
    def _delete_range(widget, start: int, end: int) -> None:
        """Xóa khoảng [start, end) trong block chứa cursor."""
        if isinstance(widget, QLineEdit):
            widget.setSelection(start, end - start)
            widget.del_()
        else:
            c = widget.textCursor()
            pos = c.block().position()
            c.setPosition(pos + start)
            c.setPosition(pos + end, QTextCursor.KeepAnchor)
            c.removeSelectedText()
            widget.setTextCursor(c)

    @staticmethod
    def _insert_at_cursor(widget, text: str) -> None:
        if isinstance(widget, QLineEdit):
            widget.insert(text)
        else:
            cursor = widget.textCursor()
            cursor.insertText(text)
            widget.setTextCursor(cursor)

    @staticmethod
    def _has_selection(widget) -> bool:
        if isinstance(widget, QLineEdit):
            return widget.hasSelectedText()
        return widget.textCursor().hasSelection()

    @staticmethod
    def _clear_selection(widget) -> None:
        """Xóa selection (hành vi gõ đè chuẩn)."""
        if isinstance(widget, QLineEdit):
            widget.del_()
        else:
            cursor = widget.textCursor()
            cursor.removeSelectedText()
            widget.setTextCursor(cursor)

    @staticmethod
    def _surrounding_text(widget) -> tuple:
        if isinstance(widget, QLineEdit):
            return widget.text(), widget.cursorPosition()
        cursor = widget.textCursor()
        return widget.toPlainText(), cursor.position()

    def _apply_text(self, widget, text: str) -> None:
        """Thay span hiện tại bằng text, hoặc chèn mới nếu chưa có span."""
        if self._preedit_len > 0 and widget is self._preedit_widget:
            _, pos = self._cursor_pos_in_block(widget)
            start = pos - self._preedit_len
            if start >= 0:
                self._delete_range(widget, start, pos)
                self._insert_at_cursor(widget, text)
                self._preedit_len = len(text)
                self._apply_preedit_underline(widget)
                return
            # Span lệch (text đổi ngoài kiểm soát) — chèn mới.
            self._clear_span_state()
        self._insert_at_cursor(widget, text)
        self._preedit_len = len(text)
        self._preedit_widget = widget
        self._apply_preedit_underline(widget)

    def _erase_preedit(self, widget) -> None:
        """Xóa span, đưa cursor về đầu span."""
        if self._preedit_len == 0 or widget is not self._preedit_widget:
            self._clear_span_state()
            return
        _, pos = self._cursor_pos_in_block(widget)
        start = pos - self._preedit_len
        self._clear_span_state()
        if start < 0:
            return  # không đoán được, thôi
        self._delete_range(widget, start, pos)

    def _commit_preedit_inline(self, widget) -> None:
        """Preedit trên widget trở thành text thật (đóng span, giữ text)."""
        self.engine.reset()
        self._clear_span_state()

    def _clear_span_state(self) -> None:
        self._clear_preedit_underline()
        self._preedit_len = 0
        self._preedit_widget = None

    def _apply_preedit_underline(self, widget) -> None:
        """Hiển thị preedit bằng underline mà không đổi định dạng văn bản."""
        if not isinstance(widget, (QTextEdit, QPlainTextEdit)):
            return
        if self._preedit_len <= 0 or widget is not self._preedit_widget:
            return
        _, pos = self._cursor_pos_in_block(widget)
        start = pos - self._preedit_len
        if start < 0:
            return
        cursor = widget.textCursor()
        block_start = cursor.block().position()
        cursor.setPosition(block_start + start)
        cursor.setPosition(block_start + pos, QTextCursor.KeepAnchor)
        fmt = QTextCharFormat()
        fmt.setUnderlineStyle(QTextCharFormat.SingleUnderline)
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format = fmt
        widget.setExtraSelections([selection])
        self._preedit_extra_widget = widget

    def _clear_preedit_underline(self) -> None:
        if self._preedit_extra_widget is not None:
            self._preedit_extra_widget.setExtraSelections([])
            self._preedit_extra_widget = None

    def _toggle_enabled(self, widget) -> None:
        """Ctrl+Space: bật/tắt engine. Khi tắt, preedit đang có
        được commit thành text thật (không mất chữ đang gõ dở)."""
        self._enabled = not self._enabled
        if self._preedit_len > 0 and widget is self._preedit_widget:
            # Preedit đang hiển thị thành text thật.
            self._commit_preedit_inline(widget)
        else:
            self.engine.reset()
        self.enabledChanged.emit(self._enabled)

    def is_enabled(self) -> bool:
        """Trạng thái engine, để UI hiển thị icon/label."""
        return self._enabled

    # ------------------------------------------------------------
    # Event filter chính
    # ------------------------------------------------------------
    def eventFilter(self, watched, event):
        etype = event.type()

        # ---- Mất focus: commit preedit (chuẩn fcitx5), reset. ----
        if etype == QEvent.FocusOut:
            self.engine.reset()
            self._clear_span_state()
            return super().eventFilter(watched, event)

        # ---- Mouse click/dblclick: ngữ cảnh đổi hẳn, vứt buffer.
        # Preedit cũ thành text thật (giữ nguyên, không xóa vì cursor
        # đã đổi chỗ — xóa sai còn tệ hơn). ----
        if etype in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            self.engine.reset()
            self._clear_span_state()
            return super().eventFilter(watched, event)

        if etype != QEvent.KeyPress:
            return super().eventFilter(watched, event)

        widget = watched
        if not isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
            return super().eventFilter(watched, event)

        keysym, mods = _qt_event_to_keys(event)

        # ---- Phím không map được (F1-F12, PrintScreen...):
        # thả qua, giữ nguyên preedit. ----
        if keysym == 0:
            return super().eventFilter(watched, event)

        # ---- Ctrl+Space: bật/tắt engine. ----
        if (mods & MOD_CTRL) and event.key() == Qt.Key_Space:
            self._toggle_enabled(widget)
            return True  # nuốt phím, không cho widget chèn space

        # ---- Ctrl là shortcut (Ctrl+C/V/Z...): widget tự xử lý,
        # không đưa vào engine, không phá preedit.
        if mods & MOD_CTRL:
            return super().eventFilter(watched, event)

        # ---- Selection: xóa TRƯỚC, reset buffer + span. ----
        if self._has_selection(widget):
            self.engine.reset()
            self._clear_span_state()
            self._clear_selection(widget)

        preedit_active = self._preedit_len > 0

        # ---- Engine tắt: mọi phím đi thẳng vào widget. ----
        if not self._enabled:
            self.engine.reset()
            self._clear_span_state()
            return super().eventFilter(watched, event)

        surrounding_text, surrounding_cursor = self._surrounding_text(widget)
        self.engine.set_surrounding_text(surrounding_text, surrounding_cursor)

        try:
            result = self.engine.process_key(keysym, mods, False)
        except TypeError:
            # Engine nhận 2 tham số — thử lại.
            try:
                result = self.engine.process_key(keysym, mods)
            except Exception:
                import traceback
                traceback.print_exc()
                return super().eventFilter(watched, event)
        except Exception:
            import traceback
            traceback.print_exc()
            self._clear_span_state()
            self.engine.reset()
            return super().eventFilter(watched, event)

        if not isinstance(result, dict):
            print(f"[InputManager] result bất thường: {result!r}")
            return super().eventFilter(watched, event)

        commit   = result.get("commit", "")
        preedit  = result.get("preedit", "")
        consumed = result.get("consumed", False)

        # Flush không nuốt phím: span đã hiển thị trở thành text thật,
        # sau đó để widget xử lý chính phím Return/Space/navigation.
        if commit and not consumed:
            if preedit_active:
                self._apply_text(widget, commit)
                self._clear_span_state()
            if event.key() not in (Qt.Key_Return, Qt.Key_Enter,
                                   Qt.Key_Space) and event.key() not in _NAVIGATION_KEYS:
                if not preedit_active:
                    self._apply_text(widget, commit)
                    self._clear_span_state()
            return super().eventFilter(watched, event)

        # ---- Engine xử lý phím. ----
        if consumed:
            if commit:
                # Commit: span thành text thật, đóng span.
                self._apply_text(widget, commit)
                self._clear_span_state()
                self.engine.reset()
                return True

            if preedit:
                # Preedit mới: thay span (hoặc chèn mới), refresh span.
                self._apply_text(widget, preedit)
                return True

            if preedit_active and event.key() == Qt.Key_Escape:
                self._erase_preedit(widget)
                return True

            if preedit_active and event.key() == Qt.Key_Backspace:
                self._erase_preedit(widget)
                self.engine.reset()
                return True

            # Consumed nhưng không hiển thị gì (ctrl+^, ctrl+r của Telex):
            # nuốt im lặng — đúng ý engine.
            return True

        # ---- Engine không xử lý. ----
        if preedit_active:
            qt_key = event.key()

            if qt_key in (Qt.Key_Return, Qt.Key_Enter):
                # Enter giữa chừng: preedit thành text thật, thả Enter qua.
                self._commit_preedit_inline(widget)
                return False

            if qt_key == Qt.Key_Escape:
                # Hủy preedit.
                self.engine.reset()
                self._erase_preedit(widget)
                return True

            if qt_key in _NAVIGATION_KEYS:
                # Di chuyển: preedit thành text thật, thả phím qua.
                self._commit_preedit_inline(widget)
                return False

            if qt_key == Qt.Key_Backspace:
                # Xóa 1 ký tự cuối của span.
                _, pos = self._cursor_pos_in_block(widget)
                start = pos - self._preedit_len
                if start >= 0:
                    self._delete_range(widget, pos - 1, pos)
                    self._preedit_len -= 1
                    if self._preedit_len == 0:
                        self._clear_span_state()
                        self.engine.reset()
                    return True
                # Span lệch — reset sạch.
                self._commit_preedit_inline(widget)
                return False

            if qt_key == Qt.Key_Delete:
                # Delete phía sau span: thả qua, span giữ nguyên.
                return False

            if qt_key == Qt.Key_Space:
                # Dấu cách kết thúc từ: preedit thành text thật,
                # thả space qua để widget chèn khoảng trắng.
                self._commit_preedit_inline(widget)
                return False

        # Không preedit, không consumed: thả phím qua.
        return super().eventFilter(watched, event)
