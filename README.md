# vipy-core

**vipy-core** là bộ máy gõ tiếng Việt viết bằng Python, được thiết kế để tích hợp chức năng gõ tiếng Việt vào các ứng dụng Python.

Bộ máy hỗ trợ hai kiểu gõ **Telex** và **VNI**, đồng thời cung cấp các chức năng xử lý dấu tiếng Việt, đặt dấu thanh, kiểm tra âm tiết, macro, tự động phân rã dữ liệu nhập và quản lý trạng thái preedit/commit.

Core engine không phụ thuộc vào một framework giao diện cụ thể. Ngoài ra, dự án cung cấp adapter dành cho các ứng dụng sử dụng **PySide6/Qt**.

## Tính năng

* Hỗ trợ kiểu gõ tiếng Việt **Telex**
* Hỗ trợ kiểu gõ tiếng Việt **VNI**
* Xử lý dấu phụ tiếng Việt
* Đặt dấu thanh tiếng Việt
* Hỗ trợ cách đặt dấu **hiện đại** và **cổ điển**
* Kiểm tra âm tiết tiếng Việt
* Bảo vệ khi gõ từ tiếng Anh
* Tự động khôi phục/phân rã dữ liệu nhập khi cần
* Hỗ trợ macro
* Cấu hình linh hoạt
* Quản lý preedit và commit
* Xử lý Backspace và các phím điều hướng
* Tích hợp với PySide6 thông qua `InputManager`
* Core engine Python không phụ thuộc vào Fcitx5

## Yêu cầu

* Python 3.10 trở lên
* PySide6 chỉ cần thiết nếu sử dụng phần tích hợp Qt

## Cài đặt

Clone repository:

```bash
git clone https://github.com/YOUR_USERNAME/vipy-core.git
cd vipy-core
```

Cài đặt package:

```bash
python -m pip install .
```

Trong quá trình phát triển, nên sử dụng chế độ editable:

```bash
python -m pip install -e .
```

Với editable installation, các thay đổi trong source code sẽ có hiệu lực ngay mà không cần cài đặt lại package.

Kiểm tra package đã được cài đặt:

```bash
python -c "import vipy; print(vipy.__file__)"
```

Kết quả phải trỏ tới thư mục package `vipy` trong project `vipy-core`.

## Sử dụng cơ bản

Core engine chính là:

```python
from vipy.vietnamese_input_method import VietnameseEngine
```

Khởi tạo engine:

```python
engine = VietnameseEngine()
```

Mặc định engine sử dụng Telex:

```python
engine = VietnameseEngine({
    "input_method": "telex",
})
```

Có thể gửi từng phím vào engine thông qua `process_key()`:

```python
from vipy.vietnamese_input_method import VietnameseEngine

engine = VietnameseEngine()

for key in "tieengs":
    result = engine.process_key(key)

print(result["preedit"])
```

`process_key()` trả về một dictionary:

```python
{
    "consumed": True,
    "commit": "",
    "preedit": "tiếng",
    "cursor": 5,
}
```

Ý nghĩa các trường:

| Trường     | Ý nghĩa                                        |
| ---------- | ---------------------------------------------- |
| `consumed` | Cho biết engine đã xử lý phím hay chưa         |
| `commit`   | Văn bản cần được commit trực tiếp vào ứng dụng |
| `preedit`  | Văn bản đang được người dùng gõ dở             |
| `cursor`   | Vị trí con trỏ bên trong preedit               |

Ứng dụng tích hợp có trách nhiệm hiển thị preedit và commit văn bản khi thích hợp.

## Xử lý một từ hoàn chỉnh

Ví dụ với kiểu gõ Telex:

```python
from vipy.vietnamese_input_method import VietnameseEngine

engine = VietnameseEngine()

for key in "tieengs":
    result = engine.process_key(key)

print(result["preedit"])
```

Kết quả:

```text
tiếng
```

Ứng dụng không cần tự triển khai các quy tắc như:

```text
ee -> ê
s  -> sắc
```

Các phép biến đổi này được engine xử lý nội bộ.

## Lấy preedit

Có thể lấy preedit hiện tại bằng:

```python
text, cursor = engine.get_preedit_text()

print(text)
print(cursor)
```

Ví dụ:

```text
tiếng
5
```

Giá trị `cursor` là vị trí con trỏ ở cuối preedit.

## Lấy văn bản cần commit

Khi ứng dụng muốn chuyển phần đang gõ dở thành văn bản thực tế, sử dụng:

```python
text, length = engine.get_commit_text()

print(text)
```

Ví dụ:

```python
engine = VietnameseEngine()

for key in "tieengs":
    engine.process_key(key)

text, _ = engine.get_commit_text()

print(text)
```

Engine cũng xử lý trường hợp dữ liệu đang nhập không tạo thành một âm tiết tiếng Việt hợp lệ. Tùy cấu hình, engine có thể khôi phục lại chuỗi phím gốc thay vì commit một từ tiếng Việt bị biến đổi sai.

## Lấy dữ liệu nhập gốc

Có thể lấy chuỗi phím gốc chưa qua xử lý bằng:

```python
raw, length = engine.get_raw_text()

print(raw)
```

Điều này hữu ích khi ứng dụng cần biết chính xác dữ liệu mà người dùng đã nhập trước khi engine biến đổi nó.

## Reset engine

Để hủy phần đang gõ dở:

```python
engine.reset()
```

`reset()` xóa composition hiện tại.

Nên sử dụng khi ngữ cảnh nhập thay đổi, chẳng hạn khi người dùng chuyển sang một ô nhập văn bản khác.

## Xử lý các phím đặc biệt

Engine nhận các tên phím đặc biệt bên cạnh các ký tự thông thường:

```python
engine.process_key("BackSpace")
engine.process_key("Return")
engine.process_key("Space")
engine.process_key("Escape")
engine.process_key("Tab")
```

Các phím điều hướng cũng được hỗ trợ:

```text
Left
Right
Up
Down
Home
End
PageUp
PageDown
Delete
```

Giá trị `consumed` trong kết quả cho ứng dụng biết phím đó có được engine xử lý hay không.

## Kiểu gõ VNI

Có thể khởi tạo engine với VNI:

```python
from vipy.vietnamese_input_method import VietnameseEngine

engine = VietnameseEngine({
    "input_method": "vni",
})
```

Ví dụ:

```python
for key in "duoc7":
    result = engine.process_key(key)

print(result["preedit"])
```

Engine sẽ xử lý phím số theo quy tắc của kiểu gõ VNI.

Cũng có thể chuyển kiểu gõ sau khi engine đã được khởi tạo:

```python
engine.set_config("input_method", "vni")
```

Chuyển lại sang Telex:

```python
engine.set_config("input_method", "telex")
```

## Cấu hình

Engine cung cấp các tùy chọn cấu hình sau:

```python
config = {
    "input_method": "telex",
    "tone_placement_style": "modern",
    "enable_lone_w": True,
    "enable_spell_check": True,
    "enable_macro": True,
    "enable_auto_decompose": True,
    "macros": {},
    "macro_file": "dict/vietnamese.macro",
    "append_commit_char": True,
}

engine = VietnameseEngine(config)
```

### `input_method`

Chọn kiểu gõ:

```python
"telex"
```

hoặc:

```python
"vni"
```

### `tone_placement_style`

Chọn cách đặt dấu thanh:

```python
"modern"
```

hoặc:

```python
"classic"
```

### `enable_lone_w`

Bật hoặc tắt chức năng `w` đứng riêng trong Telex:

```python
"enable_lone_w": True
```

### `enable_spell_check`

Bật kiểm tra âm tiết tiếng Việt:

```python
"enable_spell_check": True
```

### `enable_macro`

Bật xử lý macro:

```python
"enable_macro": True
```

### `enable_auto_decompose`

Bật cơ chế tự động khôi phục dữ liệu nhập gốc khi từ sau biến đổi không còn là một âm tiết hợp lệ:

```python
"enable_auto_decompose": True
```

## Thay đổi cấu hình

Có thể thay đổi từng tùy chọn:

```python
engine.set_config("input_method", "vni")
engine.set_config("tone_placement_style", "classic")
engine.set_config("enable_spell_check", False)
```

Lấy giá trị cấu hình:

```python
value = engine.get_config("input_method")
```

Việc thay đổi cấu hình sẽ reset phần đang gõ dở.

## Macro

Macro có thể được cấu hình bằng dictionary:

```python
engine.set_config(
    "macros",
    {
        "brb": "be right back",
        "vn": "Việt Nam",
    },
)
```

Bật hoặc tắt macro:

```python
engine.set_config("enable_macro", True)
```

hoặc:

```python
engine.set_config("enable_macro", False)
```

Có thể nạp macro từ file cấu hình:

```python
engine.load_macro()
```

Hoặc chỉ định một file macro khác:

```python
engine.load_macro("/path/to/macro/file")
```

## Tích hợp với ứng dụng PySide6

vipy-core cung cấp adapter Qt dành cho các ứng dụng sử dụng:

* `QLineEdit`
* `QTextEdit`
* `QPlainTextEdit`

Adapter nhận các sự kiện bàn phím của Qt và chuyển chúng sang định dạng mà `VietnameseEngine` hiểu được.

Kiến trúc tổng quát:

```text
QKeyEvent
    │
    ▼
InputManager
    │
    ▼
VietnameseEngine
    │
    ├── preedit
    └── commit
    │
    ▼
Qt text widget
```

Adapter cũng quản lý preedit, điều hướng con trỏ, Backspace, Escape, selection, thay đổi focus và bật/tắt bộ gõ.

Ứng dụng PySide6 tạo một `InputManager` gắn với `QApplication`:

```python
from PySide6.QtWidgets import QApplication

# Import InputManager từ module cung cấp Qt adapter.
# from vipy.<qt_adapter_module> import InputManager

app = QApplication([])

input_manager = InputManager(
    app=app,
    config={
        "input_method": "telex",
    },
)

app.exec()
```

`InputManager` tự cài đặt event filter cho Qt:

```python
app.installEventFilter(input_manager)
```

Do đó ứng dụng không cần tự xử lý từng `QKeyEvent`.

Adapter tự động xử lý:

* Biến đổi tiếng Việt
* Thay thế preedit
* Commit
* Backspace
* Escape
* Return/Enter
* Space
* Điều hướng con trỏ
* Selection
* Thay đổi focus
* Các phím tắt Ctrl
* Bật/tắt bộ gõ

Có thể bật/tắt bộ gõ bằng:

```text
Ctrl + Space
```

Kiểm tra trạng thái:

```python
input_manager.is_enabled()
```

Theo dõi thay đổi trạng thái:

```python
input_manager.enabledChanged.connect(
    lambda enabled: print("Bộ gõ tiếng Việt:", enabled)
)
```

## Sử dụng engine không cần Qt

`VietnameseEngine` không phụ thuộc vào PySide6.

Do đó có thể sử dụng nó trong terminal, text editor, backend hoặc các framework GUI khác:

```python
from vipy.vietnamese_input_method import VietnameseEngine

engine = VietnameseEngine()

while True:
    key = input("Key: ")

    result = engine.process_key(key)

    if result["consumed"]:
        print("Preedit:", result["preedit"])

    if result["commit"]:
        print("Commit:", result["commit"])
```

Việc tách engine khỏi giao diện là có chủ đích. Logic xử lý tiếng Việt không phụ thuộc vào giao diện người dùng.

## API

### `VietnameseEngine`

```python
VietnameseEngine(config=None)
```

Khởi tạo bộ máy gõ tiếng Việt.

### Xử lý phím

```python
process_key(key, mods=0, is_release=False)
```

Xử lý một phím và trả về:

```python
{
    "consumed": bool,
    "commit": str,
    "preedit": str,
    "cursor": int,
}
```

### Preedit

```python
get_preedit_text()
```

Trả về:

```python
(text, cursor)
```

### Commit

```python
get_commit_text()
```

Trả về:

```python
(text, length)
```

### Dữ liệu nhập gốc

```python
get_raw_text()
```

Trả về:

```python
(text, length)
```

### Reset

```python
reset()
```

Hủy composition hiện tại.

### Kích hoạt

```python
activate()
deactivate()
```

`deactivate()` trả về phần văn bản còn đang chờ commit trước khi reset engine.

### Cấu hình

```python
set_config(key, value)
get_config(key)
```

### Văn bản xung quanh con trỏ

Ứng dụng có thể cung cấp văn bản hiện tại và vị trí con trỏ:

```python
engine.set_surrounding_text(text, cursor_pos)
```

Điều này cho phép engine biết ngữ cảnh văn bản xung quanh con trỏ khi xử lý input.

## Phát triển

Clone repository:

```bash
git clone https://github.com/keworld/vipy-core.git
cd vipy-core
```

Cài đặt ở chế độ editable:

```bash
python -m pip install -e .
```

Sau đó, các thay đổi trong source code bên trong package `vipy/` sẽ có hiệu lực ngay.

Kiểm tra package đang được import từ đâu:

```bash
python -c "import vipy; print(vipy.__file__)"
```

## Cấu trúc project

Project tách biệt core engine khỏi lớp tích hợp với ứng dụng:

```text
vipy-core/
├── vipy/
│   ├── vietnamese_input_method.py
│   ├── vietnamese_phonology.py
│   ├── input_schema.py
│   ├── syllable_dict.py
│   ├── macro.py
│   └── ...
├── ui/
└── ...
```

Thành phần trung tâm là `VietnameseEngine`. Nó chịu trách nhiệm tiếp nhận phím và tạo ra kết quả preedit/commit.

Các thành phần tích hợp với ứng dụng được tách riêng, chẳng hạn `InputManager` dành cho PySide6.

## Giấy phép

Xem file `LICENSE` trong repository để biết thông tin về giấy phép sử dụng.

## Phiên bản

Phiên bản ổn định hiện tại:

**v1.0.0**
