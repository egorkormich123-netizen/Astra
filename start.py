#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import shutil
import subprocess
from pathlib import Path
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QVBoxLayout, QMessageBox
from PyQt5.QtCore import Qt

# ---------------- Настройки ----------------
WIN_WIDTH, WIN_HEIGHT = 700, 450
TARGET_DIR = Path("/var/AstraAdminTool")
BASE_DIR = Path(__file__).resolve().parent


# ---------------- Вспомогательные функции ----------------
def find_flash_lsblk():
    """
    Ищет флешку с AstraAdminTool через lsblk.
    Возвращает путь к папке AstraAdminTool на флешке или None.
    """
    try:
        result = subprocess.run(
            ["lsblk", "-o", "NAME,RM,MOUNTPOINT", "-nr"],
            stdout=subprocess.PIPE, text=True, check=True
        )
    except subprocess.CalledProcessError:
        return None

    for line in result.stdout.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        name, rm, mount = parts[0], parts[1], parts[2]
        if rm == "1" and mount != "":
            candidate = Path(mount) / "AstraAdminTool"
            if candidate.exists() and candidate.is_dir():
                return candidate
    return None


def copy_project():
    """Проверяет и при необходимости копирует AstraAdminTool в /var"""
    if TARGET_DIR.exists():
        print("[INFO] AstraAdminTool уже установлен.")
    else:
        flash_dir = find_flash_lsblk()
        if not flash_dir:
            QMessageBox.critical(
                None, "Ошибка", "Флешка с AstraAdminTool не найдена")
            sys.exit(1)

        print(f"[INFO] Копирую проект {flash_dir} → {TARGET_DIR}")
        shutil.copytree(flash_dir, TARGET_DIR)
        print("[OK] Копирование завершено.")


def run_python(script_name):
    """Запускает Python-скрипт из TARGET_DIR"""
    script_path = TARGET_DIR / script_name
    if not script_path.exists():
        QMessageBox.critical(None, "Ошибка", f"Файл {script_path} не найден")
        return
    app.quit()
    subprocess.Popen(["python3", str(script_path)], cwd=TARGET_DIR)


def run_shell(shell_name):
    """Запускает shell-скрипт из TARGET_DIR и ждёт завершения"""
    shell_path = TARGET_DIR / shell_name
    if not shell_path.exists():
        QMessageBox.critical(None, "Ошибка", f"Файл {shell_path} не найден")
        return

    QApplication.quit()
    subprocess.run(["bash", str(shell_path)], cwd=TARGET_DIR)

    # После завершения перезапускаем GUI
    subprocess.Popen(["python3", str(BASE_DIR / "start.py")])


def cancel_app():
    """Удаляет папку и завершает работу"""
    reply = QMessageBox.question(
        None,
        "Подтверждение",
        f"Удалить {TARGET_DIR} и выйти?",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No
    )
    if reply == QMessageBox.Yes:
        if TARGET_DIR.exists():
            shutil.rmtree(TARGET_DIR)
            print(f"[OK] Папка {TARGET_DIR} удалена")
        app.quit()


#Главное окно
class Launcher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AstraAdminTool Launcher")
        self.resize(WIN_WIDTH, WIN_HEIGHT)

        from PyQt5.QtWidgets import QLabel, QHBoxLayout, QApplication, QWidget, QVBoxLayout
        from PyQt5.QtCore import Qt, QSize
        from PyQt5.QtGui import QPixmap, QIcon

        # QLabel для фона
        self.background_label = QLabel(self)
        self.background_label.setGeometry(0, 0, self.width(), self.height())
        pixmap = QPixmap("/var/AstraAdminTool/logo/1.jpg")
        self.background_label.setPixmap(pixmap)
        self.background_label.setScaledContents(True)
        self.background_label.lower()  # Отправляем фон назад

        # Основной layout
        layout = QHBoxLayout()
        layout.setSpacing(50)  # расстояние между кнопками

        btn1 = QPushButton("Настройка\nсистемы")
        btn3 = QPushButton("Сбор логов\n(status_log.sh)")
        btn4 = QPushButton("Выход")

        # фон для кнопок
        #button_bg = "/var/AstraAdminTool/logo/11.png"

        #for btn in (btn1, btn3, btn4):
            #btn.setFixedSize(115, 100)
            #btn.setStyleSheet(f"""
                #QPushButton {{
                    #border: none;
                    #background-image: url("{button_bg}");
                    #background-repeat: no-repeat;
                    #background-position: center;
                #}}
            #""")

        btn1.clicked.connect(lambda: run_python("main.py"))
        btn3.clicked.connect(lambda: run_shell("status_log.sh"))
        btn4.clicked.connect(cancel_app)


        # Задаём фиксированный размер кнопок
        for btn in (btn1, btn3, btn4):
            btn.setFixedSize(115, 100)

        layout.addStretch()
        layout.addWidget(btn1, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(btn3, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(btn4, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()



        self.setLayout(layout)

    def resizeEvent(self, event): # type: ignore
        """Обновляем размер фона при изменении окна"""
        self.background_label.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)

    def closeEvent(self, event): # type: ignore
        cancel_app()
        event.accept()


# ---------------- Запуск ----------------
if __name__ == "__main__":
    if os.geteuid() != 0:
        print("[ERR] Запустите через sudo: sudo python3 start.py")
        sys.exit(1)

    # XDG_RUNTIME_DIR для Qt
    if "XDG_RUNTIME_DIR" not in os.environ:
        os.environ["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

    # Сначала проверяем и копируем проект (если нужно)
    copy_project()

    # Запуск GUI
    app = QApplication(sys.argv)
    window = Launcher()
    window.show()
    sys.exit(app.exec_())

        # btn2 = QPushButton("Автомотическая настройка системы")
        # btn2.clicked.connect(lambda: run_python("main_auto.py"))
        # layout.addWidget(btn2)
        #btn1.geometry(20, 10, 100, 30)
        #btn3.geometry(20, 10, 100, 30)
        #btn4.geometry(20, 10, 100, 30)
#layout.addWidget(btn1, alignment=Qt.AlignmentFlag.AlignCenter)

