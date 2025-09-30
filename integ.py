#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Astra Admin Tool — установка из /var/AstraAdminTool/Distr/Int.zip
"""
import sys
import os
import shutil
import subprocess
import zipfile
import tarfile
import time
from pathlib import Path
from datetime import datetime

from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QTextEdit, QMessageBox,
    QCheckBox, QVBoxLayout, QLabel, QHBoxLayout, QFileDialog
)
from PyQt5.QtCore import Qt

APP_TITLE = "Astra Admin Tool"

BASE_DIR = Path(__file__).resolve().parent
LOG_FILE = BASE_DIR / "log_integrity.txt"

# ← фиксированное местоположение Int.zip
ZIP_PATH = Path("/var/AstraAdminTool/Distr/Int.zip")
REQUIRED_JSONS = [
    "configuration.json",
    "stateKonfiguracii.json",
    "stateProject.json"]
CLIENTSEC_NAME = "clientsecurity"
PROJECTS_ROOT = Path("/Integrity/Projects")
ENVCTRL_DIR = Path("/var/IntegrityEnvCtrl")
SHARE_PREFIX = Path("/share")

#утилита

def now_str():
    return datetime.now().strftime("[%Y-%m-%d %H:%M:%S]")


def append_log(widget, msg):
    line = f"{now_str()} {msg}"
    widget.append(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def is_root():
    if hasattr(os, "geteuid"):
        return os.geteuid() == 0
    return True


def run_cmd(widget, cmd, cwd=None, env=None):
    append_log(widget, f"[CMD] {' '.join(cmd)}")
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True)
    except Exception as e:
        append_log(widget, f"[ERR] запуск команды: {e}")
        return 1
    if proc.stdout:
        for ln in proc.stdout.splitlines():
            append_log(widget, f"[OUT] {ln}")
    if proc.stderr:
        for ln in proc.stderr.splitlines():
            append_log(widget, f"[ERR] {ln}")
    return proc.returncode


def safe_mkdir(path: Path):
    path.mkdir(parents=True, exist_ok=True)

# GUE


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(820, 660)

        # layout
        main = QVBoxLayout(self)

        self.info_label = QLabel(f"Источник: {ZIP_PATH}")
        main.addWidget(self.info_label)

        # self.check_all = QCheckBox("Выполнить все задачи")
        # main.addWidget(self.check_all)

        self.cb_api = QCheckBox("Установка версии УПИ")
        self.cb_arm = QCheckBox("Установка версии АРМ оператора")
        self.cb_server = QCheckBox("Установка версии Сервер данных")
        self.cb_server_sv = QCheckBox("Установка версии Сервер связи")
        main.addWidget(self.cb_api)
        main.addWidget(self.cb_arm)
        main.addWidget(self.cb_server)
        main.addWidget(self.cb_server_sv)

        btn_layout = QHBoxLayout()
        self.run_button = QPushButton("Выполнить выбранные задачи")
        btn_layout.addWidget(self.run_button)
        main.addLayout(btn_layout)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(360)
        main.addWidget(self.log_box)

        # self.check_all.stateChanged.connect(self.toggle_all)
        self.run_button.clicked.connect(self.run_selected)

        # clear log
        try:
            if LOG_FILE.exists():
                LOG_FILE.unlink()
        except Exception:
            pass

        if not is_root():
            QMessageBox.critical(
                self, APP_TITLE, "Запустите программу под sudo/root")
            self.setDisabled(True)

    def toggle_all(self, state):
        val = state == 2
        self.cb_api.setChecked(val)
        self.cb_arm.setChecked(val)
        self.cb_server.setChecked(val)
        self.cb_server_sv.setChecked(val)

    def run_selected(self):
        tasks = []
        if self.cb_api.isChecked():
            tasks.append(("API", self.on_api))
        if self.cb_arm.isChecked():
            tasks.append(("ARM", self.on_arm))
        if self.cb_server.isChecked():
            tasks.append(("Server", self.on_server))
        if self.cb_server_sv.isChecked():
            tasks.append(("Server_sv", self.on_server))
        if not tasks:
            append_log(self.log_box, "[WARN] Задачи не выбраны")
            return
        for name, fn in tasks:
            append_log(self.log_box, f"[TASK] Начало: {name}")
            try:
                fn()
            except Exception as e:
                append_log(self.log_box, f"[ERR] Исключение: {e}")
            append_log(self.log_box, f"[TASK] Завершено: {name}")
        QMessageBox.information(
            self, APP_TITLE, "Все выбранные задачи завершены")

    #flow 
    def extract_zip(self):
        if not ZIP_PATH.exists():
            append_log(self.log_box, f"[ERR] Int.zip не найден: {ZIP_PATH}")
            return None
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest_root = Path("/home/adminib/Distr")
        dest = dest_root / f"int_{ts}"
        try:
            safe_mkdir(dest)
            append_log(self.log_box, f"[INFO] Распаковка {ZIP_PATH} -> {dest}")
            with zipfile.ZipFile(ZIP_PATH, "r") as z:
                z.extractall(dest)
            return dest
        except Exception as e:
            append_log(self.log_box, f"[ERR] Ошибка распаковки: {e}")
            return None

    def find_installer(self, folder: Path):
        candidate = folder / "IntegrityInstallerLinux" / "IntegrityInstaller.sh"
        if candidate.exists():
            return candidate
        for p in folder.rglob("IntegrityInstaller.sh"):
            return p
        return None

    def run_installer(self, path: Path):
        try:
            path.chmod(path.stat().st_mode | 0o111)
        except Exception:
            pass
        rc = run_cmd(self.log_box, ["/bin/bash",
                     str(path)], cwd=str(path.parent))
        if rc == 0:
            append_log(self.log_box, "[OK] Установщик завершился успешно")
        else:
            append_log(self.log_box, f"[WARN] Установщик вернул код {rc}")

    def copy_jsons(self, folder: Path):
        safe_mkdir(ENVCTRL_DIR)
        for name in REQUIRED_JSONS:
            found = list(folder.rglob(name))
            if not found:
                append_log(self.log_box, f"[WARN] {name} не найден")
                continue
            src = found[0]
            dst = ENVCTRL_DIR / name
            try:
                shutil.copy2(src, dst)
                append_log(self.log_box, f"[OK] {name} скопирован -> {dst}")
            except Exception as e:
                append_log(
                    self.log_box,
                    f"[ERR] Не удалось скопировать {name}: {e}")

    def copy_clientsecurity(self, folder: Path):
        found = list(folder.rglob(CLIENTSEC_NAME))
        if not found:
            append_log(self.log_box, f"[WARN] {CLIENTSEC_NAME} не найден")
            return
        src = found[0]
        targets = sorted(SHARE_PREFIX.glob("IntegrityClientSecurity-*"))
        for t in targets:
            d = t / "data"
            if d.exists():
                try:
                    shutil.copy2(src, d / src.name)
                    append_log(self.log_box,
                               f"[OK] clientsecurity скопирован -> {d}")
                    return
                except Exception as e:
                    append_log(self.log_box, f"[ERR] Ошибка копирования: {e}")

    def deploy_project(self, folder: Path):
        safe_mkdir(PROJECTS_ROOT)
        msg = QMessageBox(self)
        msg.setWindowTitle("Проект")
        msg.setText("Выберите проект: папка или архив")
        btn_folder = msg.addButton("Папка", QMessageBox.AcceptRole)
        btn_archive = msg.addButton("Архив", QMessageBox.AcceptRole)
        msg.addButton("Отмена", QMessageBox.RejectRole)
        msg.exec_()
        clicked = msg.clickedButton()
        if clicked == btn_folder:
            src = QFileDialog.getExistingDirectory(
                self, "Папка проекта", str(folder))
            if not src:
                return
            dst = PROJECTS_ROOT / Path(src).name
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            append_log(self.log_box, f"[OK] Проект скопирован -> {dst}")
        elif clicked == btn_archive:
            path, _ = QFileDialog.getOpenFileName(self, "Архив проекта", str(folder),
                                                  "Archives (*.zip *.tar *.tar.gz *.tgz)")
            if not path:
                return
            dst = PROJECTS_ROOT / Path(path).stem
            if dst.exists():
                shutil.rmtree(dst)
            safe_mkdir(dst)
            try:
                if path.endswith(".zip"):
                    with zipfile.ZipFile(path, "r") as z:
                        z.extractall(dst)
                else:
                    with tarfile.open(path, "r:*") as t:
                        t.extractall(dst)
                append_log(self.log_box, f"[OK] Архив распакован -> {dst}")
            except Exception as e:
                append_log(
                    self.log_box,
                    f"[ERR] Ошибка распаковки проекта: {e}")

    def perform_flow(self):
        folder = self.extract_zip()
        if not folder:
            return
        installer = self.find_installer(folder)
        if installer:
            self.run_installer(installer)
        self.copy_jsons(folder)
        self.copy_clientsecurity(folder)
        self.deploy_project(folder)

    def on_api(self): self.perform_flow()
    def on_arm(self): self.perform_flow()
    def on_server(self): self.perform_flow()


# ---------------- Run ----------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = App()
    w.show()
    sys.exit(app.exec_())
