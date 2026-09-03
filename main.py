import sys

from PySide6.QtWidgets import QApplication
from src.input_manager import InputManager
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)

    InputManager(app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ ==  "__main__":
    main()