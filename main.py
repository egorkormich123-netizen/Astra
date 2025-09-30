#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import shutil
import subprocess
import json
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QTextEdit, QMessageBox,
    QInputDialog, QVBoxLayout, QCheckBox, QHBoxLayout
)

APP_TITLE = "Astra Admin Tool"

BASE_DIR = Path(__file__).resolve().parent
DISTR_DIR = BASE_DIR / "Distr"
MANIFEST = DISTR_DIR / "manifest.json"
TOOL_DIR = "/var/AstraAdminTool"
LOG_FILE = BASE_DIR / "log.txt"


# Вспомогательные функции
def run_cmd(cmd, input_text=None, env=None):
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE if input_text else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env
    )
    out, err = proc.communicate(input_text)
    return proc.returncode, out, err


def is_root():
    if hasattr(os, "geteuid"):
        return os.geteuid() == 0  # type: ignore
    return True


def find_flash_with_dists_pool():
    """
    Ищет флешку с папками dists и pool.
    Возвращает путь к корню флешки, если найдены обе папки, иначе None.
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
            root = Path(mount)
            dists_path = root / "dists"
            pool_path = root / "pool"
            if dists_path.exists() and pool_path.exists():
                return root  # флешка найдена
    return None


def ensure_parent(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def copy_files(files, log_func):
    for entry in files:
        src = DISTR_DIR / entry["src"]
        dst = Path(entry["dst"])
        if not src.exists():
            log_func(f"[WARN] Нет исходного файла: {src}")
            continue
        try:
            ensure_parent(dst)
            if entry.get("backup", True) and dst.exists():
                shutil.copy2(dst, dst.with_suffix(dst.suffix + ".bak"))
                log_func(f"[OK] Backup {dst}")
            shutil.copy2(src, dst)
            log_func(f"[OK] {src} → {dst}")
            if "mode" in entry:
                os.chmod(dst, int(entry["mode"], 8))
            if "owner" in entry:
                rc, _, err = run_cmd(["chown", entry["owner"], str(dst)])
                if rc != 0:
                    log_func(f"[WARN] chown: {err.strip()}")
        except Exception as e:
            log_func(f"[ERR] {src} → {dst}: {e}")


def copy_files_sl(files_sl, log_func):
    for entry in files_sl:
        src = DISTR_DIR / entry["src"]
        dst = Path(entry["dst"])
        if not src.exists():
            log_func(f"[WARN] Нет исходного файла: {src}")
            continue
        try:
            ensure_parent(dst)
            if entry.get("backup", True) and dst.exists():
                shutil.copy2(dst, dst.with_suffix(dst.suffix + ".bak"))
                log_func(f"[OK] Backup {dst}")
            shutil.copy2(src, dst)
            log_func(f"[OK] {src} → {dst}")
            if "mode" in entry:
                os.chmod(dst, int(entry["mode"], 8))
            if "owner" in entry:
                rc, _, err = run_cmd(["chown", entry["owner"], str(dst)])
                if rc != 0:
                    log_func(f"[WARN] chown: {err.strip()}")
        except Exception as e:
            log_func(f"[ERR] {src} → {dst}: {e}")


def setup_chrony(log_func):
    """
    Устанавливает и настраивает chrony.
    Логирует процесс через log_func.
    Игнорирует ошибки интерфейса debconf.
    """
    log_func("[TASK] Установка и настройка chrony...")
    try:
        # Установка chrony в неинтерактивном режиме
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        rc, out, err = run_cmd(["apt", "-y", "install", "chrony"], env=env)
        if rc == 0:
            log_func("[OK] chrony установлен")
        else:
            log_func(f"[WARN] apt install chrony вернул {rc}")

        # Настройка конфигурационного файла
        chrony_src = DISTR_DIR / "chrony.conf"
        chrony_dst = Path("/etc/chrony/chrony.conf")
        if chrony_src.exists():
            if chrony_dst.exists():
                shutil.copy2(chrony_dst, chrony_dst.with_suffix(".bak"))
                log_func("[OK] Backup chrony.conf")
            shutil.copy2(chrony_src, chrony_dst)
            log_func("[OK] chrony.conf скопирован")

        # Перезапуск службы
        rc, _, err = run_cmd(["systemctl", "restart", "chrony"])
        if rc == 0:
            log_func("[OK] chrony перезапущен")
        else:
            log_func(f"[WARN] Ошибка при перезапуске chrony: {err.strip()}")

    except Exception as e:
        log_func(f"[ERR] chrony: {e}")


def run_apt_update(log_func):
    log_func("[TASK] Выполняется apt update...")
    try:
        rc, _, err = run_cmd(["apt", "update"])
        if rc == 0:
            log_func("[OK] apt update завершен")
        else:
            log_func(f"[WARN] apt update вернул {rc}: {err.strip()}")
    except Exception as e:
        log_func(f"[ERR] apt update: {e}")


def copy_folders(usb_path, log_func):
    dst_repo = Path("/opt/repo")
    folders = ["dists", "pool"]
    if dst_repo.exists():
        shutil.rmtree(dst_repo)
        log_func(f"[INFO] Старый /opt/repo удален")
    dst_repo.mkdir(parents=True, exist_ok=True)
    log_func(f"[OK] Создан {dst_repo}")
    for folder_name in folders:
        src_folder = usb_path / folder_name
        dst_folder = dst_repo / folder_name
        if src_folder.exists():
            shutil.copytree(src_folder, dst_folder)
            log_func(f"[OK] Папка {folder_name} скопирована в {dst_folder}")
        else:
            log_func(f"[WARN] Папка {folder_name} не найдена на флешке")


def copy_block(log_func):
    folders = [
        (DISTR_DIR / "fly", Path(os.path.expanduser("/home/adminib/.fly/theme/"))),
        (DISTR_DIR / "fly-wm", Path("/usr/share/fly-wm/theme"))
    ]
    for src_dir, dst_dir in folders:
        if not src_dir.exists():
            log_func(f"[WARN] Папка не найдена: {src_dir}")
            continue
        dst_dir.mkdir(parents=True, exist_ok=True)
        for file_path in src_dir.iterdir():
            if file_path.is_file():
                dst_file = dst_dir / file_path.name
                try:
                    subprocess.run(
                        ["cp", str(file_path), str(dst_file)], check=True)
                    subprocess.run(
                        ["chown", "root:root", str(dst_file)], check=True)
                    subprocess.run(["chmod", "644", str(dst_file)], check=True)
                except Exception as e:
                    log_func(f"[ERR] Ошибка: {e}")


# Обработчики
def on_copy(log_func):
    log_func("[TASK] Копирование файлов...")
    try:
        with MANIFEST.open("r", encoding="utf-8") as f:
            data = json.load(f)
        copy_files(data.get("files", []), log_func)
        log_func("[DONE]")
    except Exception as e:
        log_func(f"[ERR] Ошибка: {e}")


def on_copy_sl(log_func):
    log_func("[TASK] Копирование файлов...")
    try:
        with MANIFEST.open("r", encoding="utf-8") as f:
            data = json.load(f)
        copy_files(data.get("files_sl", []), log_func)
        log_func("[DONE]")
    except Exception as e:
        log_func(f"[ERR] Ошибка: {e}")


def on_repo(log_func):
    log_func("[TASK] Поиск флешки и копирование папок в /opt/repo")
    usb_root = find_flash_with_dists_pool()
    if usb_root:
        log_func(f"[INFO] Флешка найдена: {usb_root}")
        copy_folders(usb_root, log_func)
        log_func("[DONE] Копирование папок завершено")
    else:
        log_func("[WARN] Флешка с папками dists и pool не найдена")


def on_apt_update(log_func):
    run_apt_update(log_func)


def on_user(log_func):
    log_func("[TASK]Запуск программы настройки пользователей...")
    try:
        # приостановить main.py
        rc = subprocess.run(
            ["python3", str(BASE_DIR / "kiosk_user.py")],
            check=False
        ).returncode

        if rc == 0:
            log_func("[OK] программа завершина")
        else:
            log_func(f"[WARM] завершился с ошибкой {rc}")

        log_func("[DONE]")
    except Exception as e:
        log_func(f"Ошибка при запуске прогрммы натсройки пользователей: {e}")


def on_chrony(log_func):
    """
    Обработчик кнопки в PyQt5.
    Запускает установку chrony и логирует процесс в QTextEdit.
    """
    log_func("[TASK] Установка и настройка chrony...")
    try:
        setup_chrony(log_func)
        log_func("[DONE] chrony установлен и настроен")
    except Exception as e:
        log_func(f"[ERR] Ошибка при настройке chrony: {e}")


def on_kiosk(log_func):
    log_func("[TASK] Настройка блокировки киоска...")
    try:
        with MANIFEST.open("r", encoding="utf-8") as f:
            data = json.load(f)
        copy_files(data.get("kiosk", []), log_func)
        log_func("[DONE]")
    except Exception as e:
        log_func(f"[ERR] Ошибка: {e}")


def on_el(log_func):
    log_func("[TASK] Настройка энергосбережения...")
    try:
        with MANIFEST.open("r", encoding="utf-8") as f:
            data = json.load(f)
        copy_files(data.get("el", []), log_func)
        log_func("[DONE]")
    except Exception as e:
        log_func(f"[ERR] Ошибка: {e}")


def on_block(log_func):
    log_func("[TASK] Настройка блокировки экрана...")
    try:
        copy_block(log_func)
        log_func("[DONE]")
    except Exception as e:
        log_func(f"[ERR] Ошибка: {e}")


def on_int(log_func):
    log_func("[TASK]Запуск установки интегрити...")
    try:
        # приостановить main.py
        rc = subprocess.run(
            ["python3", str(BASE_DIR / "integ.py")],
            check=False
        ).returncode

        if rc == 0:
            log_func("[OK] программа завершина")
        else:
            log_func(f"[WARM] завершился с ошибкой {rc}")

        log_func("[DONE]")
    except Exception as e:
        log_func(f"Ошибка при запуске прогрммы натсройки пользователей: {e}")


def on_all_repo(log_func):
    on_repo(log_func)
    on_apt_update(log_func)


def on_all_el(log_func):
    on_kiosk(log_func)
    on_el(log_func)
    on_block(log_func)

# GUI


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(800, 650)

        # Очистка старого лога
        try:
            if LOG_FILE.exists():
                LOG_FILE.unlink()
        except Exception:
            pass

        layout = QVBoxLayout()
        self.setLayout(layout)

        # Галочка "Выполнить все задачи"
        self.check_all = QCheckBox("Выполнить все задачи")
        layout.addWidget(self.check_all)

        # Список чекбоксов
        self.checkboxes = [
            (QCheckBox("Блокировка консоли X11\n(xorg.conf)"), on_copy),
            (QCheckBox("Коприовать список источников пакетов\n(sources.list)"), on_copy_sl),
            (QCheckBox("Настроить репозитарий (/opt/repo) \nОбновить список пакетов"), on_all_repo),
            (QCheckBox("Создать пользователя киоска \n(с указанием имени и пароля)"), on_user),
            (QCheckBox("Настроить систему точного времени \n(Chrony)"), on_chrony),
            (QCheckBox(
                "Снять блокировку экрана \n(Киоск, потухание и блокировка экрана)"), on_all_el),
            (QCheckBox("Запустить установку Integrity \n(IntegrityInstaller.sh)"), on_int)
        ]
        for cb, _ in self.checkboxes:
            layout.addWidget(cb)

        # --- Логика синхронизации галки "Выбрать все" ---
        for cb, _ in self.checkboxes:
            cb.stateChanged.connect(self.update_check_all_state)

        # Кнопка выполнить все
        self.run_button = QPushButton("Выполнить выбранные задачи")
        layout.addWidget(self.run_button)

        # Лог
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(200)
        layout.addWidget(self.log_box)

        # Кнопки Назад и Отмена
        nav_layout = QHBoxLayout()
        self.back_button = QPushButton("Назад")
        self.cancel_button = QPushButton("Отмена")
        nav_layout.addWidget(self.back_button)
        nav_layout.addWidget(self.cancel_button)
        layout.addLayout(nav_layout)

        # Подключения
        self.check_all.stateChanged.connect(self.toggle_all)
        self.run_button.clicked.connect(self.run_selected)
        self.back_button.clicked.connect(self.go_back)
        self.cancel_button.clicked.connect(self.cancel_app)

        if not is_root():
            QMessageBox.critical(
                self, APP_TITLE, "Запустите программу под sudo/root")
            self.setDisabled(True)

    # --- Методы для галок ---
    def toggle_all(self, state):
        is_checked = bool(state)
        for cb, _ in self.checkboxes:
            cb.blockSignals(True)
            cb.setChecked(is_checked)
            cb.blockSignals(False)

    def update_check_all_state(self):
        all_checked = all(cb.isChecked() for cb, _ in self.checkboxes)
        self.check_all.blockSignals(True)
        self.check_all.setChecked(all_checked)
        self.check_all.blockSignals(False)

    # --- Остальные методы остаются без изменений ---
    def log(self, msg):
        self.log_box.append(msg)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception as e:
            self.log_box.append(f"[ERR] Ошибка записи в лог: {e}")

    def run_selected(self):
        self.log("[TASK] Запуск выбранных задач...")
        for cb, func in self.checkboxes:
            if self.check_all.isChecked() or cb.isChecked():
                func(self.log)
        self.log("[DONE] Все выбранные задачи выполнены")

    def go_back(self):
        self.log("[INFO] Возврат в start.py...")
        subprocess.Popen(["sudo", "python3", str(BASE_DIR / "start.py")])
        QApplication.quit()

    def cancel_app(self):
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Вы уверены, что хотите удалить {TOOL_DIR}?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.log(f"[INFO] Удаление {TOOL_DIR}...")
            try:
                shutil.rmtree(TOOL_DIR)
                self.log("[OK] Папка удалена")
            except FileNotFoundError:
                self.log("[WARN] Папка уже отсутствует")
            except Exception as e:
                self.log(f"[ERR] Ошибка при удалении: {e}")
            QApplication.quit()
        else:
            self.log("[CANCEL] Удаление отменено")


# ---------------- Запуск ----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = App()
    window.show()
    sys.exit(app.exec_())
