import os
import json
import shutil
import subprocess
import threading
import zipfile
from datetime import datetime
from pathlib import Path

import requests

try:
    import gi

    gi.require_version("Gdk", "3.0")
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk
except (ImportError, ValueError) as error:
    raise RuntimeError(
        "GUI wymaga PyGObject i GTK3. Zainstaluj pakiety python3-gi "
        "oraz gir1.2-gtk-3.0."
    ) from error

import minecraft_launcher_lib


MODRINTH_API = "https://api.modrinth.com/v2"
MINECRAFT_VERSION = "1.21.11"
MOD_NAMES = (
    "OneConfig",
    "Fabric API",
    "Fabric Language Kotlin",
    "Compose Multiplatform",
    "Sodium",
    "Iris Shaders",
    "Entity Culling",
    "Mod Menu",
    "FerriteCore",
    "Lithium",
    "ImmediatelyFast",
    "Sodium Extra",
    "AppleSkin",
    "Simple Voice Chat",
    "Zoomify",
    "Dynamic FPS",
    "Mouse Tweaks",
    "Clumps",
)
DEFAULT_RAM_GB = 4


class MinecraftLauncher(Gtk.Window):
    def __init__(self):
        super().__init__(title="Minecraft Launcher")
        self.installation_active = False
        self.minecraft_directory = os.path.join(os.getcwd(), ".minecraft")
        self.settings_path = os.path.join(
            self.minecraft_directory, "launcher_settings.json"
        )
        self.settings_error = None
        self.settings = self.load_settings()
        self.set_default_size(1200, 720)
        geometry = Gdk.Geometry()
        geometry.min_width = 820
        geometry.min_height = 560
        self.set_geometry_hints(
            None,
            geometry,
            Gdk.WindowHints.MIN_SIZE,
        )
        self.connect("destroy", Gtk.main_quit)
        self.load_css()

        overlay = Gtk.Overlay()
        self.add(overlay)
        background_path = os.path.join(os.getcwd(), "assets", "gui", "background.jpg")
        if os.path.isfile(background_path):
            background = Gtk.DrawingArea()
            background_pixbuf = GdkPixbuf.Pixbuf.new_from_file(background_path)
            background.connect("draw", self.draw_background, background_pixbuf)
        else:
            background = Gtk.Box()
        background.set_hexpand(True)
        background.set_vexpand(True)
        background.get_style_context().add_class("background")
        overlay.add(background)

        layout = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        layout.get_style_context().add_class("window-content")
        overlay.add_overlay(layout)

        navigation = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=34)
        navigation.get_style_context().add_class("navigation")
        navigation.set_size_request(-1, 76)
        navigation.set_border_width(18)
        layout.pack_start(navigation, False, False, 0)
        logo_path = self.asset_path("logo.png")
        logo = (
            Gtk.Image.new_from_pixbuf(
                GdkPixbuf.Pixbuf.new_from_file_at_scale(logo_path, 260, 52, True)
            )
            if os.path.isfile(logo_path)
            else Gtk.Label(label="MINECRAFT CLIENT")
        )
        logo.get_style_context().add_class("logo")
        navigation.pack_start(logo, False, False, 0)
        self.nav_buttons = {}
        for label in ("HOME", "MODPACKS", "SETTINGS", "NEWS"):
            item = Gtk.Button(label=label)
            item.get_style_context().add_class(
                "nav-active" if label == "HOME" else "nav-item"
            )
            item.set_relief(Gtk.ReliefStyle.NONE)
            item.connect("clicked", self.navigate, label)
            navigation.pack_start(item, False, False, 0)
            self.nav_buttons[label] = item

        top_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        navigation.pack_end(top_actions, False, False, 0)
        for label, callback in (
            ("⌕", self.search),
            ("●", self.notifications),
            ("●", self.account),
        ):
            action = Gtk.Button(label=label)
            action.get_style_context().add_class("top-action")
            action.set_relief(Gtk.ReliefStyle.NONE)
            action.connect("clicked", callback)
            top_actions.pack_start(action, False, False, 0)
        minimize = Gtk.Button(label="─")
        minimize.get_style_context().add_class("top-action")
        minimize.set_relief(Gtk.ReliefStyle.NONE)
        minimize.connect("clicked", lambda _button: self.iconify())
        top_actions.pack_start(minimize, False, False, 0)
        close = Gtk.Button(label="×")
        close.get_style_context().add_class("top-action")
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.connect("clicked", lambda _button: self.destroy())
        top_actions.pack_start(close, False, False, 0)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.get_style_context().add_class("content")
        content.set_border_width(28)
        layout.pack_start(content, True, True, 0)

        hero = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        hero.get_style_context().add_class("hero")
        content.pack_start(hero, True, True, 0)
        self.hero_version = Gtk.Label(label="1.21.11 FABRIC")
        self.hero_version.get_style_context().add_class("hero-version")
        self.hero_version.set_xalign(0)
        hero.pack_start(self.hero_version, False, False, 0)
        self.hero_text = Gtk.Label(label="Najnowsza wersja")
        self.hero_text.get_style_context().add_class("hero-text")
        self.hero_text.set_xalign(0)
        hero.pack_start(self.hero_text, False, False, 0)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        hero.pack_start(controls, False, False, 18)
        self.launch_button = Gtk.Button(label="GRAJ  ▶")
        self.launch_button.get_style_context().add_class("play-button")
        self.launch_button.connect("clicked", self.start_installation)
        controls.pack_start(self.launch_button, False, False, 0)
        settings_button = Gtk.Button(label="⚙")
        settings_button.get_style_context().add_class("settings-button")
        settings_button.connect("clicked", self.focus_settings)
        controls.pack_start(settings_button, False, False, 0)

        profiles = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        profiles.get_style_context().add_class("profiles")
        content.pack_end(profiles, False, False, 0)
        profile_data = (
            ("1.21.11 FABRIC", "card-fabric-1211.jpg", "fabric", True),
            ("1.20.6 FABRIC", "card-fabric-1206.jpg", "fabric", False),
            ("1.19.4 FORGE", "card-forge-1194.jpg", "vanilla", False),
        )
        self.profile_buttons = {}
        for label, image_name, install_type, active in profile_data:
            card_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            card_content.set_border_width(10)
            image_path = self.asset_path(image_name)
            if os.path.isfile(image_path):
                card_content.pack_start(
                    Gtk.Image.new_from_pixbuf(
                        GdkPixbuf.Pixbuf.new_from_file_at_scale(
                            image_path, 220, 124, True
                        )
                    ),
                    True,
                    True,
                    0,
                )
            card_label = Gtk.Label(label=label)
            card_label.set_xalign(0)
            card_content.pack_start(card_label, False, False, 0)
            card = Gtk.Button()
            card.add(card_content)
            card.get_style_context().add_class(
                "profile-card" if active else "profile-card-muted"
            )
            card.connect("clicked", self.select_profile, install_type, label)
            profiles.pack_start(card, True, True, 0)
            self.profile_buttons[label] = card

        settings_card = Gtk.Frame()
        settings_card.get_style_context().add_class("settings-panel")
        settings_card.set_no_show_all(True)
        settings_card.set_hexpand(True)
        content.pack_start(settings_card, False, False, 0)
        self.settings_card = settings_card
        settings_card.hide()
        settings = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        settings.set_border_width(14)
        settings.set_hexpand(True)
        settings_card.add(settings)

        version_label = Gtk.Label(label="Wersja Minecraft")
        version_label.get_style_context().add_class("field-label")
        version_label.set_xalign(0)
        settings.pack_start(version_label, False, False, 0)

        self.version_entry = Gtk.Entry()
        self.version_entry.set_hexpand(True)
        self.version_entry.get_style_context().add_class("readonly-entry")
        self.version_entry.set_text(MINECRAFT_VERSION)
        self.version_entry.set_editable(False)
        settings.pack_start(self.version_entry, False, False, 0)

        type_label = Gtk.Label(label="Typ instalacji")
        type_label.get_style_context().add_class("field-label")
        type_label.set_xalign(0)
        settings.pack_start(type_label, False, False, 0)

        self.type_combo = Gtk.ComboBoxText()
        self.type_combo.set_hexpand(True)
        self.type_combo.append("vanilla", "Vanilla")
        self.type_combo.append("fabric", "Fabric")
        self.type_combo.set_active_id("vanilla")
        settings.pack_start(self.type_combo, False, False, 0)

        username_label = Gtk.Label(label="Nazwa użytkownika")
        username_label.get_style_context().add_class("field-label")
        username_label.set_xalign(0)
        settings.pack_start(username_label, False, False, 0)

        self.username_entry = Gtk.Entry()
        self.username_entry.set_hexpand(True)
        self.username_entry.set_text(self.settings.get("username", ""))
        self.username_entry.set_placeholder_text("Wpisz swój nick")
        settings.pack_start(self.username_entry, False, False, 0)

        status_card = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        status_card.get_style_context().add_class("status-card")
        content.pack_start(status_card, False, False, 0)

        self.spinner = Gtk.Spinner()
        self.spinner.set_no_show_all(True)
        status_card.pack_start(self.spinner, False, False, 0)

        self.status_label = Gtk.Label(label="Gotowy do gry")
        self.status_label.get_style_context().add_class("status")
        self.status_label.set_xalign(0)
        if self.settings_error:
            self.status_label.set_text(self.settings_error)
        status_card.pack_start(self.status_label, True, True, 0)

        self.progress = Gtk.ProgressBar()
        self.progress.get_style_context().add_class("download-progress")
        content.pack_start(self.progress, False, False, 0)
        self.progress_max = 1

        self.progress.set_no_show_all(True)
        self.progress.hide()

    def focus_settings(self, _button):
        self.show_settings()

    def navigate(self, _button, page):
        for label, button in self.nav_buttons.items():
            button.get_style_context().remove_class("nav-active")
            button.get_style_context().add_class(
                "nav-active" if label == page else "nav-item"
            )
        if page == "SETTINGS":
            self.show_settings()
        elif page == "HOME":
            self.settings_card.hide()
            self.status_label.set_text("Gotowy do gry")
        elif page == "MODPACKS":
            self.settings_card.hide()
            self.status_label.set_text("Dostępne profile są pokazane poniżej.")
        else:
            self.settings_card.hide()
            self.status_label.set_text("Brak nowych wiadomości.")

    def search(self, _button):
        self.status_label.set_text("Wyszukiwanie jest dostępne w katalogu profili.")

    def notifications(self, _button):
        self.status_label.set_text("Brak nowych powiadomień.")

    def account(self, _button):
        self.show_settings()

    def show_settings(self):
        dialog = Gtk.Dialog(
            title="Ustawienia launchera",
            transient_for=self,
            flags=Gtk.DialogFlags.MODAL,
        )
        dialog.add_buttons(
            "Anuluj",
            Gtk.ResponseType.CANCEL,
            "Zapisz",
            Gtk.ResponseType.OK,
        )
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_resizable(True)
        dialog.set_default_size(420, 260)

        panel = dialog.get_content_area()
        panel.set_border_width(20)
        panel.set_spacing(12)

        title = Gtk.Label(label="Ustawienia profilu")
        title.get_style_context().add_class("hero-text")
        title.set_xalign(0)
        panel.pack_start(title, False, False, 0)

        version_label = Gtk.Label(label=f"Wersja: {MINECRAFT_VERSION}")
        version_label.set_xalign(0)
        panel.pack_start(version_label, False, False, 0)

        username = Gtk.Entry()
        username.set_text(self.username_entry.get_text())
        username.set_placeholder_text("Nazwa użytkownika")
        username.set_hexpand(True)
        panel.pack_start(username, False, False, 0)

        install_type = Gtk.ComboBoxText()
        install_type.append("vanilla", "Vanilla")
        install_type.append("fabric", "Fabric")
        install_type.set_active_id(self.type_combo.get_active_id() or "vanilla")
        install_type.set_hexpand(True)
        panel.pack_start(install_type, False, False, 0)

        ram_label = Gtk.Label(label="Pamięć RAM")
        ram_label.set_xalign(0)
        panel.pack_start(ram_label, False, False, 0)
        ram = Gtk.SpinButton.new_with_range(2, 32, 1)
        ram.set_value(self.settings.get("ram_gb", DEFAULT_RAM_GB))
        panel.pack_start(ram, False, False, 0)

        profiles_label = Gtk.Label(label="Profil nicku")
        profiles_label.set_xalign(0)
        panel.pack_start(profiles_label, False, False, 0)
        profiles = Gtk.ComboBoxText()
        profile_names = self.settings.get("profiles", [])
        if not profile_names:
            profile_names = [self.username_entry.get_text()]
        for profile_name in profile_names:
            profiles.append_text(profile_name)
        profiles.set_active(0)
        panel.pack_start(profiles, False, False, 0)

        mods_frame = Gtk.Frame(label="Mody")
        mods_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        mods_box.set_border_width(8)
        enabled_mods = set(self.settings.get("enabled_mods", MOD_NAMES))
        mod_checks = {}
        for mod_name in MOD_NAMES:
            check = Gtk.CheckButton(label=mod_name)
            check.set_active(mod_name in enabled_mods)
            mods_box.pack_start(check, False, False, 0)
            mod_checks[mod_name] = check
        mods_scroll = Gtk.ScrolledWindow()
        mods_scroll.set_min_content_height(120)
        mods_scroll.add(mods_box)
        mods_frame.add(mods_scroll)
        panel.pack_start(mods_frame, True, True, 0)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        backup = Gtk.Button(label="Kopia konfiguracji")
        backup.connect("clicked", lambda _button: self.create_backup())
        actions.pack_start(backup, True, True, 0)
        repair = Gtk.Button(label="Napraw instalację")
        repair.connect("clicked", lambda _button: self.repair_installation())
        actions.pack_start(repair, True, True, 0)
        logs = Gtk.Button(label="Pokaż logi")
        logs.connect("clicked", lambda _button: self.show_logs())
        actions.pack_start(logs, True, True, 0)
        updates = Gtk.Button(label="Sprawdź mody")
        updates.connect("clicked", lambda _button: self.check_updates())
        actions.pack_start(updates, True, True, 0)
        panel.pack_start(actions, False, False, 0)

        dialog.show_all()
        username.grab_focus()
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            value = username.get_text().strip()
            if value:
                self.username_entry.set_text(value)
                self.type_combo.set_active_id(install_type.get_active_id())
                names = self.settings.setdefault("profiles", [])
                if value not in names:
                    names.append(value)
                self.settings["ram_gb"] = int(ram.get_value())
                self.settings["enabled_mods"] = [
                    name for name, check in mod_checks.items() if check.get_active()
                ]
                self.save_settings(MINECRAFT_VERSION, value)
                self.status_label.set_text("Ustawienia zapisane.")
        dialog.destroy()

    def create_backup(self):
        config_dir = Path(self.minecraft_directory) / "config"
        if not config_dir.is_dir():
            self.status_label.set_text("Brak konfiguracji do skopiowania.")
            return
        backup_dir = Path(self.minecraft_directory) / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        archive = backup_dir / f"config-{datetime.now():%Y%m%d-%H%M%S}.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as backup:
            for file in config_dir.rglob("*"):
                if file.is_file():
                    backup.write(file, file.relative_to(self.minecraft_directory))
        self.status_label.set_text(f"Utworzono kopię: {archive.name}")

    def repair_installation(self):
        marker = Path(self.minecraft_directory) / "mods" / ".launcher-installed.json"
        if marker.exists():
            marker.unlink()
        self.status_label.set_text("Instalacja zostanie naprawiona przy następnym uruchomieniu.")

    def show_logs(self):
        dialog = Gtk.Dialog(title="Logi Minecrafta", transient_for=self)
        dialog.add_button("Zamknij", Gtk.ResponseType.CLOSE)
        dialog.set_default_size(760, 480)
        text = Gtk.TextView()
        text.set_editable(False)
        text.set_monospace(True)
        log_path = Path(os.getcwd()) / "logs" / "latest.log"
        try:
            content = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError as error:
            content = f"Nie można odczytać logu: {error}"
        text.get_buffer().set_text(content)
        scroll = Gtk.ScrolledWindow()
        scroll.add(text)
        dialog.get_content_area().add(scroll)
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def check_updates(self):
        self.status_label.set_text("Sprawdzanie wersji modów...")
        try:
            response = requests.get(
                f"{MODRINTH_API}/project/sodium/version",
                params={
                    "game_versions": json.dumps([MINECRAFT_VERSION]),
                    "loaders": json.dumps(["fabric"]),
                },
                timeout=20,
            )
            response.raise_for_status()
            self.status_label.set_text("Mody mają dostępne wersje dla tej wersji Minecrafta.")
        except requests.RequestException as error:
            self.status_label.set_text(f"Nie można sprawdzić modów: {error}")

    def asset_path(self, filename):
        return os.path.join(os.getcwd(), "assets", "gui", filename)

    @staticmethod
    def draw_background(_widget, context, pixbuf):
        width = max(1, context.get_target().get_width())
        height = max(1, context.get_target().get_height())
        source_width = pixbuf.get_width()
        source_height = pixbuf.get_height()
        scale = max(width / source_width, height / source_height)
        scaled_width = max(1, round(source_width * scale))
        scaled_height = max(1, round(source_height * scale))
        scaled = pixbuf.scale_simple(
            scaled_width, scaled_height, GdkPixbuf.InterpType.BILINEAR
        )
        context.save()
        context.translate((width - scaled_width) / 2, (height - scaled_height) / 2)
        Gdk.cairo_set_source_pixbuf(context, scaled, 0, 0)
        context.paint()
        context.restore()
        return False

    def select_profile(self, _button, install_type, label):
        self.type_combo.set_active_id(install_type)
        self.hero_version.set_text(label)
        self.hero_text.set_text(
            "Najnowsza wersja" if label.startswith("1.21.11") else "Profil alternatywny"
        )
        for profile_label, card in self.profile_buttons.items():
            card.get_style_context().remove_class("profile-card")
            card.get_style_context().add_class(
                "profile-card" if profile_label == label else "profile-card-muted"
            )
        self.status_label.set_text(f"Wybrano profil: {label}")

    def load_css(self):
        css = b"""
        window {
            background: #101426;
            color: #eef2ff;
        }
        .background {
            background: #141a30;
        }
        .window-content {
            background: rgba(8, 11, 20, 0.58);
        }
        .navigation {
            min-height: 54px;
            background: rgba(8, 11, 20, 0.86);
            border-bottom: 1px solid rgba(120, 166, 255, 0.24);
        }
        .logo {
            color: #f3f6ff;
            font-size: 18px;
            font-weight: 900;
            margin-right: 22px;
        }
        .nav-item, .nav-active {
            color: #d7d9e3;
            font-size: 12px;
            font-weight: 800;
            padding: 10px 12px;
            background: transparent;
            box-shadow: none;
        }
        .nav-active {
            color: #ffffff;
            border-bottom: 2px solid #ffffff;
        }
        .nav-item:hover, .nav-active:hover {
            color: #ffffff;
            background: rgba(91, 124, 250, 0.18);
        }
        .top-action {
            min-width: 30px;
            min-height: 30px;
            color: #f3f6ff;
            font-size: 18px;
            background: transparent;
        }
        .top-action:hover {
            color: #168cff;
            background: rgba(255, 255, 255, 0.1);
        }
        .content { background: transparent; }
        .hero {
            min-height: 300px;
            padding: 28px 20px;
            border-radius: 18px;
            background: linear-gradient(
                to right,
                rgba(4, 7, 14, 0.84),
                rgba(4, 7, 14, 0.38),
                rgba(4, 7, 14, 0.08)
            );
        }
        .hero-version {
            color: #ffffff;
            font-size: 44px;
            font-weight: 900;
        }
        .hero-text {
            color: #b9c9ee;
            font-size: 18px;
        }
        .play-button {
            min-width: 190px;
            min-height: 50px;
            border-radius: 30px;
            background: #4f7cff;
            color: #ffffff;
            font-size: 20px;
            font-weight: 900;
        }
        .play-button:hover { background: #7095ff; }
        .play-button:active { background: #3d66d8; }
        .settings-button {
            min-width: 58px;
            min-height: 54px;
            border-radius: 12px;
            background: rgba(25, 34, 58, 0.92);
            color: #ffffff;
            font-size: 25px;
        }
        .settings-button:hover {
            background: rgba(79, 124, 255, 0.7);
        }
        .profiles { background: transparent; }
        .profile-card, .profile-card-muted {
            min-height: 138px;
            border-radius: 13px;
            color: #ffffff;
            font-size: 14px;
            font-weight: 900;
            background: rgba(18, 24, 38, 0.94);
            border: 2px solid #4f7cff;
            padding: 0;
        }
        .profile-card-muted {
            border-color: rgba(255, 255, 255, 0.14);
        }
        .profile-card:hover, .profile-card-muted:hover {
            background: rgba(47, 69, 119, 0.96);
            border-color: #7095ff;
        }
        .settings-panel {
            background: rgba(17, 24, 39, 0.97);
            border: 1px solid rgba(120, 166, 255, 0.3);
            border-radius: 16px;
            margin: 0;
            padding: 0;
        }
        .settings-panel entry, .settings-panel combobox button {
            min-height: 30px;
            min-width: 0;
        }
        .subtitle, .field-label { color: #9da8c7; font-size: 12px; }
        .field-label { color: #cbd4ed; font-weight: 600; }
        .card {
            background: #151d2b;
            border: 1px solid #2c3550;
            border-radius: 12px;
        }
        entry, combobox button {
            min-height: 34px;
            border-radius: 8px;
            border: 1px solid #394563;
            background: #121621;
            color: #f5f7ff;
            padding: 5px 10px;
        }
        .readonly-entry { color: #8f9bbb; }
        .status-card {
            background: rgba(23, 29, 42, 0.9);
            border: 1px solid rgba(120, 166, 255, 0.2);
            border-radius: 10px;
            padding: 7px 12px;
            min-height: 26px;
        }
        .status { color: #cbd4ed; }
        progressbar trough {
            min-height: 7px;
            border-radius: 5px;
            background: #20283a;
        }
        progressbar progress {
            min-height: 7px;
            border-radius: 5px;
            background: #62d6a7;
        }
        dialog {
            background: #111827;
            color: #eef2ff;
        }
        dialog label { color: #d7def3; }
        dialog frame {
            border: 1px solid #354568;
            border-radius: 10px;
        }
        dialog frame > label {
            color: #a9c1ff;
            font-weight: 700;
        }
        dialog checkbutton { color: #d7def3; padding: 3px; }
        dialog checkbutton:hover { color: #ffffff; }
        dialog scrolledwindow {
            background: rgba(7, 11, 21, 0.55);
        }
        button.suggested-action {
            min-height: 42px;
            border-radius: 10px;
            background: #5b7cfa;
            color: white;
            font-weight: 700;
        }
        button.suggested-action:hover { background: #7692ff; }
        button.suggested-action:disabled { background: #30394f; color: #8792af; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def load_settings(self):
        try:
            with open(self.settings_path, encoding="utf-8") as settings_file:
                settings = json.load(settings_file)
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as error:
            self.settings_error = f"Nie można wczytać ustawień: {error}"
            return {}

        if not isinstance(settings, dict):
            self.settings_error = "Plik ustawień ma nieprawidłowy format."
            return {}
        if not all(
            isinstance(settings.get(key, ""), str) for key in ("version", "username")
        ):
            self.settings_error = "Plik ustawień ma nieprawidłowe dane."
            return {}
        return settings

    def save_settings(self, version, username):
        os.makedirs(self.minecraft_directory, exist_ok=True)
        temporary_path = f"{self.settings_path}.tmp"
        settings = dict(self.settings)
        settings.update({"version": version, "username": username})
        with open(temporary_path, "w", encoding="utf-8") as settings_file:
            json.dump(
                settings,
                settings_file,
                ensure_ascii=False,
                indent=2,
            )
            settings_file.write("\n")
        os.replace(temporary_path, self.settings_path)

    def set_status(self, text):
        GLib.idle_add(self.status_label.set_text, text)

    def set_busy(self, busy):
        def update():
            if busy:
                self.spinner.show()
                self.spinner.start()
                self.progress.show()
            else:
                self.spinner.stop()
                self.spinner.hide()
                self.progress.hide()
            return False

        GLib.idle_add(update)

    def set_max(self, value):
        self.progress_max = max(1, value)

    def set_progress(self, value):
        fraction = value / self.progress_max
        GLib.idle_add(self.progress.set_fraction, max(0.0, min(1.0, fraction)))

    def show_error(self, message):
        def display_error():
            dialog = Gtk.MessageDialog(
                transient_for=self,
                flags=Gtk.DialogFlags.MODAL,
                message_type=Gtk.MessageType.ERROR,
                buttons=Gtk.ButtonsType.OK,
                text="Nie udało się uruchomić Minecrafta",
            )
            dialog.format_secondary_text(message)
            dialog.run()
            dialog.destroy()
            self.launch_button.set_sensitive(True)
            self.set_busy(False)
            return False

        GLib.idle_add(display_error)

    def start_installation(self, _button):
        version = MINECRAFT_VERSION
        username = self.username_entry.get_text().strip()
        install_type = self.type_combo.get_active_id()

        if not version or not username:
            self.show_error("Podaj wersję Minecrafta i nazwę użytkownika.")
            return

        try:
            self.save_settings(version, username)
        except OSError as error:
            self.show_error(f"Nie można zapisać ustawień: {error}")
            return

        self.launch_button.set_sensitive(False)
        self.set_busy(True)
        self.progress.set_fraction(0)
        threading.Thread(
            target=self.install_and_launch,
            args=(version, username, install_type),
            daemon=True,
        ).start()

    def install_and_launch(self, version, username, install_type):
        try:
            minecraft_directory = self.minecraft_directory
            callback = {
                "setStatus": self.set_status,
                "setMax": self.set_max,
                "setProgress": self.set_progress,
            }

            version_to_launch = version
            if install_type == "fabric":
                fabric = minecraft_launcher_lib.mod_loader.get_mod_loader("fabric")
                installed_fabric = self.find_fabric_version(version)
                if installed_fabric is None:
                    self.set_status("Instalowanie Fabric...")
                    version_to_launch = fabric.install(
                        version, minecraft_directory, callback=callback
                    )
                else:
                    version_to_launch = installed_fabric
                    self.set_status("Fabric jest już zainstalowany.")
                if not self.mods_are_installed(version, minecraft_directory):
                    self.install_mods(version, minecraft_directory)
            elif not self.version_is_installed(version):
                self.set_status("Pobieranie Minecraft...")
                minecraft_launcher_lib.install.install_minecraft_version(
                    version, minecraft_directory, callback=callback
                )
            else:
                self.set_status("Minecraft jest już zainstalowany.")

            self.set_status("Uruchamianie Minecrafta...")
            options = {
                "username": username,
                "uuid": "",
                "token": "",
                "jvmArguments": [
                    f"-Xmx{max(2, int(self.settings.get('ram_gb', DEFAULT_RAM_GB)))}G"
                ],
            }
            command = minecraft_launcher_lib.command.get_minecraft_command(
                version_to_launch, minecraft_directory, options
            )
            subprocess.Popen(command)
            GLib.idle_add(self.status_label.set_text, "Minecraft uruchomiony")
            GLib.idle_add(self.launch_button.set_sensitive, True)
            self.set_busy(False)
        except Exception as error:
            self.show_error(str(error))

    def version_is_installed(self, version):
        profile = Path(self.minecraft_directory) / "versions" / version
        return (profile / f"{version}.json").is_file()

    def find_fabric_version(self, minecraft_version):
        versions_directory = Path(self.minecraft_directory) / "versions"
        profiles = versions_directory.glob(
            f"fabric-loader-*-{minecraft_version}/*.json"
        )
        return next(
            (
                profile.parent.name
                for profile in profiles
                if profile.name == f"{profile.parent.name}.json"
            ),
            None,
        )

    def mods_are_installed(self, minecraft_version, minecraft_directory):
        marker = Path(minecraft_directory) / "mods" / ".launcher-installed.json"
        try:
            with marker.open(encoding="utf-8") as marker_file:
                settings = json.load(marker_file)
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return False
        return settings == {
            "minecraft_version": minecraft_version,
            "mods": self.enabled_mods(),
        }

    def enabled_mods(self):
        configured = self.settings.get("enabled_mods")
        return [
            mod_name for mod_name in MOD_NAMES
            if configured is None or mod_name in configured
        ]

    def install_mods(self, minecraft_version, minecraft_directory):
        mods_directory = Path(minecraft_directory) / "mods"
        mods_directory.mkdir(parents=True, exist_ok=True)
        installed_projects = set()
        pending_projects = self.enabled_mods()
        session = requests.Session()
        session.headers["User-Agent"] = "MinecraftLauncher/0.1 (local launcher)"

        while pending_projects:
            project_name = pending_projects.pop(0)
            if project_name in installed_projects:
                continue

            self.set_status(f"Wyszukiwanie moda: {project_name}...")
            project = self.find_mod(session, project_name)
            versions = session.get(
                f"{MODRINTH_API}/project/{project['project_id']}/version",
                params={
                    "game_versions": json.dumps([minecraft_version]),
                    "loaders": json.dumps(["fabric"]),
                },
                timeout=30,
            )
            versions.raise_for_status()
            compatible_versions = versions.json()
            if not compatible_versions:
                raise RuntimeError(
                    f"Mod „{project_name}” nie ma wersji dla Minecrafta "
                    f"{minecraft_version} i Fabric."
                )

            mod_version = compatible_versions[0]
            primary_file = next(
                (file for file in mod_version["files"] if file.get("primary")),
                mod_version["files"][0],
            )
            target = mods_directory / primary_file["filename"]
            if not target.exists():
                self.set_status(f"Pobieranie moda: {project_name}...")
                response = session.get(primary_file["url"], timeout=60)
                response.raise_for_status()
                target.write_bytes(response.content)

            installed_projects.add(project_name)
            for dependency in mod_version.get("dependencies", []):
                if dependency.get("dependency_type") != "required":
                    continue
                dependency_id = dependency.get("project_id")
                if not dependency_id:
                    continue
                dependency_project = session.get(
                    f"{MODRINTH_API}/project/{dependency_id}", timeout=30
                )
                dependency_project.raise_for_status()
                dependency_name = dependency_project.json()["title"]
                if dependency_name not in installed_projects:
                    pending_projects.append(dependency_name)

        marker = mods_directory / ".launcher-installed.json"
        marker.write_text(
            json.dumps(
                {"minecraft_version": minecraft_version, "mods": self.enabled_mods()},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def find_mod(session, name):
        response = session.get(
            f"{MODRINTH_API}/search",
            params={"query": name, "limit": 10, "facets": json.dumps([["project_type:mod"]])},
            timeout=30,
        )
        response.raise_for_status()
        results = response.json().get("hits", [])
        normalized_name = name.casefold().replace(" ", "")
        exact_match = next(
            (
                result
                for result in results
                if result.get("title", "").casefold().replace(" ", "") == normalized_name
            ),
            None,
        )
        project = exact_match or (results[0] if results else None)
        if project is None:
            raise RuntimeError(f"Nie znaleziono moda „{name}” na Modrinth.")
        return project


def run():
    window = MinecraftLauncher()
    window.show_all()
    Gtk.main()
