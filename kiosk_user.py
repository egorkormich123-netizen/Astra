#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import re
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Tuple

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QInputDialog, QMessageBox,
    QPlainTextEdit, QLabel
)


UID_MIN = 1000
HMI_USERNAME = "HMI_Loader"
HMI_PASSWORD = "12345678"
PRINT_PASSWORD_TO_CONSOLE = True
USERNAME_NAME = re.compile(r'^[a-zA-Z0-9_-][a-zA-Z0-9_-]{0,31}$')
BASE_DIR = Path(__file__).resolve().parent
TOOL_DIR = Path("/var/AstraAdminTool")
LOG_FILE = TOOL_DIR / "Logs" / "Kiosk_logs.txt"
KIOSK_MARKER = TOOL_DIR / "kiosk_users.txt"  # simple marker file to remember kiosk users


# --- helper functions ---

def run_cmd(cmd_list: List[str]) -> Tuple[int, str, str]:
    """Run a system command and return (returncode, stdout, stderr)"""
    try:
        res = subprocess.run(cmd_list, text=True, capture_output=True)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def read_passwd_user(uid_min: int = UID_MIN) -> List[Dict]:
    """Read /etc/passwd and return list of users with uid >= uid_min.

    Each dict has keys: username, uid, home, shell
    """
    users = []
    try:
        with open("/etc/passwd", "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(":")
                if len(parts) < 7:
                    continue
                username = parts[0]
                try:
                    uid = int(parts[2])
                except ValueError:
                    continue
                home = parts[5]
                shell = parts[6]
                if uid >= uid_min and username not in ("nobody",):
                    users.append({"username": username, "uid": uid, "home": home, "shell": shell})
    except Exception:
        return []
    return users


def append_log(text: str) -> None:
    now = datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")
    line = f"{now} {text}\n"
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        # Best-effort: if logging to file fails, ignore so UI stays responsive
        pass


# --- GUI ---
class UserManager(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Управление пользователями")
        self.resize(800, 600)

        # Layouts
        main_layout = QVBoxLayout()
        main_layout.addWidget(QLabel("Список пользователей"))

        self.user_list = QListWidget()
        main_layout.addWidget(self.user_list)

        # Buttons row
        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Добавить пользователя")
        self.btn_del = QPushButton("Удалить пользователя")
        #self.btn_toggle = QPushButton("Изменить режим (kiosk/normal)\nНет функцианала")
        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_del)
        #btn_layout.addWidget(self.btn_toggle)
        main_layout.addLayout(btn_layout)

        # HMI Loader quick button
        self.btn_hmi = QPushButton(f"Добавить пользователя {HMI_USERNAME} с паролем {HMI_PASSWORD}")
        main_layout.addWidget(self.btn_hmi)

        # Logs
        main_layout.addWidget(QLabel("Логи"))
        self.logs = QPlainTextEdit()
        self.logs.setReadOnly(True)
        main_layout.addWidget(self.logs, stretch=1)

        # Back / Cancel
        #bottom_layout = QHBoxLayout()
        #self.back_button = QPushButton("Назад")
        #self.cancel_button = QPushButton("Удалить пакет AstraAdminTool")
        #bottom_layout.addWidget(self.back_button)
        #bottom_layout.addWidget(self.cancel_button)
        #main_layout.addLayout(bottom_layout)

        self.setLayout(main_layout)

        # Connect signals
        #self.back_button.clicked.connect(self.go_back)
        #self.cancel_button.clicked.connect(self.cancel_app)
        self.btn_add.clicked.connect(self.add_user)
        self.btn_del.clicked.connect(self.del_user)
        #self.btn_toggle.clicked.connect(self.toggle_user)
        self.btn_hmi.clicked.connect(self.add_hmi_user)

        # Fill list
        self.refresh()

    # UI helpers
    def log(self, text: str) -> None:
        now = datetime.now().strftime("[%H:%M:%S]")
        line = f"{now} {text}"
        self.logs.appendPlainText(line)
        append_log(text)

    def refresh(self) -> None:
        self.user_list.clear()
        users = read_passwd_user()
        for u in users:
            display = f"{u['username']} (uid={u['uid']})"
            # show marker if kiosk
            if self.is_kiosk_user(u['username']):
                display += " [KIOSK]"
            self.user_list.addItem(display)
        self.log(f"[INFO] Список пользователей обновлен: {len(users)} записей")

    # System actions
    def add_user(self) -> None:
        username, ok = QInputDialog.getText(self, "Добавить пользователя", "Имя пользователя:")
        if not ok or not username:
            return
        username = username.strip()
        if not USERNAME_NAME.match(username):
            QMessageBox.warning(self, "Ошибка", "Недопустимое имя пользователя. Допускаются a-z, A-Z, 0-9, _ и -; длина до 32 символов.")
            return
        # choose password
        password, ok = QInputDialog.getText(self, "Пароль", "Пароль пользователя (оставьте пустым для сгенерированного):")
        if not ok:
            return
        if not password:
            # simple generated password — for production use a secure generator
            password = HMI_PASSWORD
        # Confirm
        reply = QMessageBox.question(self, "Подтвердите", f"Создать пользователя '{username}'?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            self.log("[CANCEL] Добавление пользователя отменено")
            return
        # Create user using useradd
        code, out, err = run_cmd(["sudo", "useradd", "-m", "-s", "/bin/bash", username])
        if code == 0:
            self.log(f"[OK] Пользователь '{username}' создан")
            # Set password
            cmd = f"echo '{username}:{password}' | sudo chpasswd"
            code2, out2, err2 = run_cmd(["/bin/sh", "-c", cmd])
            if code2 == 0:
                self.log(f"[OK] Пароль установлен для '{username}'")
                if PRINT_PASSWORD_TO_CONSOLE:
                    print(f"User '{username}' password: {password}")
            else:
                self.log(f"[ERR] Не удалось установить пароль: {err2}")
        else:
            self.log(f"[ERR] Не удалось создать пользователя: {err}")
        self.refresh()

    def del_user(self) -> None:
        item = self.user_list.currentItem()
        if not item:
            QMessageBox.information(self, "Удаление", "Выберите пользователя в списке")
            return
        username = item.text().split()[0]
        reply = QMessageBox.question(self, "Подтверждение", f"Удалить пользователя '{username}' и домашнюю папку?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            self.log("[CANCEL] Удаление пользователя отменено")
            return
        code, out, err = run_cmd(["sudo", "userdel", "-r", username])
        if code == 0:
            self.log(f"[OK] Пользователь '{username}' удален")
            # remove kiosk mark if present
            self.unmark_kiosk(username)
        else:
            self.log(f"[ERR] Не удалось удалить пользователя: {err}")
        self.refresh()

    def toggle_user(self) -> None:
        item = self.user_list.currentItem()
        if not item:
            QMessageBox.information(self, "Toggle", "Выберите пользователя в списке")
            return
        username = item.text().split()[0]
        if self.is_kiosk_user(username):
            # switch to normal
            self.unmark_kiosk(username)
            self.log(f"[INFO] Пользователь '{username}' переключен в режим normal")
        else:
            # switch to kiosk
            self.mark_kiosk(username)
            self.log(f"[INFO] Пользователь '{username}' переключен в режим kiosk")
        self.refresh()

    def add_hmi_user(self) -> None:
        # quick helper to add the HMI loader user
        if not USERNAME_NAME.match(HMI_USERNAME):
            QMessageBox.warning(self, "Ошибка", "HMI_USERNAME не соответствует шаблону")
            return
        # If user already exists, offer to set password
        users = [u['username'] for u in read_passwd_user(uid_min=0)]
        if HMI_USERNAME in users:
            reply = QMessageBox.question(self, "HMI", f"Пользователь '{HMI_USERNAME}' уже существует. Переустановить пароль?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
            cmd = f"echo '{HMI_USERNAME}:{HMI_PASSWORD}' | sudo chpasswd"
            code, out, err = run_cmd(["/bin/sh", "-c", cmd])
            if code == 0:
                self.log(f"[OK] Пароль для '{HMI_USERNAME}' обновлен")
                if PRINT_PASSWORD_TO_CONSOLE:
                    print(f"User '{HMI_USERNAME}' password: {HMI_PASSWORD}")
            else:
                self.log(f"[ERR] Не удалось обновить пароль: {err}")
            return
        # create user
        code, out, err = run_cmd(["sudo", "useradd", "-m", "-s", "/bin/bash", HMI_USERNAME])
        if code == 0:
            cmd = f"echo '{HMI_USERNAME}:{HMI_PASSWORD}' | sudo chpasswd"
            code2, out2, err2 = run_cmd(["/bin/sh", "-c", cmd])
            if code2 == 0:
                self.log(f"[OK] HMI-пользователь '{HMI_USERNAME}' создан с паролем по умолчанию")
                if PRINT_PASSWORD_TO_CONSOLE:
                    print(f"User '{HMI_USERNAME}' password: {HMI_PASSWORD}")
            else:
                self.log(f"[ERR] Не удалось установить пароль для HMI: {err2}")
        else:
            self.log(f"[ERR] Не удалось создать HMI-пользователя: {err}")
        self.refresh()

    def go_back(self) -> None:
        self.log("[INFO] Возврат в main.py...")
        # Try to start the other script if present
        start_script = BASE_DIR / "main.py"
        if start_script.exists():
            run_cmd(["sudo", "python3", str(start_script)])
        QApplication.quit()

    def cancel_app(self) -> None:
        reply = QMessageBox.question(self, "Подтверждение", f"Вы уверены, что хотите удалить '{TOOL_DIR}'? Это действие необратимо.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.log(f"[INFO] Удаление {TOOL_DIR}...")
            try:
                if TOOL_DIR.exists():
                    shutil.rmtree(TOOL_DIR)
                    self.log("[OK] Папка удалена")
                else:
                    self.log("[WARN] Папка уже отсутствует")
            except Exception as e:
                self.log(f"[ERR] Ошибка при удалении: {e}")
            QApplication.quit()
        else:
            self.log("[CANCEL] Удаление отменено")

    # Simple kiosk marking helpers (non-destructive)
    def is_kiosk_user(self, username: str) -> bool:
        try:
            if not KIOSK_MARKER.exists():
                return False
            with open(KIOSK_MARKER, "r", encoding="utf-8") as f:
                return username in [l.strip() for l in f if l.strip()]
        except Exception:
            return False

    def mark_kiosk(self, username: str) -> None:
        try:
            KIOSK_MARKER.parent.mkdir(parents=True, exist_ok=True)
            lines = []
            if KIOSK_MARKER.exists():
                with open(KIOSK_MARKER, "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f if l.strip()]
            if username not in lines:
                lines.append(username)
                with open(KIOSK_MARKER, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
        except Exception as e:
            self.log(f"[ERR] Не удалось пометить kiosk: {e}")

    def unmark_kiosk(self, username: str) -> None:
        try:
            if not KIOSK_MARKER.exists():
                return
            with open(KIOSK_MARKER, "r", encoding="utf-8") as f:
                lines = [l.strip() for l in f if l.strip() and l.strip() != username]
            with open(KIOSK_MARKER, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + ("\n" if lines else ""))
        except Exception as e:
            self.log(f"[ERR] Не удалось снять пометку kiosk: {e}")


# Entry point
def main():
    app = QApplication(sys.argv)
    win = UserManager()
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
